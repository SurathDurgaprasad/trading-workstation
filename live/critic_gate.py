"""LIVE SYSTEM HARDENING mission -- wires the deterministic critic
(critic.engine.evaluate(), already used by `shadow-run`) into `paper-live`.

Real architectural gap this closes: LiveSimPipeline.process_next() calls
strategy.generate_signal() directly and never constructs a
decision_engine.models.Decision at all (confirmed by reading
live/pipeline.py before writing this module) -- it has no scanner
evidence, no market_context in the decision_engine sense, nothing
critic.engine.evaluate() requires. shadow-run's own Decision comes from
decision_engine.engine.make_decision(), which derives its LABEL from
decision_engine.rules.classify(candidate, risk_context) -- a computation
based ENTIRELY on scanner evidence, independent of any live strategy's
own signal. Calling make_decision() here would let classify() silently
produce a DIFFERENT label (WATCH/AVOID/NO_ACTION) than the BUY the live
strategy already, separately decided -- critic.engine.evaluate() requires
label == BUY and raises otherwise. So this module does NOT call
make_decision(): it builds the Decision directly, with label=BUY (the
live strategy's own already-real decision, unchanged), and attaches real,
independently-computed scanner_evidence/market_context/confidence for the
critic to genuinely scrutinize -- exactly the critic's actual designed
purpose ("independently re-examines an already-proposed BUY... against
evidence decision_engine.rules.classify never looks at", per critic/
engine.py's own docstring).

Scanner evidence (CandidateScore) and benchmark/regime context are
daily-timeframe signals (the scanner's own trend/momentum/breakout
scores are SMA20/50, RSI14, 20-bar-high computations -- meant for a
"does this look interesting structurally" read, not a live tick).
Recomputing them on every live bar would be wasted network calls, not
extra safety, so CriticGate refreshes them on a bounded timer
(default 15 minutes) via the SAME public run_scan()/
compute_benchmark_context() functions shadow-run already uses -- a real,
single-symbol scan, never a duplicated re-implementation of the scanner's
own scoring logic.

Fails closed: any exception while refreshing evidence or evaluating is
treated as BLOCKED, with the error recorded as the block reason -- never
silently treated as a pass.
"""

import time
from dataclasses import dataclass
from datetime import datetime, timezone

from critic.config import CriticConfig
from critic.engine import evaluate as critic_evaluate
from critic.models import CriticAssessment, CriticVerdict
from decision_engine.confidence import compute_confidence
from decision_engine.models import Decision, DecisionLabel, RiskContext
from market.context import MarketContext
from market.data_provider import MarketDataProvider
from market.indicators import TechnicalIndicators
from market_data.universe import MarketUniverse
from market_intelligence.regime import BenchmarkContext, compute_benchmark_context
from market_intelligence.scanner import run_scan
from strategy.signal import Signal

DEFAULT_REFRESH_SECONDS = 900.0  # 15 minutes -- see module docstring for why daily-timeframe evidence does not need per-tick refreshing

BLOCKING_VERDICTS = (CriticVerdict.REJECT, CriticVerdict.INSUFFICIENT_EVIDENCE)
"""Matches shadow-run's own existing _bridge_to_paper_execution policy in
main.py exactly (critic_blocks_execution = verdict in (REJECT,
INSUFFICIENT_EVIDENCE)) -- not a new rule invented for this module.
DOWNGRADE and APPROVE both let a signal proceed to risk/execution, same
as shadow-run's own precedent."""


@dataclass(frozen=True)
class CriticGateResult:
    blocked: bool
    block_reason: str
    """Human-readable, always populated when blocked=True; empty otherwise."""
    assessment: CriticAssessment | None
    """None only when evidence refresh itself failed (fail-closed) -- the
    critic never ran because it had nothing real to evaluate against."""
    decision: Decision | None


