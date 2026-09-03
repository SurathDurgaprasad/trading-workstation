from datetime import datetime, timedelta, timezone

import pytest

from market.context import MarketContext, get_market_context
from market.data_provider import OHLCV, DataSource, DataStatus, MarketDataError, OHLCVBar
from market.indicators import MACDValues, TechnicalIndicators, VolumeAnalysis
from market_data.models import InstrumentSnapshot
from market_data.quality import SourceHealth


def test_market_context_from_indicators_maps_all_fields():
    indicators = TechnicalIndicators(
        symbol="AAPL",
        as_of=datetime(2026, 8, 24),
        close=310.34,
        sma_20=313.01,
        sma_50=310.50,
        rsi_14=48.23,
        macd=MACDValues(macd=-1.49, signal=-1.25, histogram=-0.23),
        atr_14=6.04,
        volume=VolumeAnalysis(
            current_volume=1_000_000,
            volume_sma_20=1_500_000,
            volume_ratio=0.66,
            trend="decreasing",
        ),
    )

    context = MarketContext.from_indicators(indicators)

    assert context.symbol == "AAPL"
    assert context.price == 310.34
    assert context.macd == -1.49
    assert context.macd_signal == -1.25
    assert context.macd_histogram == -0.23
    assert context.volume_ratio == 0.66
    assert context.volume_trend == "decreasing"


def test_market_context_from_indicators_handles_missing_macd_and_volume():
    indicators = TechnicalIndicators(
        symbol="THIN",
        as_of=datetime(2026, 8, 24),
        close=10.0,
        sma_20=None,
        sma_50=None,
        rsi_14=None,
        macd=None,
        atr_14=None,
        volume=None,
    )

    context = MarketContext.from_indicators(indicators)

    assert context.macd is None
    assert context.macd_signal is None
    assert context.volume_trend is None


def test_market_context_is_frozen():
    context = MarketContext(symbol="AAPL", as_of=datetime(2026, 8, 24), price=1.0)
    try:
        context.price = 2.0
        assert False, "MarketContext should be immutable"
    except Exception:
        pass


def test_to_prompt_lines_renders_unknown_for_missing_values():
    context = MarketContext(symbol="THIN", as_of=datetime(2026, 8, 24), price=10.0)
    lines = context.to_prompt_lines()

    joined = "\n".join(lines)
    assert "UNKNOWN" in joined
    assert "THIN" in joined
    # A real number must never render as UNKNOWN.
    assert "Price: 10.00" in joined


def test_to_prompt_lines_never_hallucinates_missing_as_a_number():
    context = MarketContext(symbol="THIN", as_of=datetime(2026, 8, 24), price=10.0)
    rsi_line = next(line for line in context.to_prompt_lines() if line.startswith("RSI14"))
    assert rsi_line == "RSI14: UNKNOWN"


# --- Phase 31: multi-source composition ------------------------------------------


def _bars(n: int = 60, start: float = 100.0, step: float = 1.0, **bar_kwargs) -> list[OHLCVBar]:
    return [
        OHLCVBar(
            timestamp=datetime(2026, 1, 1) + timedelta(days=i),
            open=start + step * i, high=(start + step * i) * 1.01, low=(start + step * i) * 0.99,
            close=start + step * i, volume=1_000_000.0, **bar_kwargs,
        )
        for i in range(n)
    ]


class _FakeProvider:
    def __init__(self, bars: list[OHLCVBar]):
        self._bars = bars

    def fetch_ohlcv(self, symbol, *, period="6mo", interval="1d"):
        return OHLCV(symbol=symbol, interval=interval, bars=self._bars)


class _FakeSnapshotAdapter:
    def __init__(self, snapshot: InstrumentSnapshot | None = None, *, raises: Exception | None = None):
        self._snapshot = snapshot
        self._raises = raises
        self.requested_symbols: list[str] = []

    def get_snapshot(self, symbol: str) -> InstrumentSnapshot:
        self.requested_symbols.append(symbol)
        if self._raises is not None:
            raise self._raises
        return self._snapshot

    def close(self) -> None:
        pass


@pytest.fixture(autouse=True)
def _fake_yahoo_provider(monkeypatch):
    import market.context as context_module

    fake = _FakeProvider(_bars())
    monkeypatch.setattr(context_module, "get_market_data_provider", lambda: fake)
    yield fake


