# Phase 1 — Derivatives Research/Data Inventory

New research program (2026-09-21, continuing from `f9a3b99`): "Determine whether Indian equity/
index derivatives contain predictive information not already captured by the exhausted OHLCV-only
research." This phase audits what already exists — repo code (via a dedicated Explore agent) and
live external capability (via direct, verified API calls) — before building anything.

## 1–14: Answers to the mission's own numbered questions

**1. What NSE derivatives data is already available (in this repo)?** None, at the data-consumption
level. `quant_research/point_in_time_fno_universe.py` already downloads and parses real NSE F&O
bhavcopy files (both the "classic" and "UDiFF" formats), but extracts ONLY the `FUTSTK`/`STF` rows'
underlying symbol — every option-specific column (`STRIKE_PR`/`StrkPric`, `OPTION_TYP`/`OptnTp`,
`OPEN_INT`/`OpnIntrst`, `CONTRACTS`/`TtlTradgVol`, `SETTLE_PR`/`SttlmPric`, `UndrlygPric`) is already
read into the parsed `pandas.DataFrame` by `pd.read_csv` but never selected or used.

**2. What Dhan API capabilities are currently available (in this repo vs. at Dhan itself)?**
Currently exercised in this repo: **zero.** `live/dhan/rest_client.py` (`DhanRestClient`) exposes
exactly three read-only endpoints — `/fundlimit`, `/positions`, `/holdings` — no option-chain or
futures-quote REST call exists. The WebSocket wire-format parser (`live/dhan/wire.py`) CAN parse OI
(`DhanOpenInterestPacket`, packet code 5) and Full packets (which include `open_interest`), but the
live pipeline (`live/dhan/market_data_source.py:555`) only ever subscribes in **Quote mode**
(`SUBSCRIBE_QUOTE=17`) to the **equity segment** (`NSE_EQ`) — never `NSE_FNO`, never
`SUBSCRIBE_FULL`/`SUBSCRIBE_DEPTH`. This exact gap was already independently documented in
`TRADING_FEATURE_CATALOG.json:555-565` and `TRADING_INTELLIGENCE_GAP_ANALYSIS.md:261-265` (dated
2026-09-13).

**Available AT DHAN but not yet wrapped by this repo** (verified this session via real, live,
credentialed API calls — not read from docs alone): Dhan's official v2 API (`dhanhq.co/docs/v2/`)
has a **Data APIs** section with two capabilities this repo has never called:
- `POST /optionchain` + `/optionchain/expirylist` — real-time (current-only) full option chain:
  OI, Greeks (delta/theta/gamma/vega), IV, volume, top bid/ask, per strike, across all active
  expiries. Rate limit: 1 unique request per 3 seconds.
- `POST /charts/rollingoption` — **real historical minute-level options data**, up to 5 years back,
  for BOTH index (`OPTIDX`) and stock (`OPTSTK`) options, strike-relative to spot (`ATM`, `ATM±N`),
  returning `open/high/low/close/volume/oi/iv/strike/spot` at 1/5/15/25/60-minute resolution, up to
  30 days per call.
- `POST /charts/historical` (daily) and `POST /charts/intraday` (minute, 90-day cap per call) —
  the SAME general-purpose OHLC endpoints already used for equities also accept `instrument=
  FUTIDX/FUTSTK/OPTIDX/OPTSTK` and an `oi: true` flag, returning `open_interest` alongside OHLC.

**Empirically verified this session** (real API calls, real credentials already in `.env`, all
read-only Data-API calls):
- `/charts/rollingoption` for NIFTY (`securityId=13`, `OPTIDX`, ATM CALL, Sep 2025, hourly): HTTP 200,
  real IV (8-9%), real OI (100K-2M), real rolling ATM strikes (24500-24850 as spot moved), real spot
  series, real OHLC. **A real, previously-undocumented API quirk was caught empirically**:
  `expiryCode=0` (documented as valid, meaning "current/near expiry") is REJECTED by this specific
  endpoint (`DH-905 "expiryCode is required"`); `expiryCode=1` works. This quirk is specific to
  `/charts/rollingoption` — the general `/charts/historical` endpoint accepted `expiryCode=0` fine in
  a separate test call.