class CriticGate:
    """One instance per (symbol, interval) -- mirrors CandleBuilder's own
    one-instance-per-symbol lifecycle. Stateful only in its evidence
    cache; evaluate() itself is otherwise a thin, deterministic bridge."""

    def __init__(
        self,
        *,
        symbol: str,
        provider: MarketDataProvider,
        benchmark_symbol: str | None,
        config: CriticConfig | None = None,
        refresh_seconds: float = DEFAULT_REFRESH_SECONDS,
        period: str = "1y",
        interval: str = "1d",
        clock=time.monotonic,
    ):
        self._symbol = symbol.strip().upper()
        self._provider = provider
        self._benchmark_symbol = benchmark_symbol
        self._config = config or CriticConfig()
        self._refresh_seconds = refresh_seconds
        self._period = period
        self._interval = interval
        self._clock = clock

        self._candidate = None
        self._exclusion_reason: str | None = None
        self._benchmark_context: BenchmarkContext | None = None
        self._last_refresh: float | None = None
        self._last_refresh_error: str | None = None

    @property
    def last_refresh_error(self) -> str | None:
        return self._last_refresh_error

    def _refresh_if_needed(self) -> None:
        now = self._clock()
        if self._last_refresh is not None and (now - self._last_refresh) < self._refresh_seconds:
            return
        try:
            universe = MarketUniverse.from_watchlist([self._symbol])
            report = run_scan(
                universe, provider=self._provider, benchmark_symbol=self._benchmark_symbol,
                period=self._period, interval=self._interval,
            )
            self._candidate = report.get(self._symbol)
            self._exclusion_reason = next(
                (e.reason for e in report.excluded if e.symbol == self._symbol), None
            ) if self._candidate is None else None
            self._benchmark_context = compute_benchmark_context(
                self._benchmark_symbol, provider=self._provider, period=self._period, interval=self._interval,
            )
            self._last_refresh_error = None
        except Exception as exc:  # noqa: BLE001 -- fail closed, never crash the live loop over a data refresh
            self._last_refresh_error = f"{type(exc).__name__}: {exc}"
        self._last_refresh = now

    def evaluate(
        self,
        signal: Signal,
        *,
        indicators: TechnicalIndicators | None,
        now: datetime | None = None,
        kill_switch_active: bool | None,
        existing_pending_order: bool,
        existing_open_position: bool,
    ) -> CriticGateResult:
        self._refresh_if_needed()

        if self._candidate is None:
            if self._last_refresh_error:
                reason = f"No real scanner evidence available for {self._symbol} -- {self._last_refresh_error}"
            elif self._exclusion_reason:
                reason = f"No real scanner evidence available for {self._symbol} -- {self._exclusion_reason}"
            else:
                reason = f"No real scanner evidence available for {self._symbol} (excluded from screening or no history)."
            return CriticGateResult(blocked=True, block_reason=reason, assessment=None, decision=None)

        market_context = MarketContext.from_indicators(indicators) if indicators is not None else None
        resolved_now = now or datetime.now(timezone.utc)

        decision = Decision(
            decision_id=Decision.new_id(),
            symbol=self._symbol,
            as_of=resolved_now,
            label=DecisionLabel.BUY,
            rationale=[
                f"{self._symbol}: live strategy ({signal.strategy_name}) generated a BUY signal "
                f"({', '.join(rc.value for rc in signal.reason_codes)}) -- this label reflects that live "
                "decision directly, not decision_engine.rules.classify() (deliberately not called here; "
                "see live/critic_gate.py's own module docstring for why)."
            ],
            config_version="live-critic-gate-direct",
            scanner_evidence=self._candidate,
            research_evidence=None,
            market_context=market_context,
            risk_context=RiskContext(has_open_position=existing_open_position),
            confidence=compute_confidence(self._candidate).score,
            confidence_explanation=compute_confidence(self._candidate).explanation(),
            narrative=None,
            narrative_unavailable_reason="Critic gate evaluation is deterministic-only by design -- no LLM narration is attempted here.",
        )

        assessment = critic_evaluate(
            decision, signal, config=self._config, now=resolved_now, kill_switch_active=kill_switch_active,
            existing_pending_order=existing_pending_order, existing_open_position=existing_open_position,
            benchmark_context=self._benchmark_context,
        )
        blocked = assessment.verdict in BLOCKING_VERDICTS
        block_reason = assessment.reasons[0] if blocked and assessment.reasons else ("Critic verdict: " + assessment.verdict.value if blocked else "")
        return CriticGateResult(blocked=blocked, block_reason=block_reason, assessment=assessment, decision=decision)
