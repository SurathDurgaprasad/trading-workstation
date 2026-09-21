# Derivatives Research Audit — Log

## 2026-09-21 — Mission start, Phases 1-5

New research program, continuing from `f9a3b99` (the closed OHLCV/technical-signal research tree).
User's own objective: determine whether Indian equity/index derivatives (options + futures)
information is predictive beyond what the exhausted OHLCV research already covered, starting from a
rigorous data-availability audit before any signal work.

**Phase 1**: dispatched a dedicated Explore agent to inventory every existing repo code path
touching derivatives (Dhan integration, bhavcopy parsing, market_intelligence, DB schemas, tests,
prior audit documents). Result: zero derivatives capability is currently exercised anywhere in the
live/research pipeline, though raw material (Dhan instrument-master strike/expiry/option-type
columns; NSE bhavcopy option/future rows) already flows through existing code paths unused. In
parallel, made real, live, credentialed calls to Dhan's own official Data APIs (already-subscribed,
same account used for live trading) to verify capability beyond what this repo currently wraps:
`/optionchain` (real-time, current-only), `/charts/rollingoption` (genuine historical minute-level
IV/OI/OHLC/spot for both index and stock options, up to ~5 years, verified with real NIFTY and
RELIANCE data), `/charts/historical`/`/charts/intraday` with `oi=true` (real, nonzero futures OI,
verified for a NIFTY futures contract). Caught and disclosed a real, previously-undocumented API
quirk: `/charts/rollingoption`'s `expiryCode=0` (documented as valid) is rejected by the live
endpoint; `expiryCode=1` works — verified this is specific to that endpoint, not universal.
`yfinance` options capability for NSE symbols tested directly and confirmed empty (`.options`
returns `()`). Re-inspected the already-cached NSE bhavcopy sample from the prior session's Phase A
work to quantify real option-market illiquidity: 85.8% of OPTSTK rows, 75.2% of OPTIDX rows have
zero volume on a real sampled day.

**Phase 2**: answered all 10 of the mission's own A-J external-data questions, all grounded in the
real API/archive evidence gathered in Phase 1 (no separate new NSE archive requests made, to respect
the already-established rate-limiting caution — new verification used Dhan's own API instead, which
has generous, documented rate limits).

**Phase 3**: classified every named candidate information source into the mission's own A/B/C/D
scale against its own 9 minimum requirements. Futures OI/OI-change/basis/premium-discount/volume and
options OI/OI-change classified A. IV-level/skew/term-structure and full historical option-chain
reconstruction classified B (real, but requiring multi-call aggregation and/or lacking a direct
expiry field). Current-snapshot option chain and Dhan WebSocket OI packets classified C
(current/live-only). yfinance options and "the maximal combination" (intraday+absolute-strike+ready
-IV+full-10-year-window in one source) classified D. Decision: Phase 4 built around the strongest
(Classification A) candidates — futures OHLC+OI and options OI — not IV.

**Phase 4**: built `quant_research/derivatives_data.py`, the smallest reusable data model per the
mission's own explicit "do not build a platform" instruction — `FuturesBar`/`OptionBar` frozen
dataclasses with full provenance, `parse_bhavcopy_futures`/`parse_bhavcopy_options` reusing the prior
session's own `BhavcopyFile` retrieval unmodified, a deterministic futures-rollover selector
(`select_active_futures_contract`/`build_continuous_futures_series`), and a staleness detector.
`tests/test_derivatives_data.py` (28 tests, all passing) covers every required category from the
mission's own list. Validated against the real, already-cached 2022-06-15 bhavcopy: 582 real futures
bars and 9,747 real liquid option bars parsed correctly, with a liquidity-survival rate (15.3%)
closely matching Phase 1's own independently-measured illiquidity statistics — a genuine, internally
-consistent cross-check, not just a fixture-level test pass. No trading signal computed anywhere in
this phase, per its own explicit scope boundary.