- `/charts/rollingoption` for RELIANCE (`securityId=2885`, `OPTSTK`, ATM PUT): HTTP 200, real IV
  (~19-21%), real OI — confirms stock-option coverage, not index-only.
  - `/charts/rollingoption` at ~4.5 years back (2021-06): HTTP 200, real data returned — the "up to 5
  years" depth claim is credible at least to that point (exact boundary not pinned further).
- `/charts/historical` (daily) for a real NIFTY futures contract (`securityId=68407`,
  `NIFTY-Sep2026-FUT`, `FUTIDX`, `oi=true`): HTTP 200, real nonzero open interest (16.0M-18.4M range).
- Timestamps verified genuine and exchange-local: epoch `1756698300` → `2025-09-01 09:15:00 IST` —
  exactly NSE's own market-open time, confirming real, correctly-aligned exchange-local bar
  boundaries (matching the existing equity pipeline's own convention).

**3. Historical derivatives data already cached?** None. `data/dhan/scrip-master.csv` is a CURRENT
-snapshot-only instrument master (confirmed multiple times this session across prior missions — zero
expired FUTSTK contracts). No `.db` file (38 checked) has any table with an option/future/OI/strike/
IV/Greek-related name.

**4. Yahoo/yfinance for derivatives — tested directly this session**: `yf.Ticker("RELIANCE.NS")
.options` returns an **empty tuple**. Confirmed: yfinance has no options-chain capability for NSE
-suffixed symbols at all (unlike US tickers, where `yfinance` options support is a known, if
sometimes flaky, capability). This was a genuinely untested question before this session — no prior
finding either way existed in the repo.

**5. Does the project already have options chains / options OHLC / options volume / open interest /
implied volatility / futures prices / futures OI / expiry information / strike information?** No,
none of these are exposed by any consuming code path today, though (per items 1-2 above) most of the
RAW material already flows through existing pipelines unused: the Dhan instrument master already
loads strike/option-type/expiry/lot-size columns into memory (`DhanInstrumentMap._frame`) but no
lookup method exposes them; the NSE bhavcopy parser already reads OI/volume/strike/option-type/
settlement columns into a DataFrame but discards them after FUTSTK/STF extraction.

**6. Historical date coverage per field**: see the inventory table below — varies materially by
source (NSE bhavcopy: full history, subject to the two-format transition already mapped in Phase A;
Dhan rolling-option: confirmed to at least ~4.5 years, documented as "up to 5 years"; Dhan intraday
general endpoint: also 5 years but only 90 days retrievable per call).

**7. Intraday vs. daily resolution**: both exist. NSE bhavcopy = daily/EOD only (one row per
contract per trading day — no intraday granularity at all in the archive format). Dhan
`/charts/rollingoption` and `/charts/intraday` = genuine intraday (1/5/15/25/60-minute bars). Dhan
`/charts/historical` = daily only.

**8. Symbol/contract identity**: NSE bhavcopy identifies a contract by (`SYMBOL`/`TckrSymb`,
`EXPIRY_DT`/`XpryDt`, `STRIKE_PR`/`StrkPric`, `OPTION_TYP`/`OptnTp`) — a genuine, unique, auditable
composite key, present in every row. Dhan's rolling-option endpoint identifies by (underlying
`securityId`, `instrument` type, `expiryFlag`/`expiryCode`, relative `strike` position) — NOT an
absolute strike; the actual resolved strike is returned IN the response (`strike` array), not chosen
by the caller. Dhan's instrument master has an explicit per-contract `SEM_SMST_SECURITY_ID` (a
genuine unique contract identifier) alongside `SEM_STRIKE_PRICE`/`SEM_OPTION_TYPE`/`SEM_EXPIRY_DATE`.

**9. Expiry representation**: NSE bhavcopy uses an explicit calendar date per row (`EXPIRY_DT`, e.g.
`30-Jun-2022`, or ISO `XpryDt` in UDiFF). Dhan's rolling-option endpoint uses a relative
`expiryFlag` (`WEEK`/`MONTH`) + `expiryCode` (0=current/near, 1=next, 2=far) — a rolling, not
absolute, expiry selector; the actual expiry date is not directly returned in the rolling-option
response (a real, disclosed limitation — see Phase 3).

