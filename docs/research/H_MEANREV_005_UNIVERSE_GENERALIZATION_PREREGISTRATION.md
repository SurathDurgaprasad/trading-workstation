# H_MEANREV_005 — Universe Generalization Check for H_MEANREV_003, Pre-Registration

Written and frozen **before** any experiment code runs. Per this
project's own multiple-testing discipline: the universe, signal,
regime definition, splits, and success/failure criteria are fixed
here; none may change after seeing results.

## 1. Research question

Does `H_MEANREV_003`'s raw finding — `zscore_close_20` oversold
entries, gated on NIFTY's own `market_trend_regime == TRENDING_UP` —
**generalize beyond the original 32-symbol research universe**, or is
it a universe-specific artifact of that particular symbol selection?

Explicitly **not** the question "can mean reversion be made
profitable somehow" — a test of whether the SAME frozen mechanism,
unchanged in every respect except which symbols it is measured
against, produces the SAME sign and a comparably decisive result on
genuinely independent NSE symbols.

## 2. Audit — what `H_MEANREV_003` actually tested (verified by reading the pre-registration and registry entry directly, not assumed)

Read in full: `docs/research/
H_MEANREV_003_REGIME_CONDITIONING_PREREGISTRATION.md` and the
`H_MEANREV_003` `HypothesisRecord` in `strategy/
hypothesis_registry.py`.

- **Signal**: `zscore_close_20 < -2.0` (Candidate A) / `< -1.5`
  (Candidate B) — `H_MEANREV_001`'s own frozen a priori thresholds,
  never retuned, via `quant_research/mean_reversion_signal.py`.
- **Regime**: NIFTY's (`^NSEI`) own `market_trend_regime` (external
  overlay, `backtesting.regime.classify_trend_at` applied to the
  index, NOT each stock's own trend) via `build_benchmark_regime_series`
  + `attach_external_regime` — `TRENDING_UP` is the bucket that
  cleared the frozen success bar; `TRENDING_DOWN`/`SIDEWAYS` did not
  (dev/val decisive, OOS reverses toward zero/negative);
  `LOW_VOLATILITY`/`HIGH_VOLATILITY` were REJECTED outright (clean
  sign reversals, severely underpowered).
- **Universe**: `ORIGINAL_32_NSE_UNIVERSE` (32 large-cap NSE symbols),
  NSE-only, 10 years daily.
- **Splits**: standard 60/20/20 development/validation/out-of-sample
  on the shared calendar.
- **Horizons measured**: `FORWARD_HORIZONS` (1,2,3,5,10,20); results
  reported at h5/h10/h20 specifically (no single explicit "primary"
  horizon was pre-declared in that entry — all three were reported
  together as decisive).
- **Sample sizes** (`TRENDING_UP`, h20): Candidate A dev n=775, val
  n=225, oos n=238/250 (small variation by horizon from NaN trimming);
  Candidate B dev n=2053, val n=617, oos n=583/616.
- **Why INCONCLUSIVE, not REJECTED or SUPPORTED**: the raw measurement
  itself is real — CI-decisive positive in all three splits, both
  candidates, at h5/h10/h20, no sign reversal, broad (24-29 of 32
  symbols contribute a positive mean), non-decaying (7 of 9 complete
  years CI-decisive positive), survives a 0.30% round-trip cost check
  with a wide margin. It is INCONCLUSIVE rather than SUPPORTED because
  a raw, cost-free measurement is not the same claim as an executable,
  risk-sized trade — exactly the same reasoning `H_XSECT_001` was held
  to. Its own executable conversion, `H_MEANREV_004`, was separately
  attempted and REJECTED (both candidates showed a CI straddling zero
  in every split, via the same STOP-domination mechanism `H_XSECT_002`
  already found for an unrelated signal).