**Phase 5**: mandatory leakage audit against the mission's own 12-item checklist. **One real defect
found and fixed**: `select_active_futures_contract`'s original fallback logic could, in principle,
select an already-expired contract if one were ever passed as a candidate (never manifests with real
bhavcopy data today, since NSE stops listing an expired contract the next day, but the function
should not silently rely on that external guarantee) — fixed to filter `expiry >= as_of` before any
roll-window logic in every code path, with two new regression tests, all passing. Two real,
disclosed, deliberately UNRESOLVED risks recorded for any future signal-construction phase: the
futures-roll price discontinuity (no back-adjustment built; any future price-return signal must
avoid computing a return across a roll boundary or explicitly back-adjust) and corporate-action
strike/lot-size adjustment tracking (not addressed; `security_identity_map.py` only resolves
underlying-equity identity, not option-contract-level adjustments). One hard source limitation
recorded: NSE bhavcopy carries no bid/ask at all.

Full regression run before committing (see commit message for pass/fail counts). Zero production
strategy/RiskEngine/order-execution code modified. Real order execution remains disabled. Live fleet
not touched this phase (no data-availability validation required it).

Deliverables this session so far: `audit/derivatives_research/PHASE1_DATA_INVENTORY.md`,
`PHASE2_EXTERNAL_DATA_AUDIT.md`, `PHASE3_DATA_FEASIBILITY_GATE.md`, `PHASE5_LEAKAGE_AUDIT.md`,
`quant_research/derivatives_data.py`, `tests/test_derivatives_data.py`, `STATE.json`, this log.

---

## 2026-09-21 (continuing) — Major data-availability discovery, Phase 6 information-content tests, terminal stop

**Major addendum discovery**: while investigating a dense-data-density option for Phase 6, a real,
live, credentialed test call to Dhan's `/charts/historical` (`instrument=FUTIDX`, a RELATIVE
`expiryCode=0` selector rather than a specific contract's own `securityId`) over a wide date range
returned 1,623 real daily bars spanning 2019-12-31 to 2026-09-17 — far more than the single
contract's own short life that was expected. Directly verified this is a genuine, already-continuous
front-month series (not a data artifact): the 40 largest single-day price moves in the series
cluster exactly around the real, well-documented March 2020 COVID crash (e.g. close=9,546.6 on
2020-03-11, matching real historical NIFTY futures levels), not at monthly contract-roll boundaries.
A second, wider pull (2016-2026) returned 2,554 bars back to 2015-12-31. This means Dhan's own
backend already resolves contract rollover internally for this query pattern — eliminating the need
for new NSE bhavcopy pulls (and their associated rate-limit risk) to build a dense, multi-year,
research-grade NIFTY futures series. Added as an explicit addendum to `PHASE1_DATA_INVENTORY.md`'s
own table.

**Phase 6**: preregistered and executed two genuinely distinct, economically-motivated
information-content tests, both using the newly-discovered dense futures series against NIFTY's own
already-established OHLCV baseline (`trend_ratio`, `rsi_14`, `atr_pct`, `zscore_close_20` — all
already-existing, reused, not invented features), via logistic regression (chosen over any more
complex model class per the mission's own "prefer data validity over model complexity" instruction),
evaluated by ROC-AUC/Brier/calibration on a frozen 60/20/20 development/validation/out-of-sample
split (1,069/363/360 observations).

`DERIV_001` (futures basis, preregistered in
`docs/research/DERIV_001_FUTURES_BASIS_INFORMATION_CONTENT_PREREGISTRATION.md` before any result was
seen): validation ΔAUC=+0.0024, out-of-sample ΔAUC=+0.0026 — both roughly 8x smaller than the
pre-registered 0.02 decision threshold. Brier score improvements were negligible (noise-level).
Calibration was weak and non-monotonic. **NO MEANINGFUL INCREMENTAL INFORMATION.**

`DERIV_002` (futures OI change, the ONE candidate explicitly named and deferred in DERIV_001's own
preregistration, itself preregistered before any result was seen, and itself explicitly stating it
would be the LAST test in this pass): validation ΔAUC=+0.0009, out-of-sample ΔAUC=**-0.0016**
(reversed sign) — a weaker, cleaner rejection than DERIV_001. **NO MEANINGFUL INCREMENTAL
INFORMATION.**

Phases 7-9 (trading test, realistic economics, portfolio implementation) correctly SKIPPED — gated
behind Phase 6 finding meaningful incremental information, which did not occur in either entry.

**Phase 10**: the two-entry derivatives research family tracked separately in
`PHASE10_12_DERIVATIVES_FAMILY_AND_STOP_CONDITIONS.md`, per the mission's own explicit "do not bury
it inside the old 59-hypothesis count" instruction — not added to `strategy/hypothesis_registry.py`.
Family-size=2 Bonferroni context disclosed (z=2.2414), not decision-relevant since both entries used
a fixed, pre-registered effect-size threshold rather than a p-value.

**Phase 11**: not applicable — no candidate survived Phase 6 to require independent replication.

**Phase 12**: stop conditions formally checked against all 7 named conditions. Condition 3
("derivatives variables provide no meaningful incremental information") is the binding one — data
availability and quality were both genuinely sufficient (conditions 1-2 not met), but neither tested
family cleared its own pre-registered bar. **Determination: STOP.** Explicitly recorded what was NOT
tested and why: the five remaining candidate families named in the mission's own list (options OI
imbalance, put/call structure, IV level/skew/term-structure) were not tested — they remain real,
disclosed, Classification-B (not D) possibilities for a future, separately-justified pass, not
pursued now specifically to avoid the "keep trying variants until one works" pattern the mission's
own instructions explicitly prohibit. No H_ or DERIV_003+ entry was manufactured to keep the program
going.

