import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from core.config import PROJECT_ROOT
from market.data_provider import OHLCV, MarketDataProvider

CACHE_ROOT = PROJECT_ROOT / "data" / "market"

_SYMBOL_PATH_SAFE_PATTERN = re.compile(r"^[A-Z0-9^._-]+$")


def _validate_symbol_for_path(symbol: str) -> str:
    """Strategy science Phase 17 (security review) -- a real, exploitable
    path-traversal gap found by the audit: a symbol string was joined
    directly into a filesystem path here (and in report_cache_staleness)
    with no validation beyond strip()/upper(). A crafted symbol (e.g.
    from a shared/downloaded watchlist YAML -- market_data.universe's own
    from_watchlist rejects commas/whitespace but not path separators)
    containing '/', '\\', or a bare '..' component could escape
    data/market/ entirely.

    An ALLOWLIST, not a blocklist: real market symbols this project
    actually uses (see data/market/'s own directory names) only ever
    contain uppercase letters, digits, '.' (exchange suffix, e.g.
    RELIANCE.NS), '^' (index prefix, e.g. ^NSEI), and '-' (share-class
    tickers). Blocklisting specific bad characters is fragile against a
    creative bypass this allowlist doesn't need to anticipate.

    A symbol made ENTIRELY of dots (e.g. '..', '...') would pass that
    character allowlist yet still act as a parent-directory navigation
    token when used as a single path component (no '/' needed -- '..'
    alone means "parent directory" to the OS) -- rejected explicitly."""
    if not _SYMBOL_PATH_SAFE_PATTERN.match(symbol) or set(symbol) == {"."}:
        raise ValueError(
            f"Refusing to use symbol {symbol!r} to construct a filesystem path -- contains characters outside "
            "the safe set [A-Z0-9^._-], or is a path-navigation token."
        )
    return symbol


class CachedMarketDataProvider:
    """Wraps a MarketDataProvider with a local CSV cache.

    CSV, not Parquet: no parquet engine (pyarrow/fastparquet) is installed in
    this venv, and the spec explicitly allows "Parquet/CSV... if the
    environment supports it cleanly" — CSV does, with zero new dependencies.

    Cache layout: data/market/<SYMBOL>/<interval>.csv + a sibling
    <interval>.meta.json (symbol, interval, period, start, end, retrieved_at).
    On a cache hit, the cached range is served as-is regardless of the
    requested `period` — there is no freshness/invalidation logic here (see
    the Phase 3 report's known limitations). Delete the file to refresh it.
    """

    def __init__(self, inner: MarketDataProvider, cache_root: Path = CACHE_ROOT):
        self._inner = inner
        self._cache_root = cache_root

    def fetch_ohlcv(self, symbol: str, *, period: str = "1y", interval: str = "1d") -> OHLCV:
        normalized_symbol = _validate_symbol_for_path(symbol.strip().upper())
        csv_path = self._csv_path(normalized_symbol, interval)

        if csv_path.exists():
            return self._read(csv_path, symbol=normalized_symbol, interval=interval)

        ohlcv = self._inner.fetch_ohlcv(normalized_symbol, period=period, interval=interval)
        self._write(csv_path, ohlcv, symbol=normalized_symbol, interval=interval, period=period)
        return ohlcv

    def _csv_path(self, symbol: str, interval: str) -> Path:
        return self._cache_root / symbol / f"{interval}.csv"

    def _meta_path(self, csv_path: Path) -> Path:
        return csv_path.with_suffix(".meta.json")

    def _read(self, csv_path: Path, *, symbol: str, interval: str) -> OHLCV:
        frame = pd.read_csv(csv_path, parse_dates=["Date"], index_col="Date")
        return OHLCV.from_dataframe(symbol=symbol, interval=interval, frame=frame)

    def _write(self, csv_path: Path, ohlcv: OHLCV, *, symbol: str, interval: str, period: str) -> None:
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        frame = ohlcv.to_dataframe()
        frame.to_csv(csv_path, index_label="Date")

        meta = {
            "symbol": symbol,
            "interval": interval,
            "period": period,
            "start": frame.index.min().isoformat() if not frame.empty else None,
            "end": frame.index.max().isoformat() if not frame.empty else None,
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "bar_count": len(frame),
        }
        self._meta_path(csv_path).write_text(json.dumps(meta, indent=2))


@dataclass(frozen=True)
class CacheStalenessRecord:
    """Strategy science Phase 12 (data source architecture review) --
    CachedMarketDataProvider's own docstring already admits "there is no
    freshness/invalidation logic here"; it WRITES retrieved_at into each
    symbol's meta.json but nothing ever READS it back to answer "how old
    is the data every backtest/experiment this session ran against."
    This is a read-only diagnostic over that already-persisted metadata
    -- it does not change caching behavior (still serves the cached range
    as-is on a hit, unchanged) -- so a user or a future session can see
    cache age at a glance instead of manually opening meta.json files."""

    symbol: str
    interval: str
    retrieved_at: datetime | None
    """None if the meta.json file is missing or unreadable -- never
    fabricated as "now" or any other assumed value."""
    data_end: datetime | None
    """The last bar's own timestamp, from meta.json's "end" field --
    None under the same conditions as retrieved_at."""
    age_days: float | None
    """Wall-clock days since retrieved_at, computed against the moment
    this report was generated. None when retrieved_at is None."""


def report_cache_staleness(
    symbols: list[str], *, interval: str = "1d", cache_root: Path = CACHE_ROOT,
) -> list[CacheStalenessRecord]:
    """One record per requested symbol, in the SAME order given -- a
    symbol with no cache entry at all (never fetched, or the file was
    deleted) gets a record with every field None rather than being
    silently skipped, so a caller always gets exactly len(symbols)
    records back."""
    now = datetime.now(timezone.utc)
    records = []
    for symbol in symbols:
        normalized = _validate_symbol_for_path(symbol.strip().upper())
        meta_path = (cache_root / normalized / f"{interval}.csv").with_suffix(".meta.json")

        retrieved_at = None
        data_end = None
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text())
                if meta.get("retrieved_at"):
                    retrieved_at = datetime.fromisoformat(meta["retrieved_at"])
                if meta.get("end"):
                    data_end = datetime.fromisoformat(meta["end"])
            except (json.JSONDecodeError, ValueError):
                pass  # malformed meta.json -- report as unknown (None), never a fabricated age

        age_days = (now - retrieved_at).total_seconds() / 86400 if retrieved_at is not None else None
        records.append(CacheStalenessRecord(symbol=normalized, interval=interval, retrieved_at=retrieved_at, data_end=data_end, age_days=age_days))

    return records