**10. Data timestamp semantics**: NSE bhavcopy = one EOD snapshot per contract per day, dated by
trading day (no intraday timestamp). Dhan rolling-option/intraday = real per-bar epoch timestamps,
verified this session to be genuine, correctly-aligned NSE-local (IST) bar-close/bar-boundary times.

**11. Missingness**: quantified empirically this session (see the "Illiquidity" finding below) — the
raw option universe is dominated by structurally-zero-activity contracts on any given day; this is
NOT a data-quality defect, it is the genuine shape of an options market (most listed strikes never
trade on most days), but it means "missingness" in a derived feature set must be treated as
economically meaningful (illiquid/untraded), not imputed.

**12. Corporate-action implications**: unexamined this session in depth — flagged as an open Phase 5
item; the existing `quant_research/security_identity_map.py` (renamed/merged underlying identity
resolution, built for the equity/futures-universe research this session's predecessor work) is
directly reusable for any derivatives research that needs to track an underlying across a corporate
action, since options/futures are always written against a specific underlying equity identity.

**13. Survivorship implications**: the same underlying-equity survivorship concerns already
documented for the OHLCV research (`H_XSECT_006`, Phase A of the prior mission) apply identically to
any options/futures research keyed to those same underlyings — not a new problem, the same one,
with the same partially-built mitigation (`quant_research/point_in_time_fno_universe.py`,
`quant_research/security_identity_map.py`) already available to reuse.

**14. Can historical option chains be reconstructed?** **Partially, via two genuinely different
routes with different strengths/weaknesses** — see the inventory table and Phase 3 classification
below. Route A (NSE bhavcopy): full absolute-strike chain, EOD-only, no ready IV (would need a
pricing/inversion model built from scratch). Route B (Dhan rolling-option API): genuine intraday
resolution with ready-made IV/OI/spot, but only a relative-moneyness window (ATM±N strikes), not the
full chain, and no direct expiry-date field in the response.

## Real, quantified illiquidity finding (from re-inspecting this session's own already-downloaded
NSE bhavcopy sample, `classic_2022-06-15.zip`)

| Instrument type | Rows | Zero-volume fraction | Zero-OI fraction |
|---|---:|---:|---:|
| OPTSTK (stock options) | 56,796 | **85.8%** | **77.4%** |
| OPTIDX (index options) | 6,731 | **75.2%** | (not separately computed) |

This is a critical, quantified data-quality fact directly relevant to Phase 3/5: on ANY given day,
the overwhelming majority of listed option strikes have zero trading activity. A research design
that naively uses "the whole option chain" would be drowning in economically meaningless noise; any
serious signal must restrict to a liquidity-filtered subset (near-ATM, front-month — which is
precisely why Dhan's own `/charts/rollingoption` endpoint is designed around ATM±N rather than the
full chain, an implicitly liquidity-aware product design, not an arbitrary restriction).

## Formal inventory table

