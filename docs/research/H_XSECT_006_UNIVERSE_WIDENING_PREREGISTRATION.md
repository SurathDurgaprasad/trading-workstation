# H_XSECT_006 — Universe Widening Pre-Registration

Written and frozen **before** any expanded-universe backtest is run.
Per this project's own multiple-testing discipline: eligibility rules,
strategy specification, and success/failure criteria are fixed here;
none of them may be changed after seeing results. Any deviation
discovered necessary during implementation must be disclosed and
justified in this document *before* results are examined, not folded
in silently afterward.

## 1. Research question

Does `H_XSECT_005`'s cross-sectional laggard portfolio effect (60-day
lookback, bottom quintile, pure fixed 20-bar hold, no stop, no target,
equal-weight, 20-day non-overlapping rebalance) survive when evaluated
on a materially larger NSE universe selected by an objective,
verifiable eligibility rule — and does it survive specifically on the
**symbols not in the original 32-symbol universe**, which is the only
way to distinguish "this is a real, broad phenomenon" from "this is an
artifact of which 32 stocks happened to be chosen first"?

**Explicit scope limit, stated up front**: this experiment does *not*
attempt to solve `H_XSECT_005`'s own sample-size problem (only ~120
rebalance periods exist at a 20-day cadence over 10 years, regardless
of how many symbols are in the universe each period). Universe
widening is cross-sectional external validation and a check on
universe-selection risk — a different axis entirely from the
time-series observation count. Widening the universe does not, and is
not claimed to, increase the number of independent rebalance periods.

## 2. Universe selection rule (audited, not assumed)

**Audit finding, before any new symbols were chosen**: this repository
already made a deliberate architectural decision, prior to this
session, to *not* implement NIFTY 50/100/200/500 index-membership
universes (`market_data/universe.py`'s own module docstring): *"this
project has no live, verifiable source for current membership
integrated anywhere — shipping a static list under the name 'NIFTY 50'
would claim an accuracy this project cannot back up."* This
pre-registration respects that decision rather than overriding it by
hardcoding an external NIFTY-100/200 list under a different name.
`market_intelligence/nse_sector_map.py` independently confirms the
same limitation for sector data.

The original 32-symbol universe itself is **not a documented,
versioned artifact anywhere in the committed repository** — it exists
only as a hand-copied literal repeated across this session's own
scratch scripts (never committed). No selection rationale for those
specific 32 symbols could be found in any commit, doc, or code
comment. This is disclosed honestly rather than assumed away: the
"original 32" is treated here purely as the historical control group
this research thread has already used five times (`H_XSECT_001`–
`H_XSECT_005`), not as a principled reference universe.

**Selected approach — Option C (existing repository-supported
mechanism), with an objective eligibility rule**: `live/dhan/
instruments.py`'s `DhanInstrumentMap` already downloads Dhan's public,
unauthenticated, real NSE instrument master CSV (verified, already
integrated, no new external dependency). The expanded universe is
defined as:

> Every NSE equity symbol (`SEM_EXM_EXCH_ID="NSE"`, `SEM_SEGMENT="E"`,
> `SEM_SERIES="EQ"`) that is also the underlying of at least one active
> NSE single-stock futures contract (`SEM_EXM_EXCH_ID="NSE"`,
> `SEM_SEGMENT="D"`, `SEM_INSTRUMENT_NAME="FUTSTK"`), as of the
> instrument-master snapshot downloaded 2026-09-09.

This is an objective, exchange-vetted liquidity/market-cap gate, not
an invented threshold: NSE only permits single-stock derivatives on
names meeting SEBI's own eligibility criteria (market-wide open
interest, market capitalisation, trading volume, and price
thresholds). It reuses data this project already has legitimate,
verified access to, and requires no claim about NIFTY-index membership
at all.

