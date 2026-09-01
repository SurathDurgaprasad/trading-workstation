"""Phase 12 §8 — the human-approval domain state machine. Target flow:

    SIGNAL_GENERATED -> RISK_APPROVED -> AI_EXPLAINED -> PENDING_HUMAN_APPROVAL
        -> HUMAN_APPROVED -> EXECUTED

This module defines the STATES and legal TRANSITIONS only — it does not
decide what counts as "approved" (RiskEngine, unchanged, does that) or run
the AI (agents.signal_explainer, unchanged, does that) or execute anything
(PaperTradingEngine, unchanged, does that). It exists so that once
human-approval is required, no code path can skip straight from a risk
decision to execution — enforced structurally, not by convention.

`require_human_approval=False` keeps today's existing paper-trading
shortcut legal (RISK_APPROVED -> EXECUTED directly, matching how
PaperTradingEngine.submit_signal already works, unchanged) — Phase 12 does
not touch that default behavior. `require_human_approval=True` REMOVES that
shortcut from the legal-transition graph entirely: the only path to
EXECUTED becomes PENDING_HUMAN_APPROVAL -> HUMAN_APPROVED -> EXECUTED. No
"trust me, I checked" flag lets code skip this once enabled — the graph
itself makes the shortcut illegal.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class SignalLifecycleState(str, Enum):
    SIGNAL_GENERATED = "SIGNAL_GENERATED"
    RISK_APPROVED = "RISK_APPROVED"
    RISK_REJECTED = "RISK_REJECTED"
    AI_EXPLAINED = "AI_EXPLAINED"
    PENDING_HUMAN_APPROVAL = "PENDING_HUMAN_APPROVAL"
    HUMAN_APPROVED = "HUMAN_APPROVED"
    HUMAN_REJECTED = "HUMAN_REJECTED"
    APPROVAL_EXPIRED = "APPROVAL_EXPIRED"  # Phase 13 -- pending too long, never executable afterward
    EXECUTED = "EXECUTED"


class IllegalStateTransitionError(Exception):
    def __init__(self, current: SignalLifecycleState, attempted: SignalLifecycleState, *, require_human_approval: bool):
        self.current = current
        self.attempted = attempted
        super().__init__(
            f"Illegal transition {current.value} -> {attempted.value} "
            f"(require_human_approval={require_human_approval})."
        )


def legal_transitions(require_human_approval: bool) -> dict[SignalLifecycleState, set[SignalLifecycleState]]:
    graph: dict[SignalLifecycleState, set[SignalLifecycleState]] = {
        SignalLifecycleState.SIGNAL_GENERATED: {SignalLifecycleState.RISK_APPROVED, SignalLifecycleState.RISK_REJECTED},
        SignalLifecycleState.RISK_APPROVED: {SignalLifecycleState.AI_EXPLAINED, SignalLifecycleState.PENDING_HUMAN_APPROVAL},
        SignalLifecycleState.AI_EXPLAINED: {SignalLifecycleState.PENDING_HUMAN_APPROVAL},
        SignalLifecycleState.PENDING_HUMAN_APPROVAL: {
            SignalLifecycleState.HUMAN_APPROVED, SignalLifecycleState.HUMAN_REJECTED, SignalLifecycleState.APPROVAL_EXPIRED,
        },
        # RISK_REJECTED is reachable from HUMAN_APPROVED because the SECOND
        # risk check (submit_signal(), run fresh at approval time) can still
        # say no if account state changed between the first check and the
        # human's decision -- the target flow's own "risk check again" step
        # is not a formality, and this transition is what lets that honest
        # outcome be represented rather than forced into EXECUTED.
        SignalLifecycleState.HUMAN_APPROVED: {SignalLifecycleState.EXECUTED, SignalLifecycleState.RISK_REJECTED},
        SignalLifecycleState.RISK_REJECTED: set(),
        SignalLifecycleState.HUMAN_REJECTED: set(),
        SignalLifecycleState.APPROVAL_EXPIRED: set(),
        SignalLifecycleState.EXECUTED: set(),
    }
    if not require_human_approval:
        # ONLY legal when human approval is not required (today's existing
        # paper-auto-execute posture) -- deliberately absent from the graph
        # otherwise, so it cannot be reached by any caller, by construction.
        graph[SignalLifecycleState.RISK_APPROVED].add(SignalLifecycleState.EXECUTED)
        graph[SignalLifecycleState.AI_EXPLAINED].add(SignalLifecycleState.EXECUTED)
    return graph


@dataclass
class SignalLifecycle:
    """Tracks one signal's journey through the approval flow. `signal_id`
    should be Signal.stable_id() so history ties back to the same identity
    idempotency already uses everywhere else in this project."""

    signal_id: str
    require_human_approval: bool
    state: SignalLifecycleState = SignalLifecycleState.SIGNAL_GENERATED
    history: list[tuple[SignalLifecycleState, datetime]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.history:
            self.history.append((self.state, datetime.now(timezone.utc)))

    def transition_to(self, new_state: SignalLifecycleState, *, now: datetime | None = None) -> None:
        allowed = legal_transitions(self.require_human_approval).get(self.state, set())
        if new_state not in allowed:
            raise IllegalStateTransitionError(self.state, new_state, require_human_approval=self.require_human_approval)
        self.state = new_state
        self.history.append((new_state, now or datetime.now(timezone.utc)))

    @property
    def is_terminal(self) -> bool:
        return self.state in (
            SignalLifecycleState.RISK_REJECTED, SignalLifecycleState.HUMAN_REJECTED,
            SignalLifecycleState.APPROVAL_EXPIRED, SignalLifecycleState.EXECUTED,
        )