- **"Universe-generalization" is not named anywhere in `H_MEANREV_003`'s
  own pre-registration or evidence field** as a planned next step — the
  ONLY next step that document names is the executable-strategy
  conversion (already done, REJECTED as `H_MEANREV_004`). The
  universe-generalization idea was raised in a LATER session segment's
  own status-document commentary, by analogy to `H_XSECT_006` (which
  DID test universe generalization, but for a completely different
  signal — cross-sectional laggard ranking, not this zscore+regime
  signal) — worth stating precisely since the mission's own instruction
  was not to assume that prior summary is correct. Having now read the
  primary sources directly: the check itself is real and genuinely
  useful (H_MEANREV_003's own signal has literally never been measured
  on any universe besides the original 32), even though `H_MEANREV_003`
  itself never explicitly proposed it — its value comes by analogy to
  `H_XSECT_006`'s own demonstrated selection-bias risk in this exact
  codebase, not from any planned-and-deferred item in `H_MEANREV_003`
  itself.

## 3. Infrastructure audit — zero new production code needed

- `quant_research.mean_reversion_signal.REGIME_GATED_CANDIDATES`
  (`_oversold_2std_trending_up`, `_oversold_1_5std_trending_up`)
  already implements the EXACT frozen signal, requiring only an
  externally-attached `market_trend_regime` column — reused verbatim,
  unchanged.
- `quant_research.context_experiments.build_benchmark_regime_series` +
  `attach_external_regime` already compute and attach NIFTY's own
  regime — reused verbatim, unchanged.
- `quant_research.universe_expansion.build_universe_groups` already
  computes the frozen `expanded_only` 176-symbol group from Dhan's
  public, unauthenticated instrument master (no credentials involved)
  — reused verbatim. The already-cached instrument master
  (`data/dhan/scrip-master.csv`, retrieved 2026-09-01, reused as-is,
  no network call) reproduces the IDENTICAL 176-symbol set `H_XSECT_006`
  used (176 expanded-only, same count) — recorded verbatim below,
  frozen before any measurement runs.
- `quant_research.market_behavior.measure_condition`'s own
  `regime_filter` parameter already supports filtering on
  `trend_regime`/`volatility_regime` — reused unchanged for the
  UNCONDITIONED control below.

**This check requires zero new production code** — only a scratch
measurement script, matching the established precedent for a pure
generalization/replication check.

## 4. Universe (frozen, recorded verbatim BEFORE any measurement runs)

`EXPANDED_ONLY` — the 176 F&O-eligible NSE symbols NOT in
`ORIGINAL_32_NSE_UNIVERSE`, computed via `build_universe_groups()`
against the cached Dhan instrument master:

```
360ONE.NS, ABB.NS, ABCAPITAL.NS, ADANIENSOL.NS, ADANIENT.NS,
ADANIGREEN.NS, ADANIPOWER.NS, ALKEM.NS, AMBER.NS, AMBUJACEM.NS,
ANGELONE.NS, APLAPOLLO.NS, APOLLOHOSP.NS, ASHOKLEY.NS, ASTRAL.NS,
ATHERENERG.NS, AUBANK.NS, AUROPHARMA.NS, BAJAJHLDNG.NS, BANDHANBNK.NS,
BANKBARODA.NS, BANKINDIA.NS, BDL.NS, BEL.NS, BHARATFORG.NS, BHEL.NS,
BIOCON.NS, BLUESTARCO.NS, BOSCHLTD.NS, BPCL.NS, BRITANNIA.NS, BSE.NS,
CAMS.NS, CANBK.NS, CDSL.NS, CGPOWER.NS, CHOLAFIN.NS, COCHINSHIP.NS,
COFORGE.NS, COLPAL.NS, CONCOR.NS, CROMPTON.NS, CUMMINSIND.NS, DABUR.NS,
DELHIVERY.NS, DIXON.NS, DLF.NS, DMART.NS, ETERNAL.NS, FEDERALBNK.NS,
FORCEMOT.NS, FORTIS.NS, GAIL.NS, GLENMARK.NS, GMRAIRPORT.NS,
GODFRYPHLP.NS, GODREJCP.NS, GODREJPROP.NS, GVT&D.NS, HAL.NS,
HAVELLS.NS, HDFCAMC.NS, HDFCLIFE.NS, HINDALCO.NS, HINDPETRO.NS,
HINDZINC.NS, HYUNDAI.NS, ICICIGI.NS, ICICIPRULI.NS, IDEA.NS,
IDFCFIRSTB.NS, IEX.NS, INDHOTEL.NS, INDIANB.NS, INDIGO.NS,
INDUSINDBK.NS, INDUSTOWER.NS, INOXWIND.NS, IOC.NS, IREDA.NS, IRFC.NS,
JINDALSTEL.NS, JIOFIN.NS, JSWENERGY.NS, JSWSTEEL.NS, JUBLFOOD.NS,
KALYANKJIL.NS, KAYNES.NS, KEI.NS, KFINTECH.NS, KPITTECH.NS,
LAURUSLABS.NS, LICHSGFIN.NS, LICI.NS, LODHA.NS, LTF.NS, LTM.NS,
LUPIN.NS, M&M.NS, MAHABANK.NS, MANAPPURAM.NS, MANKIND.NS, MARICO.NS,
MAXHEALTH.NS, MAZDOCK.NS, MCX.NS, MFSL.NS, MOTHERSON.NS,
MOTILALOFS.NS, MPHASIS.NS, MUTHOOTFIN.NS, NATIONALUM.NS, NAUKRI.NS,
NBCC.NS, NESTLEIND.NS, NHPC.NS, NMDC.NS, NYKAA.NS, OBEROIRLTY.NS,
OFSS.NS, OIL.NS, ONGC.NS, PAGEIND.NS, PATANJALI.NS, PAYTM.NS,
PERSISTENT.NS, PETRONET.NS, PFC.NS, PGEL.NS, PHOENIXLTD.NS,
PIDILITIND.NS, PIIND.NS, PNB.NS, PNBHOUSING.NS, POLICYBZR.NS,
POLYCAB.NS, POWERINDIA.NS, PREMIERENE.NS, PRESTIGE.NS, RADICO.NS,
RBLBANK.NS, RECLTD.NS, RVNL.NS, SAGILITY.NS, SAIL.NS, SBICARD.NS,
SBILIFE.NS, SHREECEM.NS, SHRIRAMFIN.NS, SIEMENS.NS, SOLARINDS.NS,
SONACOMS.NS, SRF.NS, SUPREMEIND.NS, SUZLON.NS, SWIGGY.NS,
TATACONSUM.NS, TATAELXSI.NS, TATAPOWER.NS, TIINDIA.NS, TITAN.NS,
TMPV.NS, TORNTPHARM.NS, TRENT.NS, TVSMOTOR.NS, UNIONBANK.NS,
UNITDSPR.NS, UNOMINDA.NS, UPL.NS, VBL.NS, VEDL.NS, VMM.NS, VOLTAS.NS,
WAAREEENER.NS, YESBANK.NS, ZYDUSLIFE.NS
```

(176 symbols, 0 overlap with `ORIGINAL_32_NSE_UNIVERSE` by
construction — set subtraction.) Same known caveat `H_XSECT_006`
already disclosed: 2 of 176 (`M&M.NS`, `GVT&D.NS`) are expected to
fail the market-data fetch due to the `&` character (a path-safety
allowlist rejection, `backtesting/cache.py`'s own
`_validate_symbol_for_path`) — disclosed in advance, not discovered
after the fact, and handled the same way every universe-level runner
in this project already handles one bad symbol (skip, continue, never
abort the batch).

## 5. Signal, regime, splits, horizons (frozen, unchanged from `H_MEANREV_003`)

- Signal: `quant_research.mean_reversion_signal.REGIME_GATED_CANDIDATES`
  (`A_oversold_2std_trending_up`, `B_oversold_1_5std_trending_up`),
  verbatim, not retuned.
- Regime: NIFTY's own `market_trend_regime` via
  `build_benchmark_regime_series("^NSEI", period="10y")` +
  `attach_external_regime`, verbatim, not retuned.
- Splits: `shared_period_boundaries`-derived 60/20/20, computed fresh
  on the EXPANDED_ONLY universe's own shared calendar (not assumed
  identical to the original universe's dates, though in practice NSE
  symbols share nearly the same calendar).
- Horizons: `FORWARD_HORIZONS` (1,2,3,5,10,20), all six reported.
  **Primary horizon: h20** — matching `H_MEANREV_003`'s own most
  emphatic evidence (the year-by-year stability table and the
  strongest, most cost-margin-surviving figures were reported at h20),
  chosen for direct comparability with that entry's own headline
  numbers, not selected after seeing this entry's own results.