| Dataset | Source | Resolution | Coverage | Fields | Historical? | Quality | Usable? |
|---|---|---|---|---|---|---|---|
| NSE F&O bhavcopy (classic) | archives.nseindia.com, already-verified real archive | Daily/EOD | ~2016 to ~2024-06/07 (format transition already mapped, Phase A) | Symbol, expiry, strike, option type, OHLC, settle, contracts(volume), OI, OI change | Yes, full history | 85.8%/75.2% zero-volume rows (OPTSTK/OPTIDX) — real, must be liquidity-filtered | **Partially usable, with mandatory liquidity filtering** |
| NSE F&O bhavcopy (UDiFF) | nsearchives.nseindia.com, already-verified real archive | Daily/EOD | ~2024-07 onward | Same fields + underlying price (`UndrlygPric`), settlement price, finer instrument-type taxonomy (STO/IDO/STF/IDF) | Yes | Same illiquidity profile expected (not yet separately measured on a UDiFF sample) | **Partially usable, with mandatory liquidity filtering** |
| Dhan `/optionchain` (+ expirylist) | Dhan official REST API, verified live this session | Real-time snapshot | **Current only — no historical parameter exists** | OI, Greeks, IV, volume, bid/ask, per strike, per expiry | **No** | High (broker-computed Greeks/IV) | Current-only — not usable for backtesting, only for a future live/paper signal if one is ever promoted |
| Dhan `/charts/rollingoption` | Dhan official REST API, verified live this session with real data | 1/5/15/25/60-min | Up to ~5 years (confirmed to at least 4.5y), 30 days per call | OHLC, IV, OI, rolling relative strike, spot | **Yes** | Real, clean, genuine IV/OI in response; strike is relative-to-spot at each bar, not absolute; no explicit expiry date field in response; `expiryCode=0` quirk (must use 1) | **Usable, with the moneyness-relative and expiry-representation caveats disclosed in Phase 3** |
| Dhan `/charts/historical` + `/charts/intraday` with `instrument=FUTIDX/FUTSTK`, `oi=true` | Dhan official REST API, verified live this session with real nonzero OI | Daily (historical) / 1-60min (intraday, 90-day cap/call) | Daily: "back to inception"; Intraday: up to 5y, 90-day windows | OHLC + open_interest | **Yes** | Real, confirmed nonzero OI | **Usable for futures OHLC+OI**, subject to per-contract rollover handling (a genuinely new engineering problem, not yet solved anywhere in this repo) |
| Dhan instrument master (`SEM_STRIKE_PRICE`/`SEM_OPTION_TYPE`/`SEM_EXPIRY_DATE`/`SEM_LOT_UNITS`) | Already-cached `data/dhan/scrip-master.csv` | Point snapshot | **Current only** | Strike, option type, expiry, lot size, per-contract security ID | No (current snapshot only, same limitation already established for the equity side) | High (structured, already loaded) | Usable for CURRENT contract identity resolution only — same current-snapshot-only limitation already known from the equity-universe research |
| Dhan WebSocket OI/Full packets | `live/dhan/wire.py`, parser exists, never subscribed to live | Real-time streaming | N/A (live-only, would only ever be "from now on") | OI, 5-level depth, LTP | No | Untested in production (parser has unit tests only, no live integration) | Not usable for historical research at all; relevant only to a future live/paper promotion, not this research phase |
| yfinance options | `yfinance` package | N/A | N/A | N/A | No | N/A | **Confirmed unusable** — empty `.options` for NSE symbols, tested directly this session |
| India VIX (index-level implied vol proxy) | Already in use (`market.data_provider`, `quant_research/context_experiments.py`) | Daily | Full 10-year depth, already verified in prior sessions | Single index-level value, not per-stock/per-strike IV | Yes | Already used in F_CONTEXT research (now closed) | Usable only as a market-wide regime variable, not a derivatives-microstructure signal — already exhausted in that role |
| **Dhan `/charts/historical` with a RELATIVE `expiryCode` (not a specific contract securityId), `instrument=FUTIDX`** | Dhan official REST API, verified live this session — a major addendum to the inventory above | Daily | **1,623 real daily bars, 2019-12-31 to 2026-09-17** (~6.7 years), verified for NIFTY | OHLC + open_interest, ALREADY continuous across contract rolls | **Yes, and already-continuous** | Directly verified economically sensible: close price at 2020-03-11 = 9546.6, and the 40 largest day-over-day jumps (>3%) cluster EXACTLY around the real, well-documented March 2020 COVID crash — not artificial splice points at monthly roll dates. Dhan appears to resolve the relative `expiryCode` selector to "the near/front-month contract as of each historical date" internally, handling rollover on the provider's own side. | **Usable, and dramatically simplifies Phase 4/6 scope for index futures** — no manual NSE-bhavcopy-based rollover stitching (Phase 4's own `build_continuous_futures_series`) is needed for this route. Not yet verified whether the same internal-continuity behavior extends to `FUTSTK` (individual stock futures) — an open item, not assumed. |
