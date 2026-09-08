import sqlite3
from datetime import datetime, timezone

import pytest

from market_intelligence.regime import BenchmarkContext, IndiaVixContext, MarketBreadth, MarketRegimeReport, SectorStrength
from market_intelligence.regime_store import MarketRegimeStore


def _report(scan_id: str = "scan-1", as_of: datetime | None = None, *, with_sector_and_vix: bool = True) -> MarketRegimeReport:
    as_of = as_of or datetime(2024, 6, 1, tzinfo=timezone.utc)
    return MarketRegimeReport(
        as_of=as_of,
        scan_id=scan_id,
        breadth=MarketBreadth(advancing=5, declining=3, flat=2, total_scored=10, advance_decline_ratio=1.6666666666666667),
        benchmark=BenchmarkContext(
            symbol="^NSEI", trend_regime="UPTREND", volatility_regime="NORMAL",
            last_close=25000.0, atr_pct_of_price=1.2, atr_pct_vs_trailing_average=1.05,
        ),
        sector_strength=(SectorStrength(sector="IT", symbol_count=5, average_composite_score=0.3),),
        sector_index_regimes=(
            {
                "NIFTY_BANK": BenchmarkContext(
                    symbol="^NSEBANK", trend_regime="DOWNTREND", volatility_regime="HIGH_VOLATILITY",
                    last_close=50000.0, atr_pct_of_price=1.5, atr_pct_vs_trailing_average=1.3,
                )
            }
            if with_sector_and_vix else {}
        ),
        india_vix=(
            IndiaVixContext(symbol="^INDIAVIX", last_value=13.5, trailing_average=12.0, ratio_vs_trailing_average=1.125, regime="NORMAL")
            if with_sector_and_vix else None
        ),
    )


def test_save_and_get_round_trips_every_nested_field(tmp_path):
    store = MarketRegimeStore(tmp_path / "regime.db")
    report = _report()
    store.save_report(report)

    fetched = store.get_report(report.scan_id)
    assert fetched == report
    store.close()


def test_save_and_get_round_trips_with_empty_sector_and_vix(tmp_path):
    """sector_index_regimes={} / india_vix=None is the default, non-opted-in
    shape most existing callers of build_market_regime_report still
    produce -- must round-trip just as cleanly as the fully-populated case."""
    store = MarketRegimeStore(tmp_path / "regime.db")
    report = _report(with_sector_and_vix=False)
    store.save_report(report)

    fetched = store.get_report(report.scan_id)
    assert fetched == report
    assert fetched.sector_index_regimes == {}
    assert fetched.india_vix is None
    store.close()


def test_get_report_returns_none_for_unknown_id(tmp_path):
    store = MarketRegimeStore(tmp_path / "regime.db")
    assert store.get_report("does-not-exist") is None
    store.close()


def test_latest_report_returns_the_most_recent_by_as_of(tmp_path):
    store = MarketRegimeStore(tmp_path / "regime.db")
    older = _report(scan_id="scan-old", as_of=datetime(2024, 1, 1, tzinfo=timezone.utc))
    newer = _report(scan_id="scan-new", as_of=datetime(2024, 6, 1, tzinfo=timezone.utc))
    store.save_report(older)
    store.save_report(newer)

    assert store.latest_report().scan_id == "scan-new"
    store.close()


def test_list_reports_orders_newest_first_and_respects_limit(tmp_path):
    store = MarketRegimeStore(tmp_path / "regime.db")
    for i in range(5):
        store.save_report(_report(scan_id=f"scan-{i}", as_of=datetime(2024, 1, 1 + i, tzinfo=timezone.utc)))

    reports = store.list_reports(limit=3)
    assert [r.scan_id for r in reports] == ["scan-4", "scan-3", "scan-2"]
    store.close()


def test_store_persists_across_reconnect(tmp_path):
    db_path = tmp_path / "regime.db"
    store = MarketRegimeStore(db_path)
    store.save_report(_report())
    store.close()

    reopened = MarketRegimeStore(db_path)
    assert reopened.get_report("scan-1") is not None
    reopened.close()


def test_save_report_is_write_once_duplicate_scan_id_raises(tmp_path):
    store = MarketRegimeStore(tmp_path / "regime.db")
    store.save_report(_report(scan_id="scan-1"))
    with pytest.raises(sqlite3.IntegrityError):
        store.save_report(_report(scan_id="scan-1"))
    store.close()
