import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from core.config import PROJECT_ROOT
from market.data_provider import OHLCV, MarketDataProvider

CACHE_ROOT = PROJECT_ROOT / "data" / "market"


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
        normalized_symbol = symbol.strip().upper()
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
