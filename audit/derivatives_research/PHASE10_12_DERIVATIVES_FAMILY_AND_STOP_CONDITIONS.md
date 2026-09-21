# Phase 10 — Derivatives Research Family Tracking, and Phase 12 — Stop Conditions

## Phase 10: a clearly defined, separately-tracked derivatives research family

Per the mission's own explicit instruction: **not buried inside the existing 59-hypothesis OHLCV
registry** (`strategy/hypothesis_registry.py`, untouched by this entire mission). Tracked here
instead, as its own family.

| ID | Question | Data source | Model spec | Preregistered? | Dependent on | Verdict |
|---|---|---|---|---|---|---|
| DERIV_001 | Does NIFTY futures basis add incremental h10 prediction over the OHLCV baseline? | Dhan `/charts/historical` (FUTIDX, continuous), `^NSEI` spot | Logistic regression, 4 baseline features + 1 augmented | Yes, before any result seen | Independent (first entry) | NO MEANINGFUL INCREMENTAL INFORMATION |
| DERIV_002 | Does NIFTY futures OI change add incremental h10 prediction over the same baseline? | Same data, same baseline | Logistic regression, same 4 baseline features + 1 different augmented | Yes, before any result seen; explicitly named as the deferred candidate in DERIV_001's own preregistration | Same baseline model/data as DERIV_001, distinct augmented feature (not a re-run) | NO MEANINGFUL INCREMENTAL INFORMATION (weaker than DERIV_001, negative on out-of-sample) |

**Total derivatives family size: 2 hypotheses, 0 variants (neither entry was re-run after seeing a
result), 1 shared dataset (NIFTY spot+futures, 2016-09 to 2026-09), 2 model specifications (baseline
vs. augmented, per entry), 2 dependent tests (same baseline model/data, no independent replication
attempted since neither entry needed to advance past Phase 6), 2 preregistered tests, 0 exploratory
tests.**

**Multiple-testing correction**: `family_size=2` → Bonferroni-corrected z=2.2414 (vs. uncorrected
1.96), computed via the same `strategy/multiple_testing.py` primitive the OHLCV research's own
Phase 8 used. Disclosed for completeness; not decision-relevant here since both entries used a fixed
ΔAUC≥0.02 effect-size threshold (not a p-value) and both failed that threshold by a wide margin
regardless of any correction.

**No hypothesis in this family was cherry-picked.** Both entries are reported in full, including
DERIV_002's own weaker-than-DERIV_001 result (a genuinely less flattering outcome that was not
suppressed or reframed).

## Phase 12: Stop conditions — formally invoked

Checked against the mission's own 7 stop conditions:

1. **Historical derivatives data is not sufficiently available**: NOT the binding condition —
   Phase 1-3 found genuinely real, historically-verified data (NSE bhavcopy, and especially Dhan's
   own already-continuous futures series). Data availability was not the limiting factor.
2. **Data quality cannot support leakage-free testing**: NOT the binding condition — Phase 5's audit
   found and fixed one real defect, disclosed two real unresolved risks (neither of which affected
   DERIV_001/002, since both used Dhan's own already-continuous series, not the manually-stitched
   bhavcopy route where the roll-discontinuity risk lives), and confirmed the rest of the checklist
   passes cleanly.
3. **Derivatives variables provide no meaningful incremental information — MET, this is the binding
   condition.** Both tested families (futures basis, futures OI change) failed their own
   pre-registered, fixed-in-advance decision thresholds, on both validation and out-of-sample, with
   DERIV_002 actually reversing sign on out-of-sample.
4. **Signals fail OOS**: subsumed by condition 3 (out-of-sample was one of the two decision-relevant
   splits in both entries' own frozen decision rule).
5. **Positive results disappear after costs**: not reached — no result was ever positive enough to
   proceed to a costed trading test (Phase 7 was never entered).
6. **Positive results fail realistic portfolio construction**: not reached, same reason.
7. **Results fail independent replication**: not reached, same reason.

**Determination: STOP.** Per the mission's own explicit instruction ("If one avenue fails, do not
automatically test dozens of alternatives. Record the failure. Move to the next genuinely distinct
information family only if the preregistered research plan allows it"): the preregistered research
plan for THIS pass explicitly named exactly two families (futures basis, futures OI change) and
explicitly stated the second entry's own preregistration would be the last one in this pass. Both
are now tested, both are recorded honestly (including DERIV_002's own weaker result), and the plan
itself does not authorize a third, fourth, fifth, sixth, or seventh family (options OI imbalance,
put/call structure, IV level/skew/term-structure) without a fresh, separately-justified research
design — not an automatic continuation.

## What was NOT done, and why (explicitly, not silently)

- **Options-based families (C-G in the mission's own list)** were never tested. Per Phase 3's own
  classification, they are real (Classification B) but carry meaningfully more engineering overhead
  (multi-call aggregation for IV skew/term-structure; no IV field at all in the NSE bhavcopy route;
  no direct expiry-date field in Dhan's rolling-option response) than the two Classification-A
  futures families that were tested first and both failed. Testing them now, immediately after two
  clean negative results on the CHEAPER, CLEANER data, would risk exactly the "keep trying variants
  until one works" pattern the mission explicitly prohibits.
- **Stock-level (not just NIFTY-index-level) versions of futures basis/OI-change** were not tested.
  Phase 6's own preregistration explicitly scoped to NIFTY only, for the stated reasons (already
  -continuous data source verified, avoids corporate-action/rollover complications). Extending to
  individual stocks would require either verifying Dhan's continuous-series behavior for `FUTSTK`
  (untested, an open item per Phase 1's own addendum) or using the more complex, disclosed
  -limitation bhavcopy route — a genuinely new, separately-scoped effort, not a costless variant.
- **A non-linear model class** (e.g., gradient boosting) was not substituted for logistic regression
  after the linear result disappointed. This would be exactly the kind of "keep trying until
  something works" pattern the mission's own "prefer data validity over model complexity" and
  "do not tune the signal after seeing results" instructions exist to prevent.

## Terminal conclusion for this research program

**Neither of the two genuinely distinct, pre-registered, economically-motivated derivatives
information families tested (futures basis, futures OI change) provides meaningful incremental
predictive information beyond the already-exhausted OHLCV feature set, at NIFTY-index level, h10
horizon.** This is not a data-availability failure (real, historically deep, economically sensible
data was found and used) and not an infrastructure failure (a genuine, tested, leak-audited data
layer was built). It is a substantive negative research result on the two specific questions asked.

Per the mission's own stated ultimate objective ("determine whether derivatives information provides
a real, reproducible, economically implementable source of trading edge") — **the answer for the two
avenues actually tested is no.** This does not close the door on derivatives research entirely (the
options-based families remain a real, disclosed, unexplored possibility — Classification B, not D),
but it does mean this specific pass stops here, honestly, without manufacturing a third test to keep
the research program going. Real order execution remains disabled throughout; nothing in this
research program touched live trading infrastructure.