**Extraction procedure** (mechanical, disclosed in full so it is
reproducible): take every unique `FUTSTK` row's `SEM_TRADING_SYMBOL`,
strip the trailing `-<expiry>-FUT`-style suffix by splitting on the
first `-`, discard any result containing the substring `NSETEST`
(exchange connectivity test instruments, not real securities — 18
found), and keep only symbols that exact-match an `EQ`-series NSE
equity `SEM_TRADING_SYMBOL`. Two F&O underlyings (`BAJAJ`, `NAM`) did
not exact-match any `EQ`-series symbol via this simple prefix rule
(likely `BAJAJ-AUTO`/`BAJAJHLDNG`-style naming or a renamed company)
and are **excluded** — not manually corrected or investigated further,
to avoid any subjective, after-the-fact symbol-mapping decision.

**Result**: 208 NSE equity symbols. The original 32-symbol universe is
a **strict subset** — all 32 are F&O-eligible, 0 are excluded from the
208 — leaving exactly 176 genuinely new symbols with zero overlap
contamination. This is confirmed by direct set comparison, not
assumed.

## 3. Comparison groups (frozen)

| Group | Definition | n |
|---|---|---|
| ORIGINAL | The unchanged 32-symbol universe every `H_XSECT_001`–`005` entry used | 32 |
| EXPANDED-ONLY | The 176 F&O-eligible symbols not in ORIGINAL | 176 |
| COMBINED | ORIGINAL ∪ EXPANDED-ONLY | 208 |

Each group is run **independently** through the identical frozen
methodology below. ORIGINAL is the control (expected to closely
reproduce `H_XSECT_005`'s own already-registered numbers, since it is
the same 32 symbols over the same 10-year period). EXPANDED-ONLY is
the real test: if the effect only survives on ORIGINAL, that is a
selection-bias warning, not independent validation.

## 4. Eligibility rules beyond F&O membership (frozen)

- **Historical data availability**: identical, unmodified path every
  prior `H_XSECT_00x` entry already uses —
  `quant_research.market_behavior.build_symbol_dataset` /
  `build_universe_datasets`, `period="10y"`, via the existing
  `CachedMarketDataProvider`. A symbol that fails to fetch or build a
  dataset is excluded and reported by name — never silently dropped.
- **No additional liquidity threshold.** F&O eligibility is already an
  exchange-vetted liquidity/market-cap gate. Layering a second,
  independently-chosen `avg_daily_value` threshold on top would itself
  be an undisclosed, unregistered filter applied after the fact —
  explicitly not done.
- **Duplicate exclusion**: automatic via set union when forming
  COMBINED.
- **Corporate-action/data-quality handling**: identical to every other
  `H_XSECT_00x` entry — no special-casing for the expanded universe.
- **Sector coverage, disclosed limitation**: `market_intelligence/
  nse_sector_map.py`'s `NSE_SECTOR_MAP` covers 20 of the ORIGINAL 32
  symbols and **0 of the 176 new symbols** (it was hand-built,
  deliberately narrow, and never extended this session). Sector
  concentration for EXPANDED-ONLY will therefore be reported as
  **not available from existing infrastructure** rather than
  fabricated — building a new sector map for 176 symbols is out of
  scope for this experiment (see §9).

## 5. Fixed strategy specification (frozen, unchanged from `H_XSECT_005`)

`quant_research.cross_sectional_portfolio.
run_cross_sectional_laggard_portfolio_backtest` — `score_lookback=60`,
`n_buckets=5` (bottom quintile = Q5), `holding_bars=20`
(`DEFAULT_MAX_HOLDING_BARS`), `rebalance_every_bars=20`, no stop, no
target, `CostModel.india_nse_intraday_2026()`,
`initial_capital=100_000.0`, `min_symbols_per_date=15` (unchanged
default — noted as potentially conservative for the 176-symbol
EXPANDED-ONLY group, which has more than enough symbols to clear it
easily; not adjusted either way). **No parameter is retuned for the
larger universe.**

