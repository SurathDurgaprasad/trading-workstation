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


# --- CORPORATE_ACTIONS_FRESHNESS (adversarial hardening pass, 2026-09-18) ----
#
# Closes this module's own documented KNOWN GAP: corporate_actions.as_of
# was never checked against `now`. All tests below pass `now` explicitly to
# opt into the check -- see test_omitting_now_never_appends_the_freshness_
# check_at_all for proof that NOT passing it is still fully backward
# compatible with every test above.


def _dated_snapshot(*, as_of, status="AVAILABLE", actions=(), unavailable_reason=None) -> CorporateActionsSnapshot:
    return CorporateActionsSnapshot(
        symbol="RELIANCE.NS", as_of=as_of, actions=tuple(actions), status=status, unavailable_reason=unavailable_reason,
    )


def test_a_fresh_snapshot_is_allow():
    from datetime import datetime, timedelta, timezone

    now = datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc)
    snapshot = _dated_snapshot(as_of=now - timedelta(hours=1), actions=[])
    assessment = assess_event_risk(symbol="RELIANCE.NS", as_of=_AS_OF, corporate_actions=snapshot, now=now)
    assert assessment.verdict == EventRiskVerdict.ALLOW
    freshness = next(c for c in assessment.checks if c.name.value == "CORPORATE_ACTIONS_FRESHNESS")
    assert freshness.verdict == EventRiskVerdict.ALLOW
    assert "3,600" in freshness.detail  # 1 hour = 3600s, the real computed age, not a fabricated one


def test_a_stale_snapshot_is_treated_the_same_as_missing_evidence():
    from datetime import datetime, timedelta, timezone

    now = datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc)
    snapshot = _dated_snapshot(as_of=now - timedelta(hours=25), actions=[])  # past the 24h default
    assessment = assess_event_risk(symbol="RELIANCE.NS", as_of=_AS_OF, corporate_actions=snapshot, now=now)
    assert assessment.verdict == EventRiskVerdict.UNKNOWN  # config.treat_missing_corporate_actions_as's default
    freshness = next(c for c in assessment.checks if c.name.value == "CORPORATE_ACTIONS_FRESHNESS")
    assert freshness.verdict == EventRiskVerdict.UNKNOWN
    assert "exceeding" in freshness.detail


def test_stale_snapshot_missing_data_policy_is_overridable_same_as_missing_evidence():
    """The staleness verdict reuses treat_missing_corporate_actions_as --
    proving that override applies uniformly to both failure modes, not
    just the missing-evidence one."""
    from datetime import datetime, timedelta, timezone

    now = datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc)
    snapshot = _dated_snapshot(as_of=now - timedelta(hours=25), actions=[])
    config = EventRiskConfig(treat_missing_corporate_actions_as=EventRiskVerdict.BLOCK)
    assessment = assess_event_risk(symbol="RELIANCE.NS", as_of=_AS_OF, corporate_actions=snapshot, now=now, config=config)
    assert assessment.verdict == EventRiskVerdict.BLOCK


def test_a_missing_snapshot_never_triggers_a_freshness_check_at_all():
    """Freshness is meaningless without data -- already fully covered by
    CORPORATE_ACTIONS_AVAILABILITY, so no separate FRESHNESS check
    should even appear when there is nothing to date."""
    from datetime import datetime, timezone

    assessment = assess_event_risk(symbol="RELIANCE.NS", as_of=_AS_OF, corporate_actions=None, now=datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc))
    names = {c.name.value for c in assessment.checks}
    assert "CORPORATE_ACTIONS_FRESHNESS" not in names


def test_omitting_now_never_appends_the_freshness_check_at_all():
    """The design this fix landed on after an earlier draft regressed
    every pre-existing call pattern's overall verdict (see the inline
    comment above the check in event_risk.py for the full story) --
    `now=None` (the default) must produce a check list and overall
    verdict byte-identical to before this fix existed."""
    snapshot = _snapshot(status="AVAILABLE", actions=[])
    assessment = assess_event_risk(symbol="RELIANCE.NS", as_of=_AS_OF, corporate_actions=snapshot)
    names = {c.name.value for c in assessment.checks}
    assert "CORPORATE_ACTIONS_FRESHNESS" not in names
    assert assessment.verdict == EventRiskVerdict.ALLOW  # NOT downgraded to UNKNOWN merely for lacking `now`


def test_freshness_check_disabled_via_none_threshold_never_appends_either():
    from datetime import datetime, timedelta, timezone

    now = datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc)
    snapshot = _dated_snapshot(as_of=now - timedelta(days=999), actions=[])  # absurdly stale
    config = EventRiskConfig(max_corporate_actions_staleness_seconds=None)
    assessment = assess_event_risk(symbol="RELIANCE.NS", as_of=_AS_OF, corporate_actions=snapshot, now=now, config=config)
    names = {c.name.value for c in assessment.checks}
    assert "CORPORATE_ACTIONS_FRESHNESS" not in names
    assert assessment.verdict == EventRiskVerdict.ALLOW  # the absurd staleness never even gets a chance to matter


def test_a_future_timestamped_snapshot_is_not_treated_as_stale():
    """A snapshot whose as_of is (implausibly) after `now` -- age_seconds
    goes negative, which is never > a positive threshold, so this reads
    as fresh rather than crashing or being misclassified as stale. Not a
    claim this is a GOOD state (a future as_of is itself suspicious), only
    that the freshness arithmetic doesn't break under it."""
    from datetime import datetime, timedelta, timezone

    now = datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc)
    snapshot = _dated_snapshot(as_of=now + timedelta(hours=1), actions=[])
    assessment = assess_event_risk(symbol="RELIANCE.NS", as_of=_AS_OF, corporate_actions=snapshot, now=now)
    freshness = next(c for c in assessment.checks if c.name.value == "CORPORATE_ACTIONS_FRESHNESS")
    assert freshness.verdict == EventRiskVerdict.ALLOW
