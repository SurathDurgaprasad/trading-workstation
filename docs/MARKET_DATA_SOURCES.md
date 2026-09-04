# Market Data Source Capability Matrix

Audited directly against the code (not against prior reports) as part of the
autonomous continuous-validation mission's Section 8 requirement. Every row
below was verified by reading the actual class/function, not inferred from a
name.

## Capability matrix

| Component | Historical | Intraday | Live (streaming) | Provider | Local cache | Credential required |
|---|---|---|---|---|---|---|
| `market.data_provider.YahooFinanceProvider` | Yes | Yes (subject to Yahoo's own intraday history limits) | No | Yahoo Finance | No | No |
| `backtesting.cache.CachedMarketDataProvider` | Yes (wraps any provider) | Yes | No | Whatever it wraps (Yahoo in every current call site) | Yes — local file cache | Inherits wrapped provider |
| `market_data.resilience.ResilientMarketDataProvider` | Wraps any provider | Wraps any provider | Wraps any provider | Provider-agnostic — adds circuit breaker/retry-with-backoff/timeout, no data of its own | Inherits wrapped | Inherits wrapped |
| `market.context.get_market_context` | Yes (base price/ATR from Yahoo) | Yes | Optional — overlays a live Dhan quote on the Yahoo-derived context when `live_snapshot_provider` is supplied | Yahoo base, optional Dhan overlay | No | Only when `--live-source dhan` is used |
| `market_intelligence.scanner.run_scan` | Yes | N/A (scans on daily/configured-interval bars) | No | Whatever `MarketDataProvider` is passed (Yahoo by default, `--resilient` wraps it) | Depends on caller | No |
| `live.dhan.market_data_source.DhanMarketDataSource` | No | Yes (aggregates via `CandleBuilder`) | Yes — real Dhan WebSocket ticks | Dhan | No | **Yes** — `DHAN_CLIENT_ID`/`DHAN_ACCESS_TOKEN` |
| `live.dhan.rest_client.DhanRestClient` | No | N/A | Yes — on-demand REST (funds/positions/holdings) | Dhan | No | **Yes** |
| `live.dhan.instruments.DhanInstrumentMap` | N/A (metadata, not price) | N/A | N/A | Dhan's public instrument master | Yes — local CSV cache, `--refresh-instrument-map` forces re-download | No (public endpoint) |
| `research.news.YahooNewsProvider` | N/A (news, not price) | N/A | N/A | Yahoo Finance | No | No |
| `research.sector.YahooSectorInfoProvider` | N/A | N/A | N/A | Yahoo Finance | No | No |
| `live.mock_source.MockMarketDataSource` | Replays cached history | Simulated from cached history | No — synthetic, never real-time | None (replays `CachedMarketDataProvider`'s own cache) | Yes (reuses the cache above) | No |

## What this means in practice

- **Historical analysis, backtesting, scanning, and the default `size`/`predict`/`decide`/`shadow-run`/`schedule` paths are Yahoo-only.** This is deliberate, not an oversight: Yahoo is free, requires no credentials, and is adequate for the daily-bar-driven scanner/decision/prediction pipeline this project runs today.
- **Real-time intraday intelligence is Dhan-only, and opt-in.** `--live-source dhan` (on `size`/`predict`/`shadow-run`/`schedule`) or `--source dhan` (on `paper-live`) are the only ways real Dhan data enters the system. Every other invocation never touches Dhan at all.
- **No component silently substitutes one source for another.** `MarketContext.data_source`/`data_status` (Phase 31) are set explicitly and printed/persisted on every decision, so "was this live or historical" is always answerable from the record itself, never inferred.
- **Freshness is policed, not assumed.** `live.freshness.FreshnessPolicy` (threshold = 2x the bar interval, floored at 30s, both overridable) gates every tick `LiveSimPipeline` accepts — a stale or future-timestamped tick is rejected rather than silently used.
- **This environment has no Dhan credentials.** Every Dhan-dependent row above is structurally complete and tested with fakes, but **NOT VERIFIED against a real Dhan connection** in this session — stated honestly, not worked around.

## Non-goals reaffirmed by this audit

Blindly replacing Yahoo with Dhan everywhere was considered and rejected: Yahoo is the correct source for historical/backtesting/scanning (no credential dependency, adequate freshness for a daily-cadence pipeline), and Dhan is the correct source only where genuine real-time intraday awareness is needed and explicitly requested. The architecture already reflects this split; this audit found no component using the wrong source for its purpose.
