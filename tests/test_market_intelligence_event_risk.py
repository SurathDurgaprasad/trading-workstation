"""EXECUTION SAFETY mission, Part 5 -- unit coverage for
market_intelligence/event_risk.py. Pure function, no I/O -- every test
constructs its own CorporateActionsSnapshot evidence directly, the same
posture tests/test_critic.py takes toward critic.engine.evaluate()."""
from datetime import date

from market_intelligence.corporate_actions import CorporateAction, CorporateActionKind, CorporateActionsSnapshot
from market_intelligence.event_risk import EventRiskConfig, EventRiskVerdict, assess_event_risk

_AS_OF = date(2026, 9, 7)


def _snapshot(*, status="AVAILABLE", actions=(), unavailable_reason=None) -> CorporateActionsSnapshot:
    from datetime import datetime, timezone

    return CorporateActionsSnapshot(
        symbol="RELIANCE.NS", as_of=datetime.now(timezone.utc), actions=tuple(actions),
        status=status, unavailable_reason=unavailable_reason,
    )


def _earnings(event_date: date) -> CorporateAction:
    return CorporateAction(symbol="RELIANCE.NS", kind=CorporateActionKind.EARNINGS_ESTIMATE, event_date=event_date, detail="test")


def test_no_corporate_actions_supplied_at_all_is_unknown_not_allow():
    assessment = assess_event_risk(symbol="RELIANCE.NS", as_of=_AS_OF, corporate_actions=None)
    assert assessment.verdict == EventRiskVerdict.UNKNOWN


def test_a_real_fetch_failure_is_unknown_not_allow():
    snapshot = _snapshot(status="UNAVAILABLE", unavailable_reason="simulated outage")
    assessment = assess_event_risk(symbol="RELIANCE.NS", as_of=_AS_OF, corporate_actions=snapshot)
    assert assessment.verdict == EventRiskVerdict.UNKNOWN
    assert "simulated outage" in assessment.checks[0].detail


def test_available_evidence_with_no_upcoming_earnings_is_allow():
    snapshot = _snapshot(status="AVAILABLE", actions=[_earnings(date(2027, 1, 1))])  # far away
    assessment = assess_event_risk(symbol="RELIANCE.NS", as_of=_AS_OF, corporate_actions=snapshot)
    assert assessment.verdict == EventRiskVerdict.ALLOW


def test_available_evidence_with_no_actions_at_all_is_allow():
    """Genuinely no earnings estimate exists for this symbol -- a real,
    valid outcome, not treated as missing evidence."""
    snapshot = _snapshot(status="AVAILABLE", actions=[])
    assessment = assess_event_risk(symbol="RELIANCE.NS", as_of=_AS_OF, corporate_actions=snapshot)
    assert assessment.verdict == EventRiskVerdict.ALLOW


def test_earnings_within_the_caution_window_is_caution():
    snapshot = _snapshot(status="AVAILABLE", actions=[_earnings(date(2026, 9, 9))])  # 2 days out
    assessment = assess_event_risk(symbol="RELIANCE.NS", as_of=_AS_OF, corporate_actions=snapshot)
    assert assessment.verdict == EventRiskVerdict.CAUTION
    detail = next(c for c in assessment.checks if c.name.value == "UPCOMING_EARNINGS").detail
    assert "2026-09-09" in detail


def test_earnings_exactly_at_the_window_boundary_is_caution():
    snapshot = _snapshot(status="AVAILABLE", actions=[_earnings(date(2026, 9, 10))])  # exactly 3 days out (default window)
    assessment = assess_event_risk(symbol="RELIANCE.NS", as_of=_AS_OF, corporate_actions=snapshot)
    assert assessment.verdict == EventRiskVerdict.CAUTION


def test_earnings_just_past_the_window_boundary_is_allow():
    snapshot = _snapshot(status="AVAILABLE", actions=[_earnings(date(2026, 9, 11))])  # 4 days out, past the default 3-day window
    assessment = assess_event_risk(symbol="RELIANCE.NS", as_of=_AS_OF, corporate_actions=snapshot)
    assert assessment.verdict == EventRiskVerdict.ALLOW


def test_a_past_earnings_date_never_triggers_caution():
    """An already-passed earnings date must never retroactively caution
    a fresh decision -- only genuinely upcoming events matter."""
    snapshot = _snapshot(status="AVAILABLE", actions=[_earnings(date(2026, 9, 1))])  # 6 days in the past
    assessment = assess_event_risk(symbol="RELIANCE.NS", as_of=_AS_OF, corporate_actions=snapshot)
    assert assessment.verdict == EventRiskVerdict.ALLOW


def test_earnings_caution_window_is_configurable():
    snapshot = _snapshot(status="AVAILABLE", actions=[_earnings(date(2026, 9, 15))])  # 8 days out
    config = EventRiskConfig(earnings_caution_days=10)
    assessment = assess_event_risk(symbol="RELIANCE.NS", as_of=_AS_OF, corporate_actions=snapshot, config=config)
    assert assessment.verdict == EventRiskVerdict.CAUTION


def test_missing_evidence_policy_is_overridable_to_allow():
    """The mission's own explicit instruction: do not globally halt
    trading merely because every optional intelligence source is
    unavailable -- a caller may explicitly choose to treat missing
    evidence as ALLOW for their own purpose, but only explicitly, never
    as this module's own silent default."""
    config = EventRiskConfig(treat_missing_corporate_actions_as=EventRiskVerdict.ALLOW)
    assessment = assess_event_risk(symbol="RELIANCE.NS", as_of=_AS_OF, corporate_actions=None, config=config)
    assert assessment.verdict == EventRiskVerdict.ALLOW


def test_missing_evidence_policy_is_overridable_to_block():
    config = EventRiskConfig(treat_missing_corporate_actions_as=EventRiskVerdict.BLOCK)
    assessment = assess_event_risk(symbol="RELIANCE.NS", as_of=_AS_OF, corporate_actions=None, config=config)
    assert assessment.verdict == EventRiskVerdict.BLOCK


def test_symbol_is_normalized_and_as_of_is_recorded():
    assessment = assess_event_risk(symbol=" reliance.ns ", as_of=_AS_OF, corporate_actions=None)
    assert assessment.symbol == "RELIANCE.NS"
    assert assessment.as_of == _AS_OF


def test_every_check_is_always_present_regardless_of_verdict():
    """Matches critic.models.CriticCheck's own "always recorded, whether
    it ran or not" discipline -- an operator must be able to see EVERY
    check's own outcome, not just the ones that happened to fire."""
    snapshot = _snapshot(status="AVAILABLE", actions=[])
    assessment = assess_event_risk(symbol="RELIANCE.NS", as_of=_AS_OF, corporate_actions=snapshot)
    names = {c.name.value for c in assessment.checks}
    assert names == {"CORPORATE_ACTIONS_AVAILABILITY", "UPCOMING_EARNINGS"}
