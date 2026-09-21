# DERIV_003 / DERIV_004 — Options Volatility-Surface Information-Content Tests, Pre-Registration

Written and frozen **before** any dense multi-year IV data is fetched or any model is fit. Third and
fourth entries of the derivatives research family (after DERIV_001 futures basis, DERIV_002 futures
OI change, both closed/negative). Final controlled pass, per the user's own explicit framing.

## 1. Research question (frozen)

"Does the options implied-volatility surface (ATM level, and separately, put/call asymmetry)
provide incremental out-of-sample information about NIFTY's own forward return direction, beyond
the existing OHLCV feature set **and** the previously-tested futures information (basis, OI
change)?"

Two tests, both preregistered together, both accounted for in the multiple-testing treatment below
— not a "test one, then decide whether to test the second" design.

- **DERIV_003 (primary)**: ATM implied-volatility level (`atm_iv_level`, from
  `quant_research.iv_surface.compute_atm_iv_level`).
- **DERIV_004 (the one pre-declared backup, per Phase 3's own explicit scoping)**: put/call IV
  asymmetry (`put_call_iv_skew`, from `quant_research.iv_surface.compute_put_call_iv_skew`).

No third or fourth options feature (strike-based skew, term structure) is tested in this pass —
Phase 3's own document names this explicitly, before either result is seen.

## 2. Frozen baseline — per the mission's own explicit definition

**"Existing frozen OHLCV features + previously tested futures information"** — unlike DERIV_001/002
(which used OHLCV alone as baseline), this baseline INCLUDES `futures_basis` and
`futures_oi_change_pct`, even though neither cleared its own independent significance bar in
DERIV_001/002. This is the mission's own explicit instruction, not a re-litigation of those closed
results — the question now is whether IV features add anything BEYOND this fuller (already
-including-futures) baseline, matching real research practice of layering a new information source
on top of everything already investigated, not just the raw OHLCV subset.

Baseline features (6, all already-established from DERIV_001/002, no new computation): `trend_ratio`,
`rsi_14`, `atr_pct`, `zscore_close_20`, `futures_basis`, `futures_oi_change_pct`.

## 3. Frozen augmented features

- DERIV_003: baseline + `atm_iv_level` (raw percent units, per `iv_surface.py`'s own documented
  convention — no rescaling).
- DERIV_004: baseline + `put_call_iv_skew` (percentage-point difference, put minus call).

Each tested independently against the SAME baseline (two separate augmented models, not one model
with both IV features at once — matching the mission's own "do not combine into a complex model"
instruction, carried from Phase 3 into Phase 4).

## 4. Frozen data source and retrieval plan

NIFTY (`securityId=13`, `OPTIDX`), Dhan `/charts/rollingoption`, `strike="ATM"`, `expiryFlag=
"MONTH"`, `expiryCode=1` (the only working near-term selector — `expiryCode=0` is a confirmed
-broken Dhan endpoint value, Phase 1's own finding), `interval="60"` (hourly — the finest resolution
available; DAILY is not directly offered by this endpoint), fetched in sequential, paced 30-day
windows (the endpoint's own documented per-call cap) covering approximately the most recent 2.2
years available at the time of retrieval, for BOTH `drvOptionType="CALL"` and `"PUT"`. Each trading
day's own DAILY feature value is the LAST valid (post-quality-gate) hourly reading of that day —
matching how "close" is used as the representative daily value throughout this project's existing
OHLCV pipeline, not a new convention invented for this entry.

Quality gate: exactly Phase 2's own frozen rules (`MIN_PLAUSIBLE_IV_PCT=3.0`,
`VOLUME_MEDIAN_MULTIPLE=20.0`), applied via `quant_research.iv_surface`'s own tested functions,
unmodified.

## 5. Frozen target, model, splits

Identical to DERIV_001/002: `y = 1 if fwd_return_10 > 0 else 0` (h10 primary); logistic regression,
development-only fit; `backtesting.splits.split_periods` (60/20/20) applied to the merged spot
+futures+options frame's own available date range (bounded by whichever series is shortest — now the
options series, given its own more limited ~2.2-year retrieval versus the futures series' multi-year
depth).

## 6. Statistical discipline

- **Primary metrics**: ROC-AUC and Brier score on validation and out-of-sample, for baseline vs. each
  augmented model — ΔAUC and ΔBrier are the quantities of interest, exactly as in DERIV_001/002.
- **Calibration**: reliability table (predicted-probability deciles vs. realized frequency) for
  each augmented model on out-of-sample.
- **Minimum sample**: 100 observations per split (unchanged from DERIV_001/002) — given the shorter
  options-data retrieval window, this is EXPLICITLY CHECKED before any model is fit; if any split
  falls below 100, that is recorded as a genuine data-adequacy limitation, not silently worked
  around by lowering the floor after the fact.
- **Multiple-testing family**: `family_size=2` for THIS pass (DERIV_003, DERIV_004 tested together);
  `family_size=4` for the derivatives program as a whole (including DERIV_001/002) — both disclosed
  via `strategy/multiple_testing.py`'s own `bonferroni_corrected_z`, exactly as DERIV_002 already
  did for its own family-size=2 context. As before, this is disclosure context, not a re-decision,
  since the decision rule uses a fixed effect-size threshold, not a p-value.

## 7. Decision rule (frozen, identical structure to DERIV_001/002)

- **Meaningful incremental information** (per feature, independently): ΔAUC ≥ 0.02 on BOTH
  validation and out-of-sample, AND Brier score does not worsen on either split.
- **No meaningful incremental information**: any other outcome.
- Per the mission's own explicit Phase 6 instruction: **if NEITHER DERIV_003 nor DERIV_004 shows
  meaningful incremental information, the derivatives research program CLOSES — no third IV
  threshold, strike, expiry, holding period, model, or OI feature will be tested afterward,
  regardless of how close either result comes to the threshold.**

## 8. What will NOT change after this is pre-registered

No new baseline feature. No third options feature substituted in. No threshold adjustment after
seeing either ΔAUC. No re-derivation of the target horizon or the daily-aggregation convention
(last-valid-hourly-reading). No retroactive change to DERIV_001/002's own verdicts.

## 9. Scope note

Offline, isolated audit scripts, reusing `quant_research/iv_surface.py`,
`market.indicators`/`quant_research.alpha_features`, `backtesting.splits` unmodified. Real, live,
read-only Dhan Data API calls (already-credentialed, already-subscribed) — no order placement of any
kind. No production strategy/RiskEngine code touched. No live-fleet dependency.