**Disclosed mechanical adaptation (found during Phase 1 data-
availability audit, before any backtest was run or any return
examined)**: `run_cross_sectional_laggard_portfolio_backtest` picked
its shared-rebalance-calendar reference symbol via `next(iter(
datasets.values()))` — arbitrary dict-insertion order. This was silently
safe for the original 32-symbol universe only because every one of
those 32 symbols happened to share the same ~10-year start date. A
5-symbol feasibility sample from the expanded universe found at least
one recently-listed name (`360ONE.NS`, ~7 years of history, not 10) —
had it been picked as the reference, the shared rebalance calendar
would have been silently truncated to its own shorter window,
discarding real, available years of data for every other symbol.
Fixed by extracting `select_reference_dataset` (new, unit-tested): the
reference is now explicitly the dataset with the **earliest start
date** (longest available history) among the group being tested. This
is a correctness fix to calendar selection, not a strategy-parameter
change — every other frozen parameter in this section is unchanged,
and the fix applies identically to all three comparison groups
(verified to leave ORIGINAL's own result unaffected, since its 32
symbols share one start date regardless of which is picked).

## 6. Success / failure criteria (frozen)

**This is explicitly NOT "clears `evaluate_promotion`'s 30-observation
sample-size gate."** Widening the universe does not change the number
of rebalance periods (~120, structurally fixed by 10 years ÷ 20
trading days), so that gate will almost certainly still return
`INSUFFICIENT_DATA` for validation/OOS on every group, exactly as it
did for `H_XSECT_005`. Reporting that as a "failure" would misrepresent
what this experiment can and cannot test — it is disclosed here so it
is not confused with a negative result later.

**Success (supports the "real, broad phenomenon" reading)**:
- EXPANDED-ONLY shows the same sign (positive mean portfolio return)
  as ORIGINAL in development, validation, and out-of-sample, with no
  split reversing sign in either group.
- COMBINED's own result is not driven by a small number of ORIGINAL
  symbols dominating the pooled sample (checked via §7's concentration
  diagnostics).

**Weak confirmation**: COMBINED positive but EXPANDED-ONLY mixed or
close to zero in one split.

**Selection-bias warning**: ORIGINAL positive, EXPANDED-ONLY negative
or clearly weaker.

**Failure (rejects the "broad phenomenon" reading)**: EXPANDED-ONLY
reverses sign relative to ORIGINAL in any split, or the effect is
revealed to be concentrated in a handful of symbols/one sector once
diagnosed (§7).

## 7. Mandatory adversarial checks (run regardless of outcome)

