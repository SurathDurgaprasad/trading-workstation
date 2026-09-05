# Data Source Architecture Review

Strategy science mission, Phase 12. Distinct from Phase 11 (which audited
whether data-source *labels* are honest); this phase reviews the
*architecture* itself — provider abstraction, caching, and failover — for
soundness and single points of failure. Source of truth is always the code,
not this document.

## 1. Provider abstraction

`market/data_provider.py` defines a clean `MarketDataProvider` protocol
(`fetch_ohlcv(symbol, *, period, interval) -> OHLCV`) with exactly one
concrete implementation reachable via `get_market_data_provider()`:
`YahooFinanceProvider`. `MarketDataProviderName` is an enum with a single
member (`YAHOO`); `get_market_data_provider()` raises `ValueError` for
anything else — there is no silent fallback to a different provider if
Yahoo Finance fails.

**Finding**: the entire historical-OHLCV pipeline (backtesting, paper
trading, walk-forward validation, every experiment this session ran) is a
**single point of failure on Yahoo Finance's API**. This is not
dishonest — Yahoo Finance genuinely does aggregate real NSE/BSE data (the
"RELIANCE.NS"-style symbols this session used throughout are real,
Yahoo-sourced NSE data, not synthetic) — but if Yahoo's API changes shape,
rate-limits aggressively, or becomes unavailable, there is no second
historical-data provider to fall back to. This is architecturally distinct
from the LIVE path (`live/dhan/`), which is a genuine second, independent
data source — but that path only serves live streaming ticks, not
historical OHLCV for backtesting. Building a second historical provider
(e.g. a real Dhan historical-candle REST client) is a real, non-trivial
undertaking and is explicitly **not** attempted in this phase — flagging
the gap honestly is the deliverable, not a speculative implementation.

## 2. Caching architecture

`backtesting/cache.py`'s `CachedMarketDataProvider` wraps any
`MarketDataProvider` with a local CSV cache (`data/market/<SYMBOL>/
<interval>.csv` + a `.meta.json` sidecar). Its own docstring already states
the key limitation plainly: **"On a cache hit, the cached range is served
as-is regardless of the requested `period` — there is no freshness/
invalidation logic here."** The sidecar records `retrieved_at`, but nothing
in the codebase read that value back before this phase — it was write-only
metadata.

**Concretely, how stale is this session's own real data?** Checked against
the actual cache: `RELIANCE.NS` and `AAPL` were both retrieved
2026-08-25, ~11 days before this document was written (2026-09-05) — recent,
not alarmingly stale, but every "real 41-symbol universe" result this
session reported reflects data as of 2026-08-25, not the current date. This
matters for interpreting every dev/val/oos split, walk-forward fold, and
Monte Carlo result in this session's own work honestly: they are all
computed against one fixed historical snapshot, not a continuously
refreshed dataset.

**Added this phase**: `backtesting/cache.py`'s `report_cache_staleness()`
is a read-only diagnostic that reads each symbol's `retrieved_at`/`end`
metadata and reports its age — it does **not** change caching behavior (a
cache hit is still served as-is, unchanged); it only makes the
already-documented limitation visible instead of requiring someone to
manually open `.meta.json` files. Wired into a new CLI command,
`cache-status` (`--symbols`, `--interval`, `--stale-after-days`, default
threshold 30 days), which lists every cached symbol's age and flags any
past the threshold. 9 new tests in `tests/test_backtest_cache.py` cover a
real cache entry's age, a backdated (simulated 45-day-old) entry, a
never-cached symbol (reports `None` fields honestly, never a fabricated
age), ordering, and malformed `meta.json` handled without crashing.

Real output against this session's own cache (`cache-status --symbols
RELIANCE.NS,AAPL`, run 2026-09-05): both symbols ~11 days old, 0 flagged
stale at the default 30-day threshold.

## 3. Failover behavior — not architected, and not claimed to be

There is no retry/circuit-breaker logic in `YahooFinanceProvider.fetch_ohlcv`
— a transient failure raises `MarketDataError` immediately, once, with no
automatic retry. For the LIVE path, `market/context.py`'s
`_apply_live_overlay` already handles this gracefully by falling back to
the last-known historical label rather than raising or fabricating a value
(see Phase 11's audit) — but that is specific to the live-overlay code
path, not a general retry/backoff mechanism for the historical fetch path
itself. This is a reasonable, honest scope for a personal research
system — building production-grade retry/circuit-breaker infrastructure
for a single-user, paper-trading tool is not attempted here, and nothing in
the codebase claims this capability exists.

## Summary

| Concern | Finding | Action this phase |
|---|---|---|
| Provider abstraction | Clean protocol, but exactly one real implementation (Yahoo) — single point of failure for all historical data | Documented, not built (out of scope) |
| Cache staleness | No invalidation logic (already self-documented); `retrieved_at` was write-only | Closed: `report_cache_staleness()` + `cache-status` CLI command, 9 tests |
| Failover/retry | None exists; none is claimed | Documented, not built (reasonable scope for this project) |
