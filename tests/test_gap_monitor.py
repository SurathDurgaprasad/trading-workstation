"""Real-time strategy validation mission, multi-symbol hardening pass --
tests for live/gap_monitor.py::BarGapMonitor. See that module's own
docstring for the real, live-observed gap (2026-09-15 session) this
closes.
"""
from datetime import datetime, timedelta

from live.gap_monitor import BarGapMonitor, GapStatus

_T0 = datetime(2026, 1, 1, 9, 15, 0)


def _monitor(*, interval_seconds: int = 60, multiplier: float = 3.0, repeat_seconds: int = 60) -> BarGapMonitor:
    return BarGapMonitor(
        expected_interval=timedelta(seconds=interval_seconds),
        gap_multiplier=multiplier,
        repeat_warning_interval=timedelta(seconds=repeat_seconds),
    )


def test_no_baseline_yet_never_reports_a_gap():
    """Before the first bar has ever arrived, there is nothing to be
    'gapped' relative to -- a session that hasn't started is not the
    same thing as a session with a delivery problem."""
    monitor = _monitor()
    assert monitor.check(now=_T0) is None
    assert monitor.check(now=_T0 + timedelta(hours=1)) is None


def test_within_threshold_reports_no_gap():
    monitor = _monitor(interval_seconds=60, multiplier=3.0)  # threshold = 180s
    monitor.record_new_bar(now=_T0)
    assert monitor.check(now=_T0 + timedelta(seconds=60)) is None
    assert monitor.check(now=_T0 + timedelta(seconds=179)) is None


def test_exactly_at_threshold_is_not_yet_a_gap():
    monitor = _monitor(interval_seconds=60, multiplier=3.0)  # threshold = 180s
    monitor.record_new_bar(now=_T0)
    assert monitor.check(now=_T0 + timedelta(seconds=180)) is None


def test_past_threshold_reports_a_new_gap():
    monitor = _monitor(interval_seconds=60, multiplier=3.0)  # threshold = 180s
    monitor.record_new_bar(now=_T0)
    status = monitor.check(now=_T0 + timedelta(seconds=181))
    assert isinstance(status, GapStatus)
    assert status.is_new is True
    assert status.elapsed == timedelta(seconds=181)
    assert status.threshold == timedelta(seconds=180)


def test_immediately_polling_again_during_the_same_gap_does_not_re_report():
    """The mission's own explicit requirement: do not flood output on
    every poll iteration once a gap is already being reported."""
    monitor = _monitor(interval_seconds=60, multiplier=3.0, repeat_seconds=60)
    monitor.record_new_bar(now=_T0)
    first = monitor.check(now=_T0 + timedelta(seconds=181))
    assert first is not None and first.is_new is True
    # Poll again 1 second later -- same gap, well under the 60s repeat interval.
    assert monitor.check(now=_T0 + timedelta(seconds=182)) is None
    assert monitor.check(now=_T0 + timedelta(seconds=200)) is None


def test_a_persisting_gap_re_reports_after_the_repeat_interval():
    monitor = _monitor(interval_seconds=60, multiplier=3.0, repeat_seconds=60)
    monitor.record_new_bar(now=_T0)
    first = monitor.check(now=_T0 + timedelta(seconds=181))
    assert first is not None and first.is_new is True

    still_too_soon = monitor.check(now=_T0 + timedelta(seconds=181 + 59))
    assert still_too_soon is None

    second = monitor.check(now=_T0 + timedelta(seconds=181 + 60))
    assert second is not None
    assert second.is_new is False  # a REPEAT report, not a fresh detection
    assert second.elapsed == timedelta(seconds=181 + 60)


def test_a_new_bar_clears_an_active_gap_and_resets_the_clock():
    monitor = _monitor(interval_seconds=60, multiplier=3.0)
    monitor.record_new_bar(now=_T0)
    gapped = monitor.check(now=_T0 + timedelta(seconds=200))
    assert gapped is not None

    monitor.record_new_bar(now=_T0 + timedelta(seconds=205))
    # Immediately after the new bar, well within threshold again.
    assert monitor.check(now=_T0 + timedelta(seconds=206)) is None
    # A SUBSEQUENT gap past the new baseline is reported as NEW again, not
    # as a continuation of the earlier one.
    fresh_gap = monitor.check(now=_T0 + timedelta(seconds=205 + 181))
    assert fresh_gap is not None
    assert fresh_gap.is_new is True


def test_gap_multiplier_is_configurable_and_actually_used():
    """A tighter multiplier flags a gap sooner -- proves the multiplier
    genuinely drives the threshold, not just accepted and ignored."""
    lenient = _monitor(interval_seconds=60, multiplier=10.0)  # threshold = 600s
    lenient.record_new_bar(now=_T0)
    assert lenient.check(now=_T0 + timedelta(seconds=200)) is None

    strict = _monitor(interval_seconds=60, multiplier=2.0)  # threshold = 120s
    strict.record_new_bar(now=_T0)
    assert strict.check(now=_T0 + timedelta(seconds=200)) is not None


def test_reproduces_the_real_2026_09_15_session_gap_shape():
    """Not a synthetic edge case -- the exact real numbers from
    docs/LIVE_MARKET_VALIDATION_REPORT_2026-09-15.md: 1-minute bars,
    21 clean bars, then a real ~15-minute (900s) gap before the next bar
    arrived (and was itself stale). Proves this monitor would have
    surfaced that gap in real time, not only reconstructably afterward."""
    monitor = _monitor(interval_seconds=60, multiplier=3.0)  # threshold = 180s
    last_bar_at = _T0
    monitor.record_new_bar(now=last_bar_at)
    # Polling continues every ~1s (as the real loop does) with no new bar.
    assert monitor.check(now=last_bar_at + timedelta(seconds=60)) is None  # 1 min in, still normal
    assert monitor.check(now=last_bar_at + timedelta(seconds=120)) is None  # 2 min in, still normal
    gap_report = monitor.check(now=last_bar_at + timedelta(seconds=181))  # just past 3x1m threshold
    assert gap_report is not None and gap_report.is_new is True
    # At the real 15-minute mark (900s), the gap must still be correctly
    # classified as ongoing (a repeat report, well past the 60s repeat
    # cadence since the first detection at 181s).
    still_gapped_at_15_min = monitor.check(now=last_bar_at + timedelta(seconds=900))
    assert still_gapped_at_15_min is not None
    assert still_gapped_at_15_min.is_new is False
    assert still_gapped_at_15_min.elapsed == timedelta(seconds=900)
