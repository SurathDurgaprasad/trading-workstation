import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

from backtesting.cache import CachedMarketDataProvider, report_cache_staleness
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


# --- report_cache_staleness ---------------------------------------------


def test_staleness_report_reflects_a_real_cached_entrys_actual_age(tmp_path):
    inner = _CountingProvider(_sample_ohlcv("TEST"))
    cached = CachedMarketDataProvider(inner, cache_root=tmp_path)
    cached.fetch_ohlcv("TEST", interval="1d")

    records = report_cache_staleness(["TEST"], interval="1d", cache_root=tmp_path)

    assert len(records) == 1
    record = records[0]
    assert record.symbol == "TEST"
    assert record.retrieved_at is not None
    assert record.data_end is not None
    assert record.age_days is not None
    assert 0 <= record.age_days < 0.01  # just written, should be seconds old


def test_staleness_report_backdates_correctly_for_an_older_entry(tmp_path):
    inner = _CountingProvider(_sample_ohlcv("TEST"))
    cached = CachedMarketDataProvider(inner, cache_root=tmp_path)
    cached.fetch_ohlcv("TEST", interval="1d")

    # Rewrite the meta.json's retrieved_at to simulate a cache entry
    # fetched 45 days ago -- the report must reflect that real age, not
    # "just now".
    meta_path = tmp_path / "TEST" / "1d.meta.json"
    meta = json.loads(meta_path.read_text())
    meta["retrieved_at"] = (datetime.now(timezone.utc) - timedelta(days=45)).isoformat()
    meta_path.write_text(json.dumps(meta))

    records = report_cache_staleness(["TEST"], interval="1d", cache_root=tmp_path)

    assert records[0].age_days == pytest.approx(45.0, abs=0.01)


def test_staleness_report_returns_none_fields_for_a_symbol_never_cached():
    records = report_cache_staleness(["NEVER_FETCHED"], interval="1d", cache_root=Path("/nonexistent-cache-root"))

    assert len(records) == 1
    record = records[0]
    assert record.symbol == "NEVER_FETCHED"
    assert record.retrieved_at is None
    assert record.data_end is None
    assert record.age_days is None


def test_staleness_report_returns_one_record_per_symbol_in_the_same_order(tmp_path):
    inner = _CountingProvider(_sample_ohlcv("AAA"))
    cached = CachedMarketDataProvider(inner, cache_root=tmp_path)
    cached.fetch_ohlcv("AAA", interval="1d")

    records = report_cache_staleness(["AAA", "NEVER_FETCHED", "AAA"], interval="1d", cache_root=tmp_path)

    assert [r.symbol for r in records] == ["AAA", "NEVER_FETCHED", "AAA"]
    assert records[0].retrieved_at is not None
    assert records[1].retrieved_at is None
    assert records[2].retrieved_at is not None


def test_staleness_report_handles_malformed_meta_json_without_crashing(tmp_path):
    inner = _CountingProvider(_sample_ohlcv("TEST"))
    cached = CachedMarketDataProvider(inner, cache_root=tmp_path)
    cached.fetch_ohlcv("TEST", interval="1d")

    meta_path = tmp_path / "TEST" / "1d.meta.json"
    meta_path.write_text("{not valid json")

    records = report_cache_staleness(["TEST"], interval="1d", cache_root=tmp_path)

    assert records[0].retrieved_at is None
    assert records[0].age_days is None


# --- path-traversal protection (Phase 17, security review) ---------------


@pytest.mark.parametrize(
    "malicious_symbol",
    [
        "../../../etc/passwd",
        "..\\..\\..\\Windows\\Temp\\evil",
        "..",
        "...",
        "FOO/../../BAR",
        "FOO/BAR",
        "FOO\\BAR",
        "",
    ],
)
def test_fetch_ohlcv_rejects_a_path_unsafe_symbol(tmp_path, malicious_symbol):
    # Real, exploitable gap found by a security audit: a crafted symbol
    # (e.g. from a shared/downloaded watchlist YAML) previously joined
    # straight into a filesystem path with no validation beyond
    # strip()/upper(), letting it escape data/market/ entirely.
    inner = _CountingProvider(_sample_ohlcv("TEST"))
    cached = CachedMarketDataProvider(inner, cache_root=tmp_path)

    with pytest.raises(ValueError):
        cached.fetch_ohlcv(malicious_symbol, interval="1d")

    assert inner.calls == 0  # never even reached the underlying provider


@pytest.mark.parametrize("malicious_symbol", ["../../../etc/passwd", "..", "FOO/BAR"])
def test_report_cache_staleness_rejects_a_path_unsafe_symbol(tmp_path, malicious_symbol):
    with pytest.raises(ValueError):
        report_cache_staleness([malicious_symbol], interval="1d", cache_root=tmp_path)


def test_a_malicious_symbol_never_actually_escapes_the_cache_root(tmp_path):
    # Belt-and-suspenders: even if the ValueError guard were ever
    # bypassed, confirm no file actually lands outside cache_root for a
    # realistic attack payload, by checking the directory tree stays empty.
    inner = _CountingProvider(_sample_ohlcv("TEST"))
    cached = CachedMarketDataProvider(inner, cache_root=tmp_path)

    with pytest.raises(ValueError):
        cached.fetch_ohlcv("../outside", interval="1d")

    assert not (tmp_path.parent / "outside").exists()
    assert list(tmp_path.iterdir()) == [] if tmp_path.exists() else True


@pytest.mark.parametrize("legitimate_symbol", ["AAPL", "RELIANCE.NS", "^NSEI", "BRK-B", "TATASTEEL.NS"])
def test_legitimate_real_world_symbols_are_never_rejected(tmp_path, legitimate_symbol):
    inner = _CountingProvider(_sample_ohlcv(legitimate_symbol))
    cached = CachedMarketDataProvider(inner, cache_root=tmp_path)

    result = cached.fetch_ohlcv(legitimate_symbol, interval="1d")

    assert result.symbol == legitimate_symbol
    assert inner.calls == 1