## 6. Experiment design and controls (frozen)

Three measurements, each via `measure_condition`/
`measure_condition_by_market`-style pooling (reused unchanged),
`market_filter="NSE"`, across development/validation/out-of-sample:

1. **ORIGINAL (control, not re-run)** — `H_MEANREV_003`'s own
   already-published `TRENDING_UP`-gated result on
   `ORIGINAL_32_NSE_UNIVERSE`, reused as the benchmark this entry
   compares against, not recomputed.
2. **EXPANDED_TRENDING_UP (the generalization test)** — the SAME
   `REGIME_GATED_CANDIDATES` predicates, on `EXPANDED_ONLY` (§4), same
   regime gate.
3. **EXPANDED_UNCONDITIONED (control)** — the SAME `CANDIDATES` (plain
   `_oversold_2std`/`_oversold_1_5std`, no regime gate) on
   `EXPANDED_ONLY` — mirrors `H_MEANREV_003`'s own "Step 0 unconditioned
   control" exactly, applied to the new universe, to check whether the
   TRENDING_UP gate itself still adds value here (not just whether raw
   oversold-mean-reversion works on new symbols at all).

Minimum sample size: **>=30 observations per split**, both candidates,
matching `H_MEANREV_003`'s own explicit floor — a split below this is
reported as insufficient data, not folded into a weaker bar.

## 7. Success / failure / inconclusive criteria (frozen)

**Generalizes (supports `H_MEANREV_003`'s own mechanism, not
automatic promotion)**: `EXPANDED_TRENDING_UP` shows a CI-decisive
positive mean forward return at h20 in ALL THREE splits, both
candidates, no sign reversal — the SAME bar `H_MEANREV_003` itself was
held to, now applied to independent symbols.

**Does NOT generalize (evidence of universe-dependence, a real and
useful negative finding, not a failure of process)**: a sign reversal
in any split, OR the effect fails to clear CI-decisiveness in a split
where the original universe was decisive, OR the effect size is
materially smaller/weaker on `EXPANDED_ONLY` even where directionally
consistent (assessed qualitatively against the original's own figures,
disclosed either way).

**Inconclusive**: below the 30-observation floor in any split, or a
directionally-consistent-but-not-clearly-distinguishable result (the
"underpowered, not reversed" shape this registry has repeatedly and
honestly recorded elsewhere).

## 8. What will NOT change after this is pre-registered

No retuning the -2.0/-1.5 thresholds. No redefining the regime (still
NIFTY's own trend, still `TRENDING_UP` specifically — `TRENDING_DOWN`/
`SIDEWAYS`/volatility regimes are not re-tested here, since
`H_MEANREV_003` already rejected them on the original universe and
re-testing them on a new universe without new justification would be
exactly the kind of scope creep this project's discipline forbids). No
redefining the 176-symbol universe after seeing any result. No
switching horizons after seeing results (h20 primary, fixed above). No
dropping a losing candidate.

## 9. Adversarial checks (mandatory ONLY if §7's "generalizes" criterion is met)

Symbol concentration (does the effect fire broadly across the 176 new
symbols, or concentrate in a handful); era stability (year-by-year, as
`H_MEANREV_003` itself did); cost-margin check against `CostModel.
india_nse_intraday_2026()`'s ~0.21%-0.30% round-trip reference (raw
measurement only, not a claim about executable survival — the
`H_XSECT_002`/`004` lesson still applies); sector concentration where
`NSE_SECTOR_MAP` coverage permits (a real, disclosed partial-coverage
gap, same caveat carried by every prior entry that touches it).

## 10. Scope note

Pure historical-data research, read-only against the existing/newly-
fetched market-data cache. Does not touch `data/paper_trading.db`,
`data/live_state.db`, `data/scheduler_runs.db`,
`data/direction_forecasts.db`, or `data/predictions.db`. No broker
execution changes. No scheduler dependency (uses only cached/fetched
historical data via the standard research provider, not the live Dhan
feed — and the one Dhan-sourced input this entry uses, the instrument
master, is public and unauthenticated, already cached locally, no
credentials involved).
