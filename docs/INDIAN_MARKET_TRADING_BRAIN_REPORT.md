# Indian Market Trading Brain — Report

Mission: "BUILD THE REAL INDIAN MARKET TRADING BRAIN" (2026-09-08,
continuing the same day's earlier "TRADING BRAIN EXECUTION LOOP"
session). Explicit pivot: NSE/BSE is the primary product; the US
market becomes context-only. This report covers the repository audit,
the India Market Context Engine extension, the SEBI/constraint audit,
a real data-integrity incident found and fixed mid-session, and the
first Family C (global → India transmission) research result.

## 1. Repository & architecture audit (Phase 1–3)

Per the mission's own explicit "reuse, don't rebuild" instruction, the
existing architecture was inspected before any code was written.
Finding: `market_intelligence/regime.py` already implemented the core
of what the mission calls a "Market Context Engine" —
`MarketBreadth` (advance/decline), `BenchmarkContext` (NIFTY 50
trend+volatility via `compute_benchmark_context`, fully generic —
works for any symbol), and `SectorStrength` (generic Yahoo GICS sector
grouping), combined into one `MarketRegimeReport`. What was genuinely
missing, confirmed by reading the code rather than assumed: official
NIFTY sectoral indices (as opposed to the existing generic GICS
buckets) and India VIX.

A real, live check (not a guess) of candidate India-specific and
global macro tickers against the existing Yahoo infrastructure found:

| Signal | Ticker | Status |
|---|---|---|
| 8 NIFTY sectoral indices (BANK/IT/AUTO/PHARMA/FMCG/METAL/REALTY/ENERGY) | `^NSEBANK`, `^CNXIT`, etc. | **Real, working, verified with genuine 2-year+ depth** |
| NIFTY Financial Services | `NIFTY_FIN_SERVICE.NS` | **Real, working** — the naming-convention-matching `^CNXFIN` looked right on a shallow check but has ~zero historical depth; caught via a real failed live run, corrected |
| India VIX | `^INDIAVIX` | **Real, working** |
| USD/INR, crude (WTI/Brent), gold, DXY | `INR=X`, `CL=F`/`BZ=F`, `GC=F`, `DX-Y.NYB` | **Real, working**, not yet wired into the regime engine — a natural next increment |
| GIFT Nifty | (several plausible tickers tried) | **Not reliably available** via Yahoo — a genuine, disclosed gap |

All of the working signals require zero new credentials — they go
through the existing Yahoo-backed `MarketDataProvider`.

## 2. India Market Context Engine extension (Phase 4/5)

Extended `market_intelligence/regime.py` (not a new module) with:

- `NIFTY_SECTOR_INDICES` + `compute_sector_index_regimes()` — one real
  official-index trend+volatility regime per sector, reusing
  `compute_benchmark_context()` completely unchanged (pure
  aggregation, no new regime logic).
