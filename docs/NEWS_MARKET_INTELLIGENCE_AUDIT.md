# News & Market Intelligence Architecture Audit

Strategy science mission, Phase 11. Answers one question honestly, with
code-level evidence: **does this codebase's news/market-intelligence layer
accurately represent what it actually does, or does it overclaim** (a
"LIVE" label on data that isn't actually live, an "NSE supported" claim
never verified against real NSE data, fabricated news presented as real)?

Source of truth is always the code and tests, not this document.

## Verdict

**No overclaiming found.** This is the rare case where an audit's main
output is confirmation rather than correction — every data-source label,
NSE/BSE claim, and news/AI-narration boundary I checked carries a caveat
proportionate to its actual evidence. One concrete gap was found and fixed
this phase (see below): a stale banner claim, not a fabrication.

## 1. Data source labeling — earned, not assumed

`market/data_provider.py`'s `DataStatus` enum documents its own rule:
`DhanMarketDataSource` is the *only* code path allowed to set
`status=LIVE`. That is enforced structurally, not just by convention:

- `live/dhan/candle_builder.py`'s `_finalize()` hardcodes `LIVE` only on a
  bar built from real ticks received over `DhanMarketDataSource`'s actual
  WebSocket connection to `api-feed.dhan.co` — which itself won't claim
  `CONNECTED` until the handshake genuinely completes (`on_open`-gated).
- `live/mock_source.py` hardcodes `source=MOCK, status=SIMULATED` — the
  mock feed can never produce a `LIVE` label, structurally.
- `live/state_store.py`'s `feed_status` table is written only from
  `bar.source`/`bar.status` as actually processed — "deliberately NOT
  fabricated from the dashboard side" (its own docstring).
- `market/context.py`'s `_apply_live_overlay` only overwrites a symbol's
  `data_status` when a live snapshot is genuinely `HEALTHY`; a failed or
  disconnected live source silently falls back to the prior historical
  label rather than being mislabeled LIVE.

Tests already prove this at multiple layers: `test_mock_market_data_source.py`
(mock is always SIMULATED), `test_dhan_candle_builder.py` /
`test_dhan_market_data_source.py` (real-path bars are LIVE),
`test_dashboard.py::test_index_shows_no_feed_data_when_nothing_processed_yet`
(absence is never silently filled with a fabricated default),
`test_market_context.py` (a stale/disconnected/raising live source never
gets mislabeled).

## 2. NSE/BSE support claims — backed by real evidence

`data/market/` holds real cached OHLCV (1d/1m/5m) for ~30 NSE symbols —
genuine data, not placeholders. `docs/MARKET_DATA_SOURCES.md` is a
rigorously evidence-graded capability matrix, distinguishing "REAL SERVICE
VERIFIED" from "synthetic-fixture-tested only," including an honest
correction of a previously-stale line and a note that the WebSocket
live-tick path specifically had not been exercised as of that document's
writing (REST/account reads had been). `market_data/universe.py` explicitly
refuses to claim NIFTY 50/100/500 index-membership accuracy it hasn't
verified. `backtesting/costs.py`'s `india_nse_intraday_2026()` calls itself
"a documented simplification... revisit before relying on this for real
P&L" — this caveat style is consistent everywhere else NSE is mentioned in
this codebase, not an isolated case.

## 3. News/research pipeline — real news, clearly separated from AI narration

`research/news.py`'s `YahooNewsProvider` fetches `yfinance`'s real
`Ticker.news` feed and drops malformed entries rather than inventing
placeholders. `research/summarizer.py`'s own LLM prompt explicitly
instructs: "Do not introduce any fact, price, event, or opinion that is not
present in this evidence... Do not recommend buying, selling, or holding."
`research/models.py` structurally separates the real `news`/`sector` fields
from `ai_summary` (with an honest `ai_summary_unavailable_reason` shown
when the LLM can't be reached, never a fabricated summary in its place),
and the dashboard renders them as visually distinct blocks — real evidence
first, "AI summary (narration only)" labeled separately underneath.

## 4. Scanner/news coupling — none found

`market_intelligence/scanner.py` is purely price/indicator-based
(SMA/RSI/MACD/ATR/volume/relative-strength) — no news or sentiment signal
anywhere in it. News enters the system only downstream, in `research/`,
and is never folded into the scanner's own candidate scoring.

## 5. Concrete gap found and fixed this phase

`dashboard/app.py`'s page-wide banner was a **hardcoded, unconditional
static string** — "SIMULATED PAPER TRADING — NOT connected to a live
broker or feed" — shown on every page regardless of actual feed state. When
a genuine `paper-live --source dhan` session has a real, verified WebSocket
connected, the banner and the feed-status table directly below it could
contradict each other (banner: "not connected"; table: `LIVE`/`DHAN`/
`CONNECTED`). The "No real order can ever be placed here" half of the claim
was always true (a structural guarantee — no order-placement code path
exists anywhere in this codebase) and stays unconditional; only the
connectivity half was stale.

**Fixed**: `dashboard/app.py`'s new `_broker_connectivity_banner()` reads
`live.workstation.get_feed_status()` (a local SQLite read, not a network
call — same "zero I/O to a live feed on page load" rule
`_market_status_banner()` already followed) and states the CURRENT truth:
"A LIVE broker feed IS connected" only when a feed-status row is genuinely
`status=LIVE` AND `connection_state=CONNECTED`; otherwise the original "NOT
connected" text, unchanged. 4 new tests in `tests/test_dashboard.py` cover
all four states: no feed data, a mock feed present, a genuinely connected
live Dhan feed, and a live-status row whose connection has since dropped
(proving `connection_state`, not just `status`, gates the claim) — plus
confirming "No real order can ever be placed here" is present in every case.