def test_get_market_context_labels_source_and_status_from_the_historical_bar():
    context = get_market_context("AAPL")
    assert context.data_source == DataSource.YAHOO.value
    assert context.data_status == DataStatus.HISTORICAL.value
    assert context.data_freshness_seconds is None  # no live overlay requested


def test_get_market_context_with_no_live_provider_is_unaffected_by_the_new_parameter():
    """Default (no live_snapshot_provider) must behave exactly as before
    for every existing caller that never passes it."""
    context = get_market_context("AAPL")
    assert context.price == pytest.approx(_bars()[-1].close)


def test_get_market_context_applies_a_healthy_live_overlay():
    live_bar = OHLCVBar(
        timestamp=datetime.now(timezone.utc), open=500.0, high=505.0, low=499.0, close=501.5, volume=10_000.0,
        source=DataSource.DHAN, status=DataStatus.LIVE,
    )
    snapshot = InstrumentSnapshot(
        symbol="AAPL", latest_bar=live_bar,
        health=SourceHealth.from_bar_timestamp(bar_timestamp=live_bar.timestamp, interval="1m"),
        as_of=datetime.now(timezone.utc),
    )
    adapter = _FakeSnapshotAdapter(snapshot)

    context = get_market_context("AAPL", live_snapshot_provider=adapter)

    assert context.price == 501.5
    assert context.as_of == live_bar.timestamp
    assert context.data_source == DataSource.DHAN.value
    assert context.data_status == DataStatus.LIVE.value
    assert context.data_freshness_seconds is not None
    assert adapter.requested_symbols == ["AAPL"]
    # Indicators are still computed from the Yahoo historical series, not fabricated from the live overlay.
    assert context.sma_20 is not None


def test_get_market_context_ignores_a_stale_live_snapshot():
    from market_data.quality import SourceStatus

    stale_snapshot = InstrumentSnapshot(
        symbol="AAPL", latest_bar=None, health=SourceHealth(status=SourceStatus.STALE, last_updated=None, age_seconds=99999),
        as_of=datetime.now(timezone.utc),
    )
    adapter = _FakeSnapshotAdapter(stale_snapshot)

    context = get_market_context("AAPL", live_snapshot_provider=adapter)

    assert context.price == pytest.approx(_bars()[-1].close)  # fell back to Yahoo historical
    assert context.data_source == DataSource.YAHOO.value
    assert context.data_freshness_seconds is None


def test_get_market_context_ignores_a_disconnected_live_snapshot():
    disconnected = InstrumentSnapshot(symbol="AAPL", latest_bar=None, health=SourceHealth.disconnected("no connection"), as_of=datetime.now(timezone.utc))
    adapter = _FakeSnapshotAdapter(disconnected)

    context = get_market_context("AAPL", live_snapshot_provider=adapter)
    assert context.data_source == DataSource.YAHOO.value


def test_get_market_context_survives_a_live_provider_that_raises():
    """A broken live source must never break the historical fallback --
    decide/size/predict must still get a usable MarketContext."""
    adapter = _FakeSnapshotAdapter(raises=ConnectionError("Dhan unreachable"))

    context = get_market_context("AAPL", live_snapshot_provider=adapter)

    assert context.price == pytest.approx(_bars()[-1].close)
    assert context.data_source == DataSource.YAHOO.value


def test_get_market_context_live_overlay_never_raises_even_for_market_data_error():
    adapter = _FakeSnapshotAdapter(raises=MarketDataError("boom"))
    context = get_market_context("AAPL", live_snapshot_provider=adapter)
    assert context.data_source == DataSource.YAHOO.value


def test_to_prompt_lines_includes_data_source_status_and_freshness():
    context = MarketContext(
        symbol="AAPL", as_of=datetime(2026, 8, 24), price=10.0,
        data_source="DHAN", data_status="LIVE", data_freshness_seconds=2.3,
    )
    joined = "\n".join(context.to_prompt_lines())
    assert "Data Source: DHAN" in joined
    assert "Data Status: LIVE" in joined
    assert "Data Freshness (seconds): 2.3" in joined


def test_to_prompt_lines_data_source_renders_unknown_when_absent():
    context = MarketContext(symbol="THIN", as_of=datetime(2026, 8, 24), price=10.0)
    joined = "\n".join(context.to_prompt_lines())
    assert "Data Source: UNKNOWN" in joined
