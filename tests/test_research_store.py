from datetime import datetime, timezone

from research.models import NewsItem, ResearchReport, ResearchSummary, SectorInfo
from research.store import ResearchStore


def _report(report_id: str = "report-1", symbol: str = "AAPL", as_of: datetime | None = None) -> ResearchReport:
    as_of = as_of or datetime(2024, 6, 1, tzinfo=timezone.utc)
    return ResearchReport(
        report_id=report_id,
        symbol=symbol,
        as_of=as_of,
        news=[
            NewsItem(
                title="Headline", summary="Summary.", source="Yahoo Finance",
                url="https://example.com/a", published_at=datetime(2024, 5, 31, tzinfo=timezone.utc),
            )
        ],
        sector=SectorInfo(symbol=symbol, sector="Technology", industry="Consumer Electronics", as_of=as_of),
        ai_summary=ResearchSummary(summary="Neutral.", confidence=0.5, unknowns=["Whether this continues."]),
        ai_summary_unavailable_reason=None,
    )


def test_save_and_get_round_trips_through_pydantic_validation(tmp_path):
    store = ResearchStore(tmp_path / "research.db")
    report = _report()
    store.save_report(report)

    fetched = store.get_report(report.report_id)
    assert fetched == report
    store.close()


def test_get_report_returns_none_for_unknown_id(tmp_path):
    store = ResearchStore(tmp_path / "research.db")
    assert store.get_report("does-not-exist") is None
    store.close()


def test_latest_report_for_symbol_returns_the_most_recent(tmp_path):
    store = ResearchStore(tmp_path / "research.db")
    older = _report(report_id="report-old", as_of=datetime(2024, 1, 1, tzinfo=timezone.utc))
    newer = _report(report_id="report-new", as_of=datetime(2024, 6, 1, tzinfo=timezone.utc))
    store.save_report(older)
    store.save_report(newer)

    assert store.latest_report_for_symbol("AAPL").report_id == "report-new"
    store.close()


def test_latest_report_for_symbol_is_scoped_per_symbol(tmp_path):
    store = ResearchStore(tmp_path / "research.db")
    store.save_report(_report(report_id="aapl-1", symbol="AAPL", as_of=datetime(2024, 6, 1, tzinfo=timezone.utc)))
    store.save_report(_report(report_id="msft-1", symbol="MSFT", as_of=datetime(2024, 6, 2, tzinfo=timezone.utc)))

    assert store.latest_report_for_symbol("AAPL").report_id == "aapl-1"
    assert store.latest_report_for_symbol("msft").report_id == "msft-1"
    store.close()


def test_list_reports_for_symbol_orders_newest_first_and_respects_limit(tmp_path):
    store = ResearchStore(tmp_path / "research.db")
    for i in range(5):
        store.save_report(_report(report_id=f"report-{i}", as_of=datetime(2024, 1, 1 + i, tzinfo=timezone.utc)))

    reports = store.list_reports_for_symbol("AAPL", limit=3)
    assert [r.report_id for r in reports] == ["report-4", "report-3", "report-2"]
    store.close()


def test_store_persists_across_reconnect(tmp_path):
    db_path = tmp_path / "research.db"
    store = ResearchStore(db_path)
    store.save_report(_report())
    store.close()

    reopened = ResearchStore(db_path)
    assert reopened.get_report("report-1") is not None
    reopened.close()