- `compute_india_vix_context()` — the one genuinely new computation:
  current VIX LEVEL vs. its own trailing average (deliberately
  distinct from calling `compute_benchmark_context` on the VIX symbol,
  which would answer the confusing second-order "is VIX's own
  volatility elevated" question instead of "is fear elevated now").
- Both wired into `MarketRegimeReport` as **opt-in** fields
  (`include_nifty_sector_indices`, `include_india_vix`, both default
  `False`) — every existing caller of `build_market_regime_report`
  sees byte-for-byte unchanged behavior. CLI:
  `main.py regime --with-nifty-sectors --with-india-vix`.

**Verified end-to-end against real, current data (2026-09-08)**: real
sector divergence visible on the day — NIFTY BANK/IT/FMCG in
downtrend, NIFTY AUTO/PHARMA/METAL/REALTY/ENERGY in uptrend, against a
NIFTY 50 benchmark itself in a downtrend (breadth 3 advancing / 7
declining / 5 flat). India VIX at 11.2, NORMAL regime.

23 new tests. Commit `88339e9`.

## 3. SEBI / Indian market constraint awareness (Phase 2)

Documented in `docs/SEBI_ALGO_TRADING_AWARENESS.md` (commit `eb03279`)
— engineering awareness, explicitly not legal certification, sourced
via live web search rather than invented. Key finding: SEBI's
algo-trading framework (Algo-ID order tagging, Order-to-Trade Ratio
monitoring, strategy registration) becomes fully enforceable April 1,
2026, but **none of it currently applies to this project**, because
the project structurally never places a real order. Documented exactly
what would apply if that ever changed, so it stays a deliberate future
decision. Also documented Dhan's real published API rate limits
(20/10/5/1 req/s by endpoint category) and a disclosed, non-urgent gap:
`live/dhan/rest_client.py` has no client-side rate limiting of its own.

## 4. A real, live data-integrity incident, found and fixed

While running the first Family C research question (§5), per-symbol
sample counts for an identical condition varied 6–7x across 5 NSE
IT-sector stocks with no economic reason to expect that. Traced to a
real, serious bug: **28 of 32 NSE research-universe symbols had
silently degraded from ~1240 cached daily bars (5 years) to 252 bars
(1 year)**. Root cause: `CachedMarketDataProvider` serves whatever is
already cached on a hit regardless of the period later requested; a
symbol first cache-missed by a caller using a shorter `--period` (this
project's own scheduler commands default to `--period 1y`) stays that
shallow indefinitely. The project's own existing `cache-status` tool
checked cache AGE only — it reported "0 symbols stale" throughout this
entire degradation, because a shallow cache is not a stale one.

**Fixed** (commit `73eab05`): the data first — all 28 symbols
re-fetched with genuine `period=5y`, verified restored to ~1240 bars
each. Then the tooling gap — `cache-status` gained a `--shallow-below-bars`
flag surfacing real `bar_count`/`period` per symbol (already recorded
in each symbol's `meta.json`, never previously read back).

**Honest implication for prior research**: every hypothesis tested
against the NSE side of the 41-symbol universe in the earlier
same-day "TRADING BRAIN EXECUTION LOOP" session and the preceding
"BUILD THE REAL TRADING BRAIN" session (H_ENTRY_002/004, H_MEANREV_001,
H_RELSTRENGTH_001, H_BREAKOUT_001) was run against a mix of ~4
genuinely-deep and ~28 shallow NSE symbols, not the intended uniform
5-year universe — real, material, but not necessarily disqualifying
(most of those results were REJECTED/negative findings, and a smaller
sample would if anything make a confident negative result MORE
conservative, not less). The one hypothesis that used only the US side
(H_MEANREV_002) is unaffected — all 9 US symbols had full depth
throughout. Recorded as a disclosed caveat, not silently ignored;
re-litigating each affected hypothesis was judged lower-value than
documenting the caveat and moving forward with now-correct data for
new research (which is what §5 already did).

## 5. Family C research: Nasdaq → NIFTY IT transmission (H_TRANSMISSION_001)

The mission's own explicitly named example, tested directly. Does
Nasdaq's prior-session return predict NIFTY IT-sector stocks' (TCS,
Infosys, HCL Tech, Tech Mahindra, Wipro) own forward returns? Real
overnight lag: US closes ~2:30am IST, well before NSE's 9:15am IST
open the same NSE trading day that session's information becomes
available for.

Run against the **corrected**, full-depth data (post §4 fix), frozen
thresholds from development-period data only (n=3680, p20=-1.10%,
p80=+1.20%):

| Direction | Development | Validation | Out-of-sample |
|---|---|---|---|
| NASDAQ_DECLINE (bottom 20%) | DECISIVE NEGATIVE, all 3 horizons | DECISIVE NEGATIVE, all 3 horizons | Decisive at h=1 only; every horizon still negative |
| NASDAQ_ADVANCE (top 20%) | DECISIVE POSITIVE, all 3 horizons | DECISIVE POSITIVE, all 3 horizons | Not decisive at any horizon; point estimates **reverse sign** |

Per-symbol concentration check: well-balanced across all 5 IT stocks
in both directions (~217–226 observations each) — not concentrated in
any single name.

**Verdict: INCONCLUSIVE**, with a real, honest, worth-stating asymmetry.
The decline side is a genuine, direction-consistent signal that simply
lost statistical power out-of-sample (smaller OOS sample, never a
contradicting sign). The advance side is materially weaker and should
be trusted less — a genuine reversal, not just reduced significance.
Consistent with a plausible (not independently verified here) general
prior that bad news transmits across markets more reliably than good
news. Not promoted (neither direction decisive in all three splits);
not rejected (decline never flips sign, both sides strongly decisive
in 2 of 3 splits with substantial sample sizes). No strategy was built
on top of this finding — per the mission's own explicit "prove the
market behavior before building a strategy" ordering, an INCONCLUSIVE,
asymmetric raw finding does not yet warrant it.

## 6. Live paper observation

The live `schedule loop --paper-execute --live-source dhan` process
started earlier the same session continued running throughout this
entire mission segment, checked periodically, never restarted except
once (to load the scheduler fix from §... see the earlier
`MARKET_INTELLIGENCE_DISCOVERY_REPORT.md` for that specific incident).
Multiple real intraday ticks completed successfully during this
segment, including one that correctly skipped re-submitting a paper
order for a symbol with an already-pending position — expected,
honest duplicate-avoidance behavior, not a bug.

## 7. What remains genuinely open

1. **USD/INR, crude, gold, DXY** are confirmed real and working but not
   yet wired into `market_intelligence/regime.py` — natural next
   increments for Family C research (crude → ONGC/aviation/paints,
   USD/INR → IT/pharma exporters).
2. **GIFT Nifty** remains genuinely unavailable via the project's
   existing free/no-credential data path — would need a different
   source if ever pursued.
3. **H_TRANSMISSION_001's advance side** is weak enough that it should
   not be treated as a real, tradeable signal; the decline side is
   promising enough to be worth a larger-sample re-test (more IT
   symbols, or a longer history) before any strategy-level attempt.
4. **Universe quality audit (Phase 6)** — the existing 32-symbol NSE
   universe's sector representativeness, survivorship bias, and
   liquidity adequacy were not formally re-audited this segment beyond
   the cache-depth fix; a dedicated pass remains open.
5. **Sector-conditioned stock-level research (Phase 5's own core
   ask — "STOCK SIGNAL + SECTOR CONTEXT + MARKET CONTEXT")** — the
   context engine now exists and is verified; using it to condition an
   actual stock-level hypothesis (e.g., "does a BUY signal in a NIFTY
   IT stock perform better when NIFTY IT itself is in an uptrend?") is
   the natural next research step and was not yet run this segment.