Zero production strategy/RiskEngine/order-execution code modified throughout this entire mission.
Real order execution remains disabled. Live fleet not touched — no data-availability validation
required it (all verification used Dhan's own read-only Data APIs directly).

Deliverables this continuation:
`docs/research/DERIV_001_FUTURES_BASIS_INFORMATION_CONTENT_PREREGISTRATION.md`,
`docs/research/DERIV_002_FUTURES_OI_CHANGE_INFORMATION_CONTENT_PREREGISTRATION.md`,
`audit/derivatives_research/scripts/deriv_001_futures_basis_information_content.py`,
`audit/derivatives_research/scripts/deriv_002_futures_oi_change_information_content.py`,
`DERIV_001_RESULTS.md`/`.csv`, `DERIV_002_RESULTS.md`/`.csv`,
`PHASE10_12_DERIVATIVES_FAMILY_AND_STOP_CONDITIONS.md`, `PHASE1_DATA_INVENTORY.md` (addendum),
`STATE.json` (updated).

---

## 2026-09-21 (continuing) — Final controlled pass: options volatility surface, program closed

User's own explicit framing: "the FINAL CONTROLLED DERIVATIVES PASS," testing whether the options
IV surface (level, skew, term structure, call/put asymmetry) adds information beyond OHLCV+futures.

**Phase 1** (`PHASE1_OPTIONS_IV_DATA_AVAILABILITY.md`): re-verified Dhan's `/charts/rollingoption`
live this session (not re-citing the prior pass without re-checking). Confirmed real IV/OI/OHLC/
spot for both CALL and PUT. Found and disclosed a real, reproducible API defect:
`expiryCode=0` ("current/near expiry," the documented default) is rejected by this specific
endpoint; only `expiryCode=1`("next")/`2`("far") work -- meaning genuine near-term IV can never be
fetched from this endpoint, a real ceiling on any term-structure work (not attempted this pass).
Confirmed strike granularity (`ATM`/`ATM+1`/`ATM-1`/`ATM+2` all return distinct, correctly-spaced
real strikes) and a real, economically-expected put/call IV asymmetry already visible in raw data
(~9.3% call vs. ~11.6% put IV at the same strike). Found a genuine data-quality defect: the final
1-2 trading sessions before a contract's own expiry show both degenerate near-zero IV readings
(0.0, 0.4) and implausible ~1,000x-normal volume spikes in the SAME bars -- a real raw-feed
artifact, not a processing bug.

**Phase 2** (`PHASE2_LIQUIDITY_QUALITY_GATE.md`): liquidity/quality rules frozen BEFORE any
predictive result -- an IV plausibility floor (3.0%) and a 20x-trailing-median volume ceiling,
both derived directly from Phase 1's own observed defect pattern, never tuned against a return.
Adequacy determination: a real full-month sample showed 0% zero-volume/zero-OI/null-IV for the
ATM-restricted endpoint (dramatically better than the raw bhavcopy full chain's own 85.8%/75.2%
zero-volume finding from the prior pass) -- a sufficiently liquid sample exists, proceeding.

**Phase 3** (`PHASE3_VOLATILITY_SURFACE_CONSTRUCTION.md`, `quant_research/iv_surface.py`, 22 tests):
built `compute_atm_iv_level` and `compute_put_call_iv_skew`, each with an exact, documented
temporal/contract-selection specification (timestamp, expiry/strike selection, no interpolation,
missing-strike/stale-observation handling, units, normalization) and directly-tested no-look-ahead
guarantees. Deliberately scoped to these TWO features only (ATM level primary, put/call skew the
one pre-declared backup) -- strike-based skew and expiry term structure explicitly named and
deferred, not tested, to avoid the "test dozens of variants" pattern.

**Phase 4** (`docs/research/DERIV_003_004_IV_SURFACE_INFORMATION_CONTENT_PREREGISTRATION.md`):
frozen before fetching the dense multi-year dataset. Per the mission's own explicit instruction,
the baseline was redefined to include OHLCV + the previously-tested futures features (basis, OI
change) -- not OHLCV alone, since those futures features are now "existing" information even though
neither cleared its own bar independently.

**Phase 5**: 56 real, paced (1 second apart), live, read-only Dhan API calls fetched 2.2 years of
NIFTY ATM CALL/PUT rolling-option IV data (28 ~29-day windows per side, 3,946 raw bars per side).
After the frozen quality gate: 3,910/3,756 clean hourly bars, downsampled to 546 daily observations,
merged with the existing OHLCV+futures baseline to 397 usable rows. **DERIV_003** (ATM IV level):
NO MEANINGFUL INCREMENTAL INFORMATION -- ΔAUC negative on BOTH validation (-0.0070) and
out-of-sample (-0.0081), Brier score worsens on both. **DERIV_004** (put/call IV skew): NO
MEANINGFUL INCREMENTAL INFORMATION -- ΔAUC positive but 6-12x below the pre-registered 0.02
threshold on both splits (+0.0035 val, +0.0017 oos). **Honestly, prominently disclosed limitation**:
validation (n=77) and out-of-sample (n=84) fell below the pre-registered 100-observation floor,
an emergent consequence of intersecting the options data's own shorter ~2.2-year reliable window
with the temporal 60/20/20 split -- not knowable in advance, not hidden after the fact. Judged not
to change the conclusion, since both results were decisive misses (one negative-signed, the other
an order of magnitude short), not marginal ones close enough that a larger sample might plausibly
flip the verdict.

**Phase 6 decision gate**: neither DERIV_003 nor DERIV_004 passed. Per the mission's own explicit
instruction, **the derivatives research program is CLOSED.** Phases 7-10 (frozen trading
experiment, economic validity, portfolio realism, independent replication) correctly not executed
-- gated behind Phase 6, never reached.

**Terminal report** (`PHASE6_DECISION_GATE_AND_TERMINAL_REPORT.md`) covers the FULL derivatives
program (both the futures pass and this options pass): data availability, data quality, a 4
-hypothesis results table (DERIV_001-004, all negative), exact preregistrations, OOS evidence,
multiple-testing treatment (family_size=4, z=2.4977, disclosure-only since all four entries used a
fixed effect-size threshold, not a p-value), economic implications (none reached, by design -- no
result cleared the bar to even attempt a costed test), and a complete, honest limitations section
(the sample-size caveat above; deliberately narrow scope -- NIFTY-only, h10-only, logistic
-regression-only, 2-of-5 named IV feature families; no bid/ask data in either source; stock-level
futures continuity unverified). **Classified: NO DEMONSTRATED EDGE WITH CURRENT INFORMATION SET.**
No `DERIV_005` or later entry was created to keep the program going.

Zero production strategy/RiskEngine/order-execution code modified throughout this entire mission.
Real order execution remains disabled. Live fleet not touched. Full regression to be run before
committing (see commit message for pass/fail counts).

Deliverables this continuation: `audit/derivatives_research/PHASE1_OPTIONS_IV_DATA_AVAILABILITY.md`,
`PHASE2_LIQUIDITY_QUALITY_GATE.md`, `PHASE3_VOLATILITY_SURFACE_CONSTRUCTION.md`,
`PHASE6_DECISION_GATE_AND_TERMINAL_REPORT.md`, `DERIV_003_004_RESULTS.md`/`.csv` x2,
`quant_research/iv_surface.py`, `tests/test_iv_surface.py`,
`docs/research/DERIV_003_004_IV_SURFACE_INFORMATION_CONTENT_PREREGISTRATION.md`,
`audit/derivatives_research/scripts/deriv_003_004_iv_surface_information_content.py`,
`STATE.json` (updated).
