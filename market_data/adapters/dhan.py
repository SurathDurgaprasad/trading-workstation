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


DEFAULT_DHAN_SNAPSHOT_WARMUP_SECONDS = 6.0
"""LIVE SYSTEM HARDENING mission finding, root-caused with three separate
real, live reproductions against the real Dhan feed (not guessed):

1. A real `shadow-run --live-source dhan` reported 0/3 live overlays
   succeeded. Instrumented reproduction showed the FIRST symbol's
   `get_snapshot()` call returned `DISCONNECTED` in ~0.03s -- the real
   WebSocket handshake is asynchronous and had not completed yet, and
   the original code had NO wait at all for this case. This 6s default
   fixes exactly that sub-case: a real re-run this same session showed
   the first (previously-failing) symbol succeed silently. This is a
   genuine, verified fix, not a guess.

2. A SECOND, deeper real finding, honestly disclosed rather than
   papered over: `next_bar()`'s public interface only ever surfaces a
   COMPLETED candle (one per `interval` -- 60s for "1m" -- per symbol),
   never a raw tick. `CandleBuilder` tracks a raw last-known-price
   internally on every tick (`_last_known_price`), but nothing public
   exposes it. This means a freshly-subscribed symbol's FIRST snapshot
   is only available once its FIRST bucket completes -- empirically
   confirmed uniformly distributed up to a full 60s (real observed
   waits: 15.3s, 30.6s, and up to the full budget), not a fixed short
   delay. **6s therefore reliably fixes sub-case 1 (the connection
   race) but CANNOT and does not claim to guarantee sub-case 2 (a
   symbol subscribed less than one full interval ago may legitimately
   have no live quote yet)** -- raising this default to a value that
   WOULD guarantee sub-case 2 (>=60s per symbol) would make a
   multi-symbol scan impractically slow, trading a rare, honest
   NO_DATA/DISCONNECTED result (which the code already handles by
   falling back to Yahoo -- never a crash, never fabricated data) for
   an unacceptable latency cost. A proper fix for sub-case 2 -- exposing
   the raw last-tick price through a new, EXPLICITLY-labeled data shape
   distinct from a completed candle -- is a real architecture
   recommendation, deliberately NOT implemented under this mission's
   own time pressure: rushing it risks exactly the "fake real-time by
   dressing up a single tick as a candle" mistake this same mission
   explicitly warns against. See docs/LIVE_SYSTEM_HARDENING_REPORT.md."""


def build_dhan_adapter(
    *,
    credentials: DhanCredentials,
    instrument_map: DhanInstrumentMap,
    interval: str,
    warmup_seconds: float = DEFAULT_DHAN_SNAPSHOT_WARMUP_SECONDS,
    warmup_poll_seconds: float = 0.25,
    **source_kwargs,
) -> StreamingSnapshotAdapter:
    """`source_kwargs` passes through to DhanMarketDataSource unchanged
    (e.g. max_reconnect_attempts, next_bar_timeout_seconds) -- this
    function does not second-guess or override any of Phase 16/17's
    connection-safety defaults. `warmup_seconds`/`warmup_poll_seconds`
    are new (LIVE SYSTEM HARDENING mission) and go to
    StreamingSnapshotAdapter instead -- see
    DEFAULT_DHAN_SNAPSHOT_WARMUP_SECONDS's own docstring and
    StreamingSnapshotAdapter.warmup_seconds's own docstring for why a
    real, bounded wait on a symbol's OWN first snapshot call is needed,
    and for the honestly-disclosed limit of what it can and cannot
    guarantee."""
    source = DhanMarketDataSource(credentials=credentials, instrument_map=instrument_map, interval=interval, **source_kwargs)
    return StreamingSnapshotAdapter(source, interval=interval, warmup_seconds=warmup_seconds, warmup_poll_seconds=warmup_poll_seconds)
