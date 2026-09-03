from datetime import datetime, timezone

from market.data_provider import DataSource, DataStatus, OHLCVBar
from market_data.models import InstrumentSnapshot, MarketSnapshot
from market_data.quality import SourceHealth


def _bar() -> OHLCVBar:
    return OHLCVBar(
        timestamp=datetime(2026, 9, 3, 10, 0), open=100.0, high=101.0, low=99.5, close=100.5, volume=1000.0,
        source=DataSource.DHAN, status=DataStatus.LIVE,
    )


def test_instrument_snapshot_wraps_an_existing_ohlcv_bar_unchanged():
    """InstrumentSnapshot must not re-derive OHLC fields -- it holds the
    SAME OHLCVBar instance this project already produces."""
    bar = _bar()
    snapshot = InstrumentSnapshot(symbol="RELIANCE.NS", latest_bar=bar, health=SourceHealth.no_data(), as_of=datetime.now(timezone.utc))
    assert snapshot.latest_bar is bar
    assert snapshot.latest_bar.source == DataSource.DHAN
    assert snapshot.latest_bar.status == DataStatus.LIVE


def test_instrument_snapshot_allows_no_bar_yet():
    snapshot = InstrumentSnapshot(symbol="RELIANCE.NS", latest_bar=None, health=SourceHealth.no_data(), as_of=datetime.now(timezone.utc))
    assert snapshot.latest_bar is None
    assert snapshot.health.status.value == "NO_DATA"


def test_market_snapshot_get_and_len():
    now = datetime.now(timezone.utc)
    a = InstrumentSnapshot(symbol="A", latest_bar=None, health=SourceHealth.no_data(), as_of=now)
    b = InstrumentSnapshot(symbol="B", latest_bar=_bar(), health=SourceHealth.no_data(), as_of=now)
    snapshot = MarketSnapshot(instruments={"A": a, "B": b}, as_of=now)

    assert len(snapshot) == 2
    assert snapshot.get("A") is a
    assert snapshot.get("MISSING") is None


def test_market_snapshot_never_silently_omits_a_symbol_with_no_data():
    """A symbol the caller asked to track, but for which nothing has ever
    been fetched, must still appear in the snapshot -- with an explicit
    no_data health, not be dropped."""
    now = datetime.now(timezone.utc)
    no_data_snapshot = InstrumentSnapshot(symbol="NEVERFETCHED", latest_bar=None, health=SourceHealth.no_data(), as_of=now)
    snapshot = MarketSnapshot(instruments={"NEVERFETCHED": no_data_snapshot}, as_of=now)

    assert "NEVERFETCHED" in snapshot.instruments
    assert snapshot.get("NEVERFETCHED").latest_bar is None
