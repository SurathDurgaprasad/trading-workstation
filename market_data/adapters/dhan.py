"""Phase 18 -- constructs a market_data snapshot adapter around the
EXISTING, unmodified DhanMarketDataSource (live/dhan/market_data_source.py).
No changes to that module, or to any other file under live/dhan/ -- this
only wraps it. Constructing the adapter does not connect to Dhan; the
underlying DhanMarketDataSource only connects when its first symbol is
subscribed, which happens lazily on the first get_snapshot() call (see
market_data/adapters/_streaming.py).
"""

from live.dhan.config import DhanCredentials
from live.dhan.instruments import DhanInstrumentMap
from live.dhan.market_data_source import DhanMarketDataSource
from market_data.adapters._streaming import StreamingSnapshotAdapter


def build_dhan_adapter(
    *,
    credentials: DhanCredentials,
    instrument_map: DhanInstrumentMap,
    interval: str,
    **source_kwargs,
) -> StreamingSnapshotAdapter:
    """`source_kwargs` passes through to DhanMarketDataSource unchanged
    (e.g. max_reconnect_attempts, next_bar_timeout_seconds) -- this
    function does not second-guess or override any of Phase 16/17's
    connection-safety defaults."""
    source = DhanMarketDataSource(credentials=credentials, instrument_map=instrument_map, interval=interval, **source_kwargs)
    return StreamingSnapshotAdapter(source, interval=interval)
