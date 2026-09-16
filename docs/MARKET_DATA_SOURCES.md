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
- **Reconciled (post-critic-system session): this environment DOES have real Dhan credentials** (`DHAN_CLIENT_ID`/`DHAN_ACCESS_TOKEN` in `.env`) — the prior "no Dhan credentials" line above was stale. What has actually been exercised, stated precisely rather than collapsed into one blanket claim:
  - **Real Dhan REST/account reads (`live.dhan.rest_client.DhanRestClient`, `live.dhan.broker_adapter.DhanAccountReader`) — REAL SERVICE VERIFIED.** Exercised directly against the live account earlier in this same continuous autonomous session.
  - **The Dhan WebSocket live-tick path (`live.dhan.market_data_source.DhanMarketDataSource`, i.e. `--live-source dhan` / `paper-live --source dhan`) — NOT exercised anywhere in this session.** Only unit/integration-tested with fakes here; do not read the REST validation above as covering this path too.
  - **Real Yahoo historical data — REAL SERVICE VERIFIED for the paper-execution/critic dashboard work this session** — `shadow-run --paper-execute` and the `/intelligence` dashboard's PAPER EXECUTION section were run against the real, accumulated ₹20,000 paper account (`data/paper_trading_20k.db`) using real Yahoo data, confirming honest "no new data yet" / correctly-rendered-live-state behavior with no fabrication.
  - The critic system (`critic/`) added this session is **synthetic-fixture-tested only** — no real-service or live-market validation of a critic verdict against a genuinely live decision has been performed yet (NSE market hours had already passed, 15:30 IST, before the critic work landed). Pending NSE reopening.

## Non-goals reaffirmed by this audit

Blindly replacing Yahoo with Dhan everywhere was considered and rejected: Yahoo is the correct source for historical/backtesting/scanning (no credential dependency, adequate freshness for a daily-cadence pipeline), and Dhan is the correct source only where genuine real-time intraday awareness is needed and explicitly requested. The architecture already reflects this split; this audit found no component using the wrong source for its purpose.

## Global/Indian macro & event intelligence audit (2026-09-16) — decision: DO NOT BUILD

A research report ([`docs/research/GEMINI_MARKET_INTELLIGENCE_SOURCE_MAP_2026-09-16.md`](research/GEMINI_MARKET_INTELLIGENCE_SOURCE_MAP_2026-09-16.md), Gemini) proposed a substantial global/Indian market-intelligence architecture: a normalized, versioned, timestamp-safe event ledger fed by Trading Economics, FRED/ALFRED, BLS, BEA, SEC EDGAR, ECB, BOJ, EIA, and scraped/RSS feeds from RBI/SEBI/PIB, with LLM-assisted extraction and a deduplication/reliability-scoring layer. Before writing any code, the report's claims were independently verified and weighed against this project's actual current state — not implemented against.

**Independently verified (web search / fetch, 2026-09-16):**
- **FRED API** — real, free (registered key, no cost), 120 req/min rate limit, matches the report's claim exactly. [fred.stlouisfed.org/docs/api/terms_of_use.html]
- **Trading Economics API** — real, Professional plan **$299/month billed yearly** confirmed via current third-party pricing pages (the provider's own pricing page requires a login to render). Matches the report's claim.
- **PIB RSS feed** — real, official, exists at `pib.gov.in/ViewRss.aspx`, public-domain government press releases, no authentication required.
- **SEBI robots.txt** — does not blanket-disallow crawling, but that is not the same as clearance for an automated/commercial polling pipeline; the report's own matrix independently flags SEBI/RBI scraping as **"SCRAPING RESTRICTED / UNKNOWN"** legally. Not contradicted by this check.
- **NIFTY sector indices + India VIX are ALREADY implemented**, contrary to an implicit assumption that this project has no Indian-market-context layer at all: `market_intelligence/regime.py` (`NIFTY_SECTOR_INDICES`, `compute_india_vix_context`, `compute_benchmark_context(include_nifty_sector_indices=..., include_india_vix=...)`) — real Yahoo Finance data, already tested. **Not wired into the live path's default call** (`live/critic_gate.py` calls `compute_benchmark_context` without these opt-in flags) and, independent of that, the regime check that DOES run is `WARNING` severity → `DOWNGRADE`, which is explicitly non-blocking (`critic/engine.py`'s `BLOCKING_VERDICTS = (REJECT, INSUFFICIENT_EVIDENCE)` never includes `DOWNGRADE`) — so even fully wired, it structurally cannot have altered a single trade decision to date.

**Decision: no new data source, provider, or event-ledger architecture was implemented.** Reasoning, against this project's own stated evidence bar (a proposed feature must show measurable incremental value before being forced into the trading model):

1. **The existing Indian-market-context layer (NIFTY sector + VIX) has never been exercised by a live decision** — the live fleet has produced zero candidates across every real session run to date (see `docs/LIVE_MARKET_VALIDATION_REPORT_2026-09-16.md`), so `CriticGate` has never once reached the point where this context would matter. Wiring in MORE global/macro context before the EXISTING, already-built context layer has been exercised even once by a real signal would be adding unmeasured complexity on top of unmeasured complexity — exactly the "architectural sprawl" this mission's own instructions warn against.
2. **Every proposed paid source is wildly disproportionate to this project's scale.** Trading Economics ($299/mo) and the NSE EOD Corporate Announcements SFTP feed (₹5,00,000/yr) are enterprise-grade costs for a single-user, local, paper-only research workstation whose entire LLM spend to date is a few dollars under an explicit, aggressively-enforced budget (`llm/budget.py`). No measurable expected value exists yet to justify either.
3. **The genuinely low-cost, low-risk option (PIB RSS)** is real and free, but building a normalized/versioned/deduplicated event ledger with point-in-time timestamp safety and LLM extraction — for a single free RSS feed, feeding a strategy that has never once reached the point of needing this context — is infrastructure without a justified consumer. If the existing NIFTY/VIX context is ever actually exercised by a live signal and shown to matter, PIB RSS is the natural, cheapest next step to revisit — not before.
4. **SEBI/RBI have no official API**; their own legal/ToS posture is ambiguous per both this audit's own check and the source report's own matrix. Not implemented.
5. **The frozen strategy (`trend_momentum_baseline v1.0`) remains unchanged**, per this project's own standing rule that a data/context addition must never be forced into the trading model without an out-of-sample experiment demonstrating incremental value — no such experiment was possible today (there is no live signal history to evaluate against), so none was fabricated.

**What this means concretely:** `market_intelligence/regime.py`'s NIFTY-sector/VIX capability remains exactly as it was — implemented, tested, available via opt-in flags, not defaulted into the live critic path. No new provider, no new dependency, no new event schema, no new scraper was added. This is a deliberate "do not build" conclusion, not an oversight — see [`FINAL_PRODUCT_CAPABILITY_MATRIX.md`](../FINAL_PRODUCT_CAPABILITY_MATRIX.md) for the full capability-by-capability status this audit reconfirmed rather than expanded.
