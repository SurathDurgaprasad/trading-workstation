"""Phase 12 §7 / Phase 13 — the live/mock pipeline driver:

    MarketDataSource -> OHLCVBar -> (growing per-symbol buffer) ->
    MarketContext-shaped indicator_series (market.indicators, UNCHANGED) ->
    Strategy (UNCHANGED) -> RiskEngine (via PaperTradingEngine, UNCHANGED) ->
    PaperTradingEngine (UNCHANGED)

Nothing in backtesting/, risk/, or paper/ is modified. This module only
SEQUENCES calls into them, the same posture every prior phase's new code has
taken toward the deterministic core.

Indicator computation stays a full recompute over an accumulating buffer on
every bar (market.indicators.compute_indicator_series, unchanged) rather
than a new incremental-update algorithm — "do not change indicator
mathematics" (Phase 12 spec §6) is satisfied literally.

Freshness gates NEW SIGNAL GENERATION only — process_bar() (existing
open-position stop/target management, existing duplicate/out-of-order
protection) always runs on every valid bar regardless of staleness; only
OPENING a new position on stale information is refused.

Phase 13 adds:
  - persistence for PENDING_HUMAN_APPROVAL signals (live/state_store.py) so
    they survive a process restart;
  - a configurable approval timeout (APPROVAL_EXPIRED once exceeded, never
    executable afterward);
  - a kill switch check before any NEW signal can reach an order (checked
    for BOTH require_human_approval modes);
  - idempotent, auditable approve_pending()/reject_pending() that NEVER
    accept a client-supplied quantity/stop/target — the method signatures
    themselves make that impossible, not a validation check that could have
    a bug (see tests/test_approval_security.py's "cannot force values into
    execution" test).
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum

import pandas as pd

from critic.models import CriticAssessment
from live.approval import SignalLifecycle, SignalLifecycleState
from live.contracts import NO_NEW_BAR, FeedDisconnectedError, MarketDataSource
from live.critic_gate import CriticGate
from live.freshness import DEFAULT_FRESHNESS_POLICY, FreshnessPolicy, FreshnessResult
from live.state_store import LiveStateStore
from market.data_provider import OHLCV, OHLCVBar
from market.indicators import TechnicalIndicators, compute_indicators, compute_indicator_series
from paper.engine import Bar, BarOutcome, PaperTradingEngine
from paper.errors import OutOfOrderBarError
from paper.models import JournalEntry
from strategy.contracts import Strategy
from strategy.signal import Signal

# Deliberately NOT a "production-correct" default -- spec explicitly says
# "do not hardcode an arbitrary production timeout, make it configurable."
# This is a reasonable value for demonstrating the expiry mechanism itself;
# an operator running paper-live sets --approval-timeout-seconds for their
# own session.
DEFAULT_APPROVAL_TIMEOUT_SECONDS = 120.0


@dataclass
class _SymbolBuffer:
    bars: list[OHLCVBar] = field(default_factory=list)

    def append(self, bar: OHLCVBar) -> None:
        self.bars.append(bar)

    def to_indicator_series(self, symbol: str, interval: str) -> pd.DataFrame:
        return compute_indicator_series(OHLCV(symbol=symbol, interval=interval, bars=self.bars))


@dataclass
class PipelineStepResult:
    """One outcome of LiveSimPipeline.process_next()."""

    kind: str  # BAR_PROCESSED | DUPLICATE_SKIPPED | OUT_OF_ORDER_REJECTED | STALE_SIGNAL_SUPPRESSED | FEED_DISCONNECTED | FEED_EXHAUSTED | NO_NEW_DATA | PENDING_HUMAN_APPROVAL | KILL_SWITCH_ACTIVE | CRITIC_REJECTED
    symbol: str | None = None
    bar: OHLCVBar | None = None
    freshness: FreshnessResult | None = None
    signal: Signal | None = None
    journal_entry: JournalEntry | None = None
    lifecycle: SignalLifecycle | None = None
    detail: str | None = None
    expired_signal_ids: list[str] = field(default_factory=list)
    critic_assessment: "CriticAssessment | None" = None
    """LIVE SYSTEM HARDENING mission: set whenever a critic_gate was
    configured and actually ran for this signal -- on CRITIC_REJECTED
    (why it was blocked) AND on a pass-through kind like BAR_PROCESSED/
    PENDING_HUMAN_APPROVAL (the critic's full assessment, for
    traceability, even when it did not block). None when no critic_gate
    is configured (unchanged, existing behavior) or the signal never
    reached the critic (e.g. KILL_SWITCH_ACTIVE, checked earlier)."""


class ApprovalActionOutcome(str, Enum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    ALREADY_DECIDED = "ALREADY_DECIDED"
    EXPIRED = "EXPIRED"
    NOT_FOUND = "NOT_FOUND"
    KILL_SWITCH_ACTIVE = "KILL_SWITCH_ACTIVE"


@dataclass
class ApprovalActionResult:
    outcome: ApprovalActionOutcome
    signal_id: str
    journal_entry: JournalEntry | None = None
    reason: str | None = None


@dataclass
class _PendingApproval:
    signal: Signal
    lifecycle: SignalLifecycle
    expires_at: datetime
    requested_quantity: int
    strategy_version: str
    risk_config_version: str


class LiveSimPipeline:
    def __init__(
        self,
        *,
        source: MarketDataSource,
        engine: PaperTradingEngine,
        strategy: Strategy,
        symbols: list[str],
        interval: str,
        freshness_policy: FreshnessPolicy = DEFAULT_FRESHNESS_POLICY,
        require_human_approval: bool = False,
        approval_timeout_seconds: float | None = DEFAULT_APPROVAL_TIMEOUT_SECONDS,
        state_store: LiveStateStore | None = None,
        clock: Callable[[], datetime] | None = None,
        critic_gate: CriticGate | None = None,
    ):
        self.source = source
        self.engine = engine
        self.strategy = strategy
        self.interval = interval
        self.freshness_policy = freshness_policy
        self.require_human_approval = require_human_approval
        self.approval_timeout_seconds = approval_timeout_seconds
        self.state_store = state_store
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self.critic_gate = critic_gate
        """LIVE SYSTEM HARDENING mission: optional, default None (byte-for-
        byte existing behavior preserved for every caller that does not
        pass one -- the entire pre-existing test suite included). When
        set, every live-generated BUY signal is evaluated against the
        SAME deterministic critic shadow-run already uses (live/
        critic_gate.py) BEFORE risk sizing; a blocking verdict (REJECT or
        INSUFFICIENT_EVIDENCE) prevents any paper order from being
        created at all -- see _handle_signal."""
        self._buffers: dict[str, _SymbolBuffer] = {}
        self.pending_approvals: dict[str, _PendingApproval] = {}
        self.lifecycles: dict[str, SignalLifecycle] = {}  # signal_id -> lifecycle, for every signal ever seen

        source.subscribe(symbols, interval)

        if self.state_store is not None:
            self._restore_pending_approvals()

    def _restore_pending_approvals(self) -> None:
        for record in self.state_store.list_pending():
            history = [(SignalLifecycleState(s), datetime.fromisoformat(ts)) for s, ts in record.history]
            lifecycle = SignalLifecycle(
                signal_id=record.signal_id, require_human_approval=True,
                state=SignalLifecycleState(record.state), history=history,
            )
            self.lifecycles[record.signal_id] = lifecycle
            self.pending_approvals[record.signal_id] = _PendingApproval(
                signal=record.signal, lifecycle=lifecycle, expires_at=datetime.fromisoformat(record.expires_at),
                requested_quantity=record.requested_quantity, strategy_version=record.strategy_version,
                risk_config_version=record.risk_config_version,
            )

    # -- kill switch (delegates entirely to state_store; a no-op without one) ---

    def is_kill_switch_active(self) -> bool:
        return self.state_store is not None and self.state_store.is_kill_switch_active()

    def _connection_state_label(self) -> str:
        """LIVE SYSTEM HARDENING mission, Part 3 (data-source health):
        real gap found -- this pipeline only ever asked is_connected()
        (a bool), collapsing a richer connection-state some sources track
        internally (e.g. a distinct CONNECTING / RECONNECTING / FAILED /
        CLOSED, not just CONNECTED/DISCONNECTED) down to a coarse
        boolean before it ever reached feed_status/the dashboard -- an
        operator could not tell "actively retrying" from "gave up" from
        "never connected".

        `source.state` is an OPTIONAL extra some MarketDataSource
        implementations expose beyond the generic live.contracts.
        MarketDataSource Protocol (which only requires is_connected()) --
        this stays a soft, getattr-based capability check, never a hard
        dependency on any one implementation, so a source without it
        (like the mock replay source) is completely unaffected. No new
        persisted column: connection_state was always a plain TEXT
        field; this only changes what value it can receive, which the
        dashboard already knows how to display as-is."""
        state = getattr(self.source, "state", None)
        if state is not None:
            return state
        return "CONNECTED" if self.source.is_connected() else "DISCONNECTED"

    def latest_indicators(self, symbol: str) -> TechnicalIndicators | None:
        """Read-only accessor for the most recently computed indicator
        snapshot (same rolling/ewm math as the signal-generating series,
        via the existing single-snapshot compute_indicators) -- for
        CLI/dashboard/AI-explanation display only. Returns None until at
        least one bar for `symbol` has been processed."""
        buffer = self._buffers.get(symbol)
        if buffer is None or not buffer.bars:
            return None
        return compute_indicators(OHLCV(symbol=symbol, interval=self.interval, bars=buffer.bars))

    # -- main loop --------------------------------------------------------------

    def process_next(self) -> PipelineStepResult:
        expired = self.expire_pending_approvals()

        try:
            event = self.source.next_bar()
        except FeedDisconnectedError as exc:
            return PipelineStepResult(kind="FEED_DISCONNECTED", detail=str(exc), expired_signal_ids=expired)

        if event is NO_NEW_BAR:
            # The feed is alive but had nothing new within this poll (a
            # real, open-ended streaming source, as opposed to a finite
            # scripted replay) -- distinct from FEED_EXHAUSTED, which means
            # the source will never produce another bar. Existing
            # positions/kill-switch/expiry checks above already ran;
            # there's simply no bar to process this call. See
            # live/contracts.py's NO_NEW_BAR docstring.
            return PipelineStepResult(kind="NO_NEW_DATA", expired_signal_ids=expired)

        if event is None:
            return PipelineStepResult(kind="FEED_EXHAUSTED", expired_signal_ids=expired)

        symbol, bar = event.symbol, event.bar
        buffer = self._buffers.setdefault(symbol, _SymbolBuffer())
        buffer.append(bar)

        if self.state_store is not None:
            # Phase 15 §7/§22: the ONLY way a separate process (the
            # dashboard) can honestly know what the feed most recently
            # delivered -- written the moment a bar arrives, independent of
            # what the paper engine goes on to do with it (duplicate/
            # out-of-order/stale are all still "the feed is alive and
            # delivering bar_timestamp", which is exactly what this
            # records).
            self.state_store.save_feed_status(
                symbol=symbol, source=bar.source.value, status=bar.status.value,
                bar_timestamp=bar.timestamp, received_at=bar.received_at or self._clock(),
                connection_state=self._connection_state_label(), last_price=bar.close,
            )

        engine_bar = Bar(timestamp=bar.timestamp, open=bar.open, high=bar.high, low=bar.low, close=bar.close, volume=bar.volume)
        try:
            outcome = self.engine.process_bar(symbol, engine_bar)
        except OutOfOrderBarError as exc:
            return PipelineStepResult(kind="OUT_OF_ORDER_REJECTED", symbol=symbol, bar=bar, detail=str(exc), expired_signal_ids=expired)

        if outcome == BarOutcome.DUPLICATE_SKIPPED:
            return PipelineStepResult(kind="DUPLICATE_SKIPPED", symbol=symbol, bar=bar, expired_signal_ids=expired)

        now = self._clock()
        freshness = self.freshness_policy.check(bar.timestamp, interval=self.interval, now=now)
        if not freshness.is_fresh:
            return PipelineStepResult(kind="STALE_SIGNAL_SUPPRESSED", symbol=symbol, bar=bar, freshness=freshness, expired_signal_ids=expired)

        indicator_series = buffer.to_indicator_series(symbol, self.interval)
        signal = self.strategy.generate_signal(indicator_series, len(indicator_series) - 1, symbol)
        if signal is None:
            return PipelineStepResult(kind="BAR_PROCESSED", symbol=symbol, bar=bar, freshness=freshness, expired_signal_ids=expired)

        if self.is_kill_switch_active():
            return PipelineStepResult(kind="KILL_SWITCH_ACTIVE", symbol=symbol, bar=bar, freshness=freshness, signal=signal, expired_signal_ids=expired)

        result = self._handle_signal(signal, symbol=symbol, bar=bar, freshness=freshness)
        result.expired_signal_ids = expired
        return result

    def _handle_signal(self, signal: Signal, *, symbol: str, bar: OHLCVBar, freshness: FreshnessResult) -> PipelineStepResult:
        signal_id = signal.stable_id()
        lifecycle = self.lifecycles.setdefault(signal_id, SignalLifecycle(signal_id=signal_id, require_human_approval=self.require_human_approval))

        critic_assessment = None
        if self.critic_gate is not None:
            now = self._clock()
            gate_result = self.critic_gate.evaluate(
                signal, indicators=self.latest_indicators(symbol), now=now,
                kill_switch_active=self.is_kill_switch_active(),
                existing_pending_order=self.engine.store.get_pending_order(symbol) is not None,
                existing_open_position=self.engine.store.get_open_position(symbol) is not None,
            )
            critic_assessment = gate_result.assessment
            if gate_result.blocked:
                lifecycle.transition_to(SignalLifecycleState.CRITIC_REJECTED)
                if self.state_store is not None:
                    self.state_store.save_critic_rejection(
                        signal_id=signal_id, symbol=symbol,
                        verdict=gate_result.assessment.verdict.value if gate_result.assessment else "EVIDENCE_UNAVAILABLE",
                        reasons=list(gate_result.assessment.reasons) if gate_result.assessment else [gate_result.block_reason],
                        checks=[c.model_dump(mode="json") for c in gate_result.assessment.checks] if gate_result.assessment else [],
                        rejected_at=now,
                    )
                return PipelineStepResult(
                    kind="CRITIC_REJECTED", symbol=symbol, bar=bar, freshness=freshness, signal=signal,
                    lifecycle=lifecycle, detail=gate_result.block_reason, critic_assessment=critic_assessment,
                )

        if not self.require_human_approval:
            journal = self.engine.submit_signal(signal)
            was_approved = journal.outcome.value.startswith("APPROVED")
            lifecycle.transition_to(SignalLifecycleState.RISK_APPROVED if was_approved else SignalLifecycleState.RISK_REJECTED)
            if was_approved:
                lifecycle.transition_to(SignalLifecycleState.EXECUTED)
            return PipelineStepResult(
                kind="BAR_PROCESSED", symbol=symbol, bar=bar, freshness=freshness, signal=signal,
                journal_entry=journal, lifecycle=lifecycle, critic_assessment=critic_assessment,
            )

        # require_human_approval=True: evaluate risk WITHOUT submitting — no
        # order is created yet. The FIRST of two risk checks; the second
        # happens inside submit_signal() at approve_pending() time, against
        # then-current account state.
        decision = self.engine.risk_engine.evaluate(signal, self.engine.account)
        if not decision.approved:
            lifecycle.transition_to(SignalLifecycleState.RISK_REJECTED)
            return PipelineStepResult(
                kind="BAR_PROCESSED", symbol=symbol, bar=bar, freshness=freshness, signal=signal,
                lifecycle=lifecycle, critic_assessment=critic_assessment,
            )

        lifecycle.transition_to(SignalLifecycleState.RISK_APPROVED)
        lifecycle.transition_to(SignalLifecycleState.PENDING_HUMAN_APPROVAL)

        now = self._clock()
        expires_at = now + timedelta(seconds=self.approval_timeout_seconds) if self.approval_timeout_seconds is not None else now + timedelta(days=36500)
        requested_quantity = decision.position_size.quantity if decision.position_size else 0
        pending = _PendingApproval(
            signal=signal, lifecycle=lifecycle, expires_at=expires_at, requested_quantity=requested_quantity,
            strategy_version=getattr(self.strategy, "version", "1.0"), risk_config_version=self.engine.risk_engine.config.version_id(),
        )
        self.pending_approvals[signal_id] = pending

        if self.state_store is not None:
            self.state_store.save_pending_approval(
                signal=signal, strategy_version=pending.strategy_version, risk_config_version=pending.risk_config_version,
                requested_quantity=requested_quantity, state=lifecycle.state.value, history=lifecycle.history,
                created_at=now, expires_at=expires_at,
            )

        return PipelineStepResult(
            kind="PENDING_HUMAN_APPROVAL", symbol=symbol, bar=bar, freshness=freshness, signal=signal,
            lifecycle=lifecycle, critic_assessment=critic_assessment,
        )

    def mark_ai_explained(self, signal_id: str) -> None:
        """Optional — call after actually running agents.signal_explainer
        (unchanged), before the signal reaches PENDING_HUMAN_APPROVAL. Not
        called by process_next() itself, since AI stays optional and this
        module has zero LLM dependency."""
        pending = self.pending_approvals.get(signal_id)
        lifecycle = pending.lifecycle if pending else self.lifecycles.get(signal_id)
        if lifecycle is not None and lifecycle.state == SignalLifecycleState.RISK_APPROVED:
            lifecycle.transition_to(SignalLifecycleState.AI_EXPLAINED)

    # -- expiry -------------------------------------------------------------------

    def expire_pending_approvals(self, now: datetime | None = None) -> list[str]:
        """Called automatically at the start of every process_next(), and
        exposed standalone so a CLI/dashboard can also call it between bars
        (a human might sit on a decision longer than the gap between two
        market bars). Returns the signal_ids that expired this call."""
        now = now or self._clock()
        expired_ids = []
        for signal_id, pending in list(self.pending_approvals.items()):
            if now > pending.expires_at:
                pending.lifecycle.transition_to(SignalLifecycleState.APPROVAL_EXPIRED, now=now)
                if self.state_store is not None:
                    self.state_store.update_decision(
                        signal_id, state=pending.lifecycle.state.value, history=pending.lifecycle.history,
                        decision="EXPIRED", decision_reason="approval_timeout_seconds exceeded", decided_at=now,
                    )
                del self.pending_approvals[signal_id]
                expired_ids.append(signal_id)
        return expired_ids

    # -- human actions --------------------------------------------------------------
    # Deliberately take ONLY signal_id (+ an optional free-text reason) — no
    # quantity/stop/target/approved-flag parameter exists on these methods
    # AT ALL, so there is no argument a caller could ever pass to override
    # execution parameters. See tests/test_approval_security.py.

    def approve_pending(self, signal_id: str, *, reason: str | None = None) -> ApprovalActionResult:
        outcome = self._check_actionable(signal_id)
        if outcome is not None:
            return outcome

        pending = self.pending_approvals.pop(signal_id)
        now = self._clock()
        pending.lifecycle.transition_to(SignalLifecycleState.HUMAN_APPROVED, now=now)

        # THE mandatory second risk check — re-derives everything from
        # CURRENT account state via the real RiskEngine, inside
        # submit_signal(). The signal's own price levels are immutable
        # (frozen Pydantic, set at generation time); only account-dependent
        # sizing/approval is re-evaluated here.
        journal = self.engine.submit_signal(pending.signal)
        was_approved = journal.outcome.value.startswith("APPROVED")
        final_state = SignalLifecycleState.EXECUTED if was_approved else SignalLifecycleState.RISK_REJECTED
        pending.lifecycle.transition_to(final_state, now=self._clock())

        approved_quantity = None
        if journal.risk_decision_id:
            redecision = self.engine.store.get_risk_decision(journal.risk_decision_id)
            if redecision and redecision.position_size:
                approved_quantity = redecision.position_size.quantity

        if self.state_store is not None:
            self.state_store.update_decision(
                signal_id, state=pending.lifecycle.state.value, history=pending.lifecycle.history, decision="APPROVE",
                decision_reason=reason, approved_quantity=approved_quantity, final_execution_result=journal.outcome.value, decided_at=now,
            )

        result_outcome = ApprovalActionOutcome.APPROVED if was_approved else ApprovalActionOutcome.REJECTED
        return ApprovalActionResult(outcome=result_outcome, signal_id=signal_id, journal_entry=journal, reason=reason)

    def reject_pending(self, signal_id: str, *, reason: str | None = None) -> ApprovalActionResult:
        outcome = self._check_actionable(signal_id)
        if outcome is not None:
            return outcome

        pending = self.pending_approvals.pop(signal_id)
        now = self._clock()
        pending.lifecycle.transition_to(SignalLifecycleState.HUMAN_REJECTED, now=now)

        if self.state_store is not None:
            self.state_store.update_decision(
                signal_id, state=pending.lifecycle.state.value, history=pending.lifecycle.history,
                decision="REJECT", decision_reason=reason, decided_at=now,
            )
        return ApprovalActionResult(outcome=ApprovalActionOutcome.REJECTED, signal_id=signal_id, reason=reason)

    def _check_actionable(self, signal_id: str) -> ApprovalActionResult | None:
        """Returns a terminal ApprovalActionResult if the signal_id is NOT
        currently actionable (idempotency: approving/rejecting twice,
        approving an expired or already-executed signal, or an unknown
        signal_id, are all reported explicitly rather than raising or
        silently re-executing)."""
        if self.is_kill_switch_active():
            return ApprovalActionResult(outcome=ApprovalActionOutcome.KILL_SWITCH_ACTIVE, signal_id=signal_id, reason="kill switch is active")

        if signal_id in self.pending_approvals:
            pending = self.pending_approvals[signal_id]
            now = self._clock()
            if now > pending.expires_at:
                self.expire_pending_approvals(now)
                return ApprovalActionResult(outcome=ApprovalActionOutcome.EXPIRED, signal_id=signal_id, reason="approval_timeout_seconds exceeded")
            return None  # actionable

        lifecycle = self.lifecycles.get(signal_id)
        if lifecycle is None:
            return ApprovalActionResult(outcome=ApprovalActionOutcome.NOT_FOUND, signal_id=signal_id, reason="no signal with this id was ever generated")
        if lifecycle.state == SignalLifecycleState.APPROVAL_EXPIRED:
            return ApprovalActionResult(outcome=ApprovalActionOutcome.EXPIRED, signal_id=signal_id, reason="already expired")
        return ApprovalActionResult(outcome=ApprovalActionOutcome.ALREADY_DECIDED, signal_id=signal_id, reason=f"already in terminal state {lifecycle.state.value}")
