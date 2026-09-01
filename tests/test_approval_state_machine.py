import pytest

from live.approval import IllegalStateTransitionError, SignalLifecycle, SignalLifecycleState


def test_starts_at_signal_generated():
    lifecycle = SignalLifecycle(signal_id="abc", require_human_approval=False)
    assert lifecycle.state == SignalLifecycleState.SIGNAL_GENERATED
    assert not lifecycle.is_terminal


def test_risk_rejection_is_terminal():
    lifecycle = SignalLifecycle(signal_id="abc", require_human_approval=False)
    lifecycle.transition_to(SignalLifecycleState.RISK_REJECTED)
    assert lifecycle.is_terminal
    with pytest.raises(IllegalStateTransitionError):
        lifecycle.transition_to(SignalLifecycleState.RISK_APPROVED)


def test_auto_paper_mode_allows_the_direct_shortcut_to_executed():
    """require_human_approval=False -- today's existing paper-auto-execute
    behavior remains legal and unchanged."""
    lifecycle = SignalLifecycle(signal_id="abc", require_human_approval=False)
    lifecycle.transition_to(SignalLifecycleState.RISK_APPROVED)
    lifecycle.transition_to(SignalLifecycleState.EXECUTED)
    assert lifecycle.state == SignalLifecycleState.EXECUTED
    assert lifecycle.is_terminal


def test_human_approval_mode_forbids_the_shortcut_structurally():
    """The core guarantee: once require_human_approval=True, RISK_APPROVED
    -> EXECUTED is not merely discouraged, it is ABSENT from the legal
    transition graph -- attempting it raises."""
    lifecycle = SignalLifecycle(signal_id="abc", require_human_approval=True)
    lifecycle.transition_to(SignalLifecycleState.RISK_APPROVED)
    with pytest.raises(IllegalStateTransitionError):
        lifecycle.transition_to(SignalLifecycleState.EXECUTED)


def test_human_approval_mode_forbids_ai_explained_shortcut_too():
    lifecycle = SignalLifecycle(signal_id="abc", require_human_approval=True)
    lifecycle.transition_to(SignalLifecycleState.RISK_APPROVED)
    lifecycle.transition_to(SignalLifecycleState.AI_EXPLAINED)
    with pytest.raises(IllegalStateTransitionError):
        lifecycle.transition_to(SignalLifecycleState.EXECUTED)


def test_full_human_approval_path_reaches_executed():
    lifecycle = SignalLifecycle(signal_id="abc", require_human_approval=True)
    lifecycle.transition_to(SignalLifecycleState.RISK_APPROVED)
    lifecycle.transition_to(SignalLifecycleState.AI_EXPLAINED)
    lifecycle.transition_to(SignalLifecycleState.PENDING_HUMAN_APPROVAL)
    lifecycle.transition_to(SignalLifecycleState.HUMAN_APPROVED)
    lifecycle.transition_to(SignalLifecycleState.EXECUTED)
    assert lifecycle.state == SignalLifecycleState.EXECUTED
    assert [s for s, _ in lifecycle.history] == [
        SignalLifecycleState.SIGNAL_GENERATED,
        SignalLifecycleState.RISK_APPROVED,
        SignalLifecycleState.AI_EXPLAINED,
        SignalLifecycleState.PENDING_HUMAN_APPROVAL,
        SignalLifecycleState.HUMAN_APPROVED,
        SignalLifecycleState.EXECUTED,
    ]


def test_ai_explanation_step_is_optional_even_in_human_approval_mode():
    """RISK_APPROVED -> PENDING_HUMAN_APPROVAL directly (skipping AI) is
    always legal -- AI remains optional per the target architecture."""
    lifecycle = SignalLifecycle(signal_id="abc", require_human_approval=True)
    lifecycle.transition_to(SignalLifecycleState.RISK_APPROVED)
    lifecycle.transition_to(SignalLifecycleState.PENDING_HUMAN_APPROVAL)
    lifecycle.transition_to(SignalLifecycleState.HUMAN_APPROVED)
    lifecycle.transition_to(SignalLifecycleState.EXECUTED)
    assert lifecycle.state == SignalLifecycleState.EXECUTED


def test_human_rejection_is_terminal():
    lifecycle = SignalLifecycle(signal_id="abc", require_human_approval=True)
    lifecycle.transition_to(SignalLifecycleState.RISK_APPROVED)
    lifecycle.transition_to(SignalLifecycleState.PENDING_HUMAN_APPROVAL)
    lifecycle.transition_to(SignalLifecycleState.HUMAN_REJECTED)
    assert lifecycle.is_terminal
    with pytest.raises(IllegalStateTransitionError):
        lifecycle.transition_to(SignalLifecycleState.HUMAN_APPROVED)


def test_cannot_skip_from_signal_generated_straight_to_pending_approval():
    lifecycle = SignalLifecycle(signal_id="abc", require_human_approval=True)
    with pytest.raises(IllegalStateTransitionError):
        lifecycle.transition_to(SignalLifecycleState.PENDING_HUMAN_APPROVAL)
