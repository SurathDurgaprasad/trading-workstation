import json

import pandas as pd
import pytest

from backtesting.cache import CachedMarketDataProvider
from market.data_provider import OHLCV


class _CountingProvider:
    def __init__(self, ohlcv: OHLCV):
        self._ohlcv = ohlcv
        self.calls = 0

    def fetch_ohlcv(self, symbol, *, period="1y", interval="1d"):
        self.calls += 1
        return self._ohlcv


def _sample_ohlcv(symbol="TEST") -> OHLCV:
    frame = pd.DataFrame(
        {
            "Open": [100.0, 101.0, 102.0],
            "High": [101.0, 102.0, 103.0],
            "Low": [99.0, 100.0, 101.0],
            "Close": [100.5, 101.5, 102.5],
            "Volume": [1_000_000.0, 1_100_000.0, 1_200_000.0],
        },
        index=pd.date_range("2026-01-01", periods=3, freq="D", name="Date"),
    )
    return OHLCV.from_dataframe(symbol=symbol, interval="1d", frame=frame)


def test_second_fetch_is_served_from_cache_not_the_underlying_provider(tmp_path):
    inner = _CountingProvider(_sample_ohlcv())
    cached = CachedMarketDataProvider(inner, cache_root=tmp_path)

    first = cached.fetch_ohlcv("TEST", period="1y", interval="1d")
    second = cached.fetch_ohlcv("TEST", period="1y", interval="1d")

    assert inner.calls == 1  # only the first call hit the "network"
    assert len(first.bars) == len(second.bars) == 3


def test_cached_round_trip_preserves_ohlcv_values(tmp_path):
    original = _sample_ohlcv()
    inner = _CountingProvider(original)
    cached = CachedMarketDataProvider(inner, cache_root=tmp_path)

    cached.fetch_ohlcv("TEST", interval="1d")  # writes the cache
    reloaded = cached.fetch_ohlcv("TEST", interval="1d")  # reads it back

    assert [b.close for b in reloaded.bars] == [b.close for b in original.bars]
    assert [b.timestamp for b in reloaded.bars] == [b.timestamp for b in original.bars]


def test_cache_writes_a_metadata_sidecar(tmp_path):
    inner = _CountingProvider(_sample_ohlcv())
    cached = CachedMarketDataProvider(inner, cache_root=tmp_path)

    cached.fetch_ohlcv("TEST", period="2y", interval="1d")

    meta_path = tmp_path / "TEST" / "1d.meta.json"
    assert meta_path.exists()
    meta = json.loads(meta_path.read_text())
    assert meta["symbol"] == "TEST"
    assert meta["interval"] == "1d"
    assert meta["period"] == "2y"
    assert meta["bar_count"] == 3
    assert "retrieved_at" in meta


def test_symbols_are_cached_independently(tmp_path):
    inner_a = _CountingProvider(_sample_ohlcv("AAA"))
    inner_b = _CountingProvider(_sample_ohlcv("BBB"))
    cache_a = CachedMarketDataProvider(inner_a, cache_root=tmp_path)
    cache_b = CachedMarketDataProvider(inner_b, cache_root=tmp_path)

    cache_a.fetch_ohlcv("AAA", interval="1d")
    cache_b.fetch_ohlcv("BBB", interval="1d")

    assert inner_a.calls == 1
    assert inner_b.calls == 1
    assert (tmp_path / "AAA" / "1d.csv").exists()
    assert (tmp_path / "BBB" / "1d.csv").exists()