1. **Symbol concentration** (EXPANDED-ONLY): each member's own
   contribution to the pooled return; report top-1/top-5/top-10 share
   of total contribution, and a diagnostic re-computation with the
   single largest contributor removed (a robustness check, not a
   parameter search — the frozen strategy is not re-run with a
   different universe definition, only the same realized trades are
   re-aggregated excluding one symbol's own trades).
2. **Sector concentration**: reported only where `NSE_SECTOR_MAP`
   actually has coverage (ORIGINAL's own 20 mapped symbols); explicitly
   marked "not available" for EXPANDED-ONLY per §4, not fabricated.
3. **Liquidity sensitivity**: `avg_daily_value` computed directly per
   symbol from real OHLCV (`(close * volume).mean()`, the same formula
   `market_intelligence/scanner.py` already uses, reused not
   duplicated) over each symbol's own history; EXPANDED-ONLY split into
   above-/below-median liquidity halves and compared.
4. **Era stability**: development / validation / out-of-sample only
   (no finer yearly split — the period counts here are already small
   enough that a yearly cut would be close to meaningless; not
   attempted, to avoid presenting an underpowered slice as evidence
   either way).
5. **Survivorship bias — explicit disclosure, not a mitigation**: the
   208-symbol universe reflects **current** (2026-09-09) F&O
   eligibility, not point-in-time historical membership. Any stock that
   was liquid/F&O-eligible for some or all of the 2016–2026 window but
   has since become ineligible or delisted is entirely absent from this
   universe. This could inflate the measured effect if such stocks
   would have disproportionately underperformed (a classic
   survivorship-bias direction). No historical, point-in-time NSE
   membership data source is available to this project (§2) — this
   limitation is carried forward into the verdict, not resolved.
6. **Original vs. expanded-only vs. combined comparison**: the
   mandatory three-way read described in §6.

## 8. Reproducibility record

- Dhan instrument-master snapshot: `data/dhan/scrip-master.csv`,
  downloaded/cached 2026-09-09 (this session), 197,288 rows.
- 208-symbol COMBINED / 176-symbol EXPANDED-ONLY / 32-symbol ORIGINAL
  lists: exact, reproducible output of
  `quant_research.universe_expansion.build_universe_groups` given that
  same instrument-master snapshot — not re-typed by hand anywhere.
- **Symbols excluded for a data-availability failure**: `GVT&D.NS` and
  `M&M.NS` (2 of 176 EXPANDED-ONLY symbols) — both fail with *"Refusing
  to use symbol ... to construct a filesystem path — contains
  characters outside the safe set"*, a pre-existing, already-documented
  `CachedMarketDataProvider` limitation (path-safety validator rejects
  `&`), not new to this experiment. 174/176 symbols built successfully;
  170/174 were selected into the bottom quintile at least once across
  the 120 rebalance periods actually tested (the remaining 4 built
  successfully but were never ranked into Q5 in this run — not an
  error).
- Data period `10y`, interval `1d`, via the existing
  `CachedMarketDataProvider`/`quant_research.market_behavior.
  build_universe_datasets` path, unchanged.
- Split boundaries: computed independently per group via
  `quant_research.cross_sectional_portfolio.select_reference_dataset`
  (see §5's disclosed fix) + `backtesting.splits.split_periods`, from
  each group's own longest-history member.
- Strategy parameters: exactly as frozen in §5, unmodified.
- Cost model: `CostModel.india_nse_intraday_2026()`, unmodified.

## 9. Results — REJECTED (selection-bias / sign-reversal, per the frozen §6 criteria)

Full evidence: `H_XSECT_006` in `strategy/hypothesis_registry.py`.

**Mean portfolio return per rebalance period, all three groups, same
frozen methodology:**

| Group (n symbols) | Development (n=72) | Validation (n=24) | Out-of-sample (n=24) |
|---|---|---|---|
| ORIGINAL (32) | **+0.76%** | **+1.81%** | **+0.46%** |
| EXPANDED-ONLY (176, 174 built) | **-0.29%** | +1.31% | **-0.58%** |
| COMBINED (208) | **-0.36%** | +1.12% | **-1.26%** |

`evaluate_promotion` returns `INSUFFICIENT_DATA` for all three groups
(unchanged from `H_XSECT_005` — as §1/§6 explicitly anticipated,
widening the universe does not change the ~120-period ceiling).

**This is exactly the §6 "Failure" condition, triggered directly**:
EXPANDED-ONLY reverses sign relative to ORIGINAL in *two* of three
splits (development and out-of-sample both flip from positive to
negative; only validation stays positive, and more weakly than
ORIGINAL's own +1.81%). COMBINED shows the same pattern, more
pronounced in out-of-sample (-1.26%). **Verdict: REJECTED** — the
laggard-outperformance pattern that looked real and robust across
`H_XSECT_001`–`H_XSECT_005` does *not* generalize beyond the original
32-symbol universe; it looks substantially attributable to
universe-selection risk (survivorship into a specific set of blue-chip
large-caps), exactly the failure mode this experiment was designed to
be able to detect.

### Adversarial checks

**1. Symbol concentration (EXPANDED-ONLY).** 170 distinct symbols were
selected into Q5 at least once. The pooled contribution total is
itself near zero (+0.79, summed across all member-period returns),
which makes a "% of total" concentration metric numerically unstable
(division by a near-zero denominator) — reported honestly as unusable
rather than a misleading number. The direct, meaningful diagnostic
instead: removing the single largest-magnitude contributor
(`YESBANK.NS`, a well-known distressed/volatile bank stock) and
re-aggregating the *same* realized trades barely moves the result —
development -0.20% (was -0.29%), validation +1.35% (was +1.31%),
out-of-sample -0.59% (was -0.58%). **The sign reversal is not a
single-outlier artifact.**

**2. Sector concentration.** Not available for EXPANDED-ONLY — `NSE_
SECTOR_MAP` covers 0 of the 176 new symbols, a disclosed gap per §4/§7,
not fabricated. Building sector coverage for 176 more symbols was
explicitly out of scope (§10).

**3. Liquidity sensitivity.** EXPANDED-ONLY (174 fetchable symbols)
split into above-/below-median `avg_daily_value` halves (median
≈₹1.36B), each **re-ranked independently within its own half** (a
different diagnostic design from check 1's same-trades
re-aggregation — this asks whether the *strategy itself* behaves
differently against a smaller, liquidity-segmented peer group, not
whether one name's realized path drove the pooled number). Both halves
show a similar, modest pattern — below-median: dev +0.46%, val +2.64%,
oos +0.00%; above-median: dev +0.35%, val +1.67%, oos -0.07% — **the
effect is not concentrated in illiquid names**; if anything the
below-median half is marginally stronger. This diagnostic does not
explain, and was not designed to explain, why the full 176-symbol
ranking (a different peer group again) reversed sign — that deeper
mechanism question is not chased further in this same run.

**4. Era stability.** Already shown in the main table — no split, in
any group, needed a finer yearly cut to see the reversal; it is
visible at the coarsest dev/val/oos granularity already.

**5. Survivorship bias.** As disclosed in §7 before any result was
seen: this is a **current** (2026-09-09) F&O-eligibility snapshot, not
point-in-time historical membership. The REJECTED verdict makes this
limitation directionally conservative, not concerning — a
survivorship-biased universe would be expected to *inflate* a positive
effect (by excluding historical underperformers that have since
delisted or lost eligibility), yet the effect still reversed sign. If
anything, a true point-in-time universe (unavailable to this project)
might show an even *weaker* result on the expanded universe, not a
stronger one.

**6. Original vs. expanded-only vs. combined.** The mandatory
three-way read (§6): this is a clean **selection-bias warning
escalating to falsification** — ORIGINAL positive in all three splits,
EXPANDED-ONLY/COMBINED negative in two of three, with validation the
only split where the sign survives (and even there, weaker than
ORIGINAL). Per §6's own frozen language, ORIGINAL positive +
EXPANDED-ONLY negative is explicitly the "selection-bias warning"
category, and the two-split reversal specifically meets the stronger
"Failure" bar.

### What this does and does not mean

This does **not** invalidate `H_XSECT_001`'s own raw measurement or
`H_XSECT_005`'s own portfolio result on the *original* 32 symbols —
both remain exactly what they were, real findings on that specific,
disclosed universe. What it does mean: the mechanism does not appear
to be a broad, universe-agnostic NSE cross-sectional phenomenon. It
looks specific to the kind of large-cap, "well-known, established,
liquid, mostly blue-chip" names the original 32 happen to be (the
project's own `starter_nse.yaml` describes them as exactly that) —
plausibly because mean-reversion in mega-cap "quality" names (temporary
overreaction, institutional dip-buying, index-flow effects) is a
different economic mechanism than mean-reversion in a broader,
more volatile mid-cap/small-cap-inclusive universe, where a stock in
the bottom quintile is more likely to be there for a genuine,
non-reverting deterioration ("catching a falling knife" risk). This is
offered as a plausible explanation, not a tested one — pursuing it
further would need its own new, honestly pre-registered hypothesis.

## 10. Explicitly out of scope for this experiment

- Building a sector map for the 176 new symbols (a real, disclosed gap
  in §4/§7, not silently patched with a fabricated mapping).
- Any stop/target redesign (that branch is closed per `H_XSECT_004`;
  unrelated to universe selection).
- Any attempt to increase the number of independent rebalance periods
  (§1's explicit scope limit).
- Point-in-time historical NSE index-membership data (unavailable to
  this project, per the existing `market_data/universe.py` decision).
