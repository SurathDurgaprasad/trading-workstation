from datetime import datetime, timezone

from market_intelligence.models import CandidateScore, ExcludedCandidate, ScanReport
from market_intelligence.store import ScanHistoryStore


def _report(scan_id: str = "scan-1", as_of: datetime | None = None) -> ScanReport:
    as_of = as_of or datetime(2024, 6, 1, tzinfo=timezone.utc)
    return ScanReport(
        scan_id=scan_id,
        as_of=as_of,
        universe_mode="watchlist",
        universe_size=1,
        benchmark_symbol="^NSEI",
        benchmark_unavailable_reason=None,
        config_version="abc123",
        candidates=[
            CandidateScore(
                symbol="AAPL", as_of=datetime(2024, 5, 31), last_close=190.0, avg_daily_value=1_000_000.0,
                volume_ratio=1.2, trend_score=1.0, momentum_score=0.3, breakout_score=0.02,
                relative_strength_score=0.05, sector_strength_score=None, composite_score=1.35,
                explanation=["Trend: uptrend -> score +1.00"],
            )
        ],
        excluded=[ExcludedCandidate(symbol="XYZ", as_of=None, reason="Data fetch failed: simulated outage")],
    )


def test_save_and_get_round_trips_through_pydantic_validation(tmp_path):
    store = ScanHistoryStore(tmp_path / "scanner.db")
    report = _report()
    store.save_report(report)

    fetched = store.get_report(report.scan_id)
    assert fetched == report
    store.close()


def test_get_report_returns_none_for_unknown_id(tmp_path):
    store = ScanHistoryStore(tmp_path / "scanner.db")
    assert store.get_report("does-not-exist") is None
    store.close()


def test_latest_report_returns_the_most_recent_by_as_of(tmp_path):
    store = ScanHistoryStore(tmp_path / "scanner.db")
    older = _report(scan_id="scan-old", as_of=datetime(2024, 1, 1, tzinfo=timezone.utc))
    newer = _report(scan_id="scan-new", as_of=datetime(2024, 6, 1, tzinfo=timezone.utc))
    store.save_report(older)
    store.save_report(newer)

    assert store.latest_report().scan_id == "scan-new"
    store.close()


def test_list_reports_orders_newest_first_and_respects_limit(tmp_path):
    store = ScanHistoryStore(tmp_path / "scanner.db")
    for i in range(5):
        store.save_report(_report(scan_id=f"scan-{i}", as_of=datetime(2024, 1, 1 + i, tzinfo=timezone.utc)))

    reports = store.list_reports(limit=3)
    assert [r.scan_id for r in reports] == ["scan-4", "scan-3", "scan-2"]
    store.close()


def test_store_persists_across_reconnect(tmp_path):
    db_path = tmp_path / "scanner.db"
    store = ScanHistoryStore(db_path)
    store.save_report(_report())
    store.close()

    reopened = ScanHistoryStore(db_path)
    assert reopened.get_report("scan-1") is not None
    reopened.close()
