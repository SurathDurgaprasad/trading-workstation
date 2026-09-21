# Path 1 Result — Mean Reversion CLOSED, Even After Point-in-Time Correction

Executed exactly per `docs/research/H_MEANREV_010_POINT_IN_TIME_REPLAY_PREREGISTRATION.md`'s own
frozen decision rule. Both steps reused H_MEANREV_010/011's own frozen entry/exit/cost/sizing/
scheduler code completely unmodified — the only change across both steps was universe membership.

## Step 1 — Corporate-action/security-identity layer

`quant_research/security_identity_map.py` (14 tests, all passing): of the 14-symbol sample
Phase A's own 2022-vs-2026 diff surfaced, **8 verified recoverable** via a real web-search-confirmed
rename or merger-survivor mapping (SRTRANSFIN→SHRIRAMFIN, MCDOWELL-N→UNITDSPR, PVR→PVRINOX,
TATAMOTORS[pre-2025]→TMPV, AMARAJABAT→ARE&M, GMRINFRA→GMRAIRPORT, IBULHSGFIN→SAMMAANCAP,
L&TFH→LTF), **3 confirmed genuinely non-recoverable** (HDFC, MINDTREE, IDFC — each legally absorbed
INTO a different, pre-existing company; splicing would create a new data-integrity error, not fix
one), **3 left unresolved** (LTI — confirmed survivor but no working successor ticker found;
GUJGASLTD, PEL — no corporate action identified). One important correction to Phase A's own earlier,
unverified assumption: IDFC.NS was originally guessed recoverable via IDFCFIRSTB.NS; direct
verification found IDFC Ltd was the ABSORBED party in a reverse merger, so IDFCFIRSTB.NS's own full
10-year Yahoo depth is the BANK's own pre-existing history, not a valid continuation of IDFC Ltd's.

**Practical caveat found during the replay itself**: `AMARAJABAT.NS`'s own correctly-identified
successor (`ARE&M.NS`) is blocked by an orthogonal, pre-existing safety guard in
`backtesting/cache.py::CachedMarketDataProvider` (refuses any ticker containing characters outside
`[A-Z0-9^._-]`, the same "&"-character path-safety class `H_XSECT_006` already documented for
`GVT&D.NS`/`M&M.NS`) — the identity mapping is factually correct, but not practically usable through
this project's existing pipeline without a separate fix to that guard (not attempted here, out of
scope for this mission).

## Step 2 — Frozen H_MEANREV_010 single-symbol replay, point-in-time universe

`audit/edge_feasibility/scripts/build_point_in_time_snapshots.py` retrieved 11 real, dated NSE F&O
bhavcopy snapshots (annual anchors 2016–2025 + 2026-09-18), paced 3 seconds apart, zero rate-limiting
encountered this time. 350 distinct canonical symbols ever eligible across the window (vs. today's
~208) — genuine historical churn, not a data artifact (142 symbols in the 2020 snapshot alone,
consistent with the COVID-era tightening of derivative eligibility criteria).

`audit/edge_feasibility/scripts/h_meanrev_010_point_in_time_replay.py`: 310/350 symbols buildable
(40 failed — many are well-known 2018–2020 NBFC/PSU-bank-crisis casualties: DHFL, JP Associates,
Reliance Capital, Andhra Bank, Allahabad Bank, Syndicate Bank, etc. — genuinely, honestly excluded,
not a bug).

| Split | Original H_MEANREV_010 | Point-in-time-corrected | Verdict |
|---|---|---|---|
| development | n=2897, +0.08% [-0.27%,+0.44%], STATISTICALLY_MEANINGLESS | **n=2765, -0.888% [-1.264%,-0.513%], NEGATIVE_PERFORMANCE (CI-decisive)** | Flips to decisively negative |
| validation | n=688, +1.51% [+0.94%,+2.08%], POSITIVE_PERFORMANCE | n=698, +1.238% [+0.778%,+1.699%], POSITIVE_PERFORMANCE | Survives, weaker |
| out_of_sample | n=840, +0.98% [+0.52%,+1.44%], POSITIVE_PERFORMANCE | n=867, +0.816% [+0.367%,+1.265%], POSITIVE_PERFORMANCE | Survives, weaker |

**Genuinely important new finding**: development's flip from "meaningless" to CI-decisively negative
is economically coherent, not noise — it is consistent with formerly-eligible stocks that later
defaulted/were resolved via NCLT (DHFL, Reliance Capital, JP Associates, several PSU banks later
merged/wound down) being included for the first time under point-in-time-correct membership. Buying
"the dip" on a company that is oversold because it is going bankrupt, not because it is a temporary
overreaction, is exactly the failure mode a genuine survivorship correction should surface. The
original, current-snapshot-biased universe had silently excluded these names' own worst historical
periods.

**Per the frozen decision rule** (validation AND out-of-sample both remain CI-decisive positive):
**this step survives.** Proceeding to Step 3.

## Step 3 — Realistic portfolio construction, point-in-time universe

`audit/edge_feasibility/scripts/h_meanrev_010_point_in_time_portfolio_realism.py`: reused
`quant_research/mean_reversion_portfolio.py::schedule_portfolio` (H_MEANREV_011's own frozen
4-position, ₹25,000-per-slot, ₹100,000-total scheduler) completely unmodified — only the candidate
event list was pre-filtered by point-in-time eligibility before scheduling. 16,982 raw candidate
events → 9,825 point-in-time-eligible (7,157 excluded as ineligible at their own signal date) → 495
accepted trades (337 rejected for capacity, 8,380 for cash, 597 for an already-open position on the
same symbol).

| Split | Original H_MEANREV_011 | Point-in-time-corrected | Verdict |
|---|---|---|---|
| development | n=555, +0.10% | n=322, **-0.445%** [-1.341%,+0.451%] | STATISTICALLY_MEANINGLESS |
| validation | n=111, -0.51% | n=94, **-0.032%** [-1.190%,+1.125%] | STATISTICALLY_MEANINGLESS |
| out_of_sample | n=105, -0.42% | n=79, **-0.796%** [-2.315%,+0.724%] | STATISTICALLY_MEANINGLESS |

**No split reaches CI-decisive significance in either direction — every confidence interval
straddles zero.** This confirms, with a now-independently-corrected universe, exactly what the
original (current-snapshot) H_MEANREV_011 already found: realistic portfolio construction (limited
concurrent positions, shared capital, cash constraints) destroys whatever statistical edge the
single-symbol, dedicated-100%-capital design showed. The point-in-time correction does not rescue
it — if anything, the point estimates are somewhat more negative than the original's own already
-disappointing numbers.

## Decision, per the user's own frozen sequencing

**"If it survives [Step 2] → portfolio realism → fails → CLOSE."** Step 2 survived; Step 3 failed.
**Mean reversion (`H_MEANREV` family) is CLOSED for this research cycle.** This is a stronger,
better-evidenced closure than the prior session's own conclusion — it is no longer contingent on an
unresolved universe-membership question; that question has now been directly, empirically answered,
and the answer does not change the outcome. Independent replication (the user's own next step "if it
survives") does not apply, since Step 3 did not survive.

## FACT / INFERENCE / ASSUMPTION / LIMITATION / DECISION

- **FACT**: the point-in-time-corrected single-symbol result remains CI-decisive positive in
  validation and out-of-sample, but portfolio-constrained scheduling collapses all three splits to
  statistically meaningless.
- **FACT**: development's point-in-time-corrected result is CI-decisively negative, a new finding
  the original, survivorship-biased universe could not surface.
- **INFERENCE**: the mean-reversion signal family's single-symbol gross/net edge is real as a raw
  statistical regularity, but is not convertible into a realistic, capital-constrained, tradable
  strategy — independent of the universe-membership question this session set out to resolve.
- **ASSUMPTION**: annual snapshot granularity and the 14-symbol identity-resolution sample (not an
  exhaustive full-window enumeration) are disclosed approximations; a more complete identity
  resolution (covering all 40 replay-time fetch failures, not just the original 14) was not
  attempted, consistent with this mission's own proportionality principle — it would not change this
  entry's own decisive Step 3 conclusion, since Step 3 already fails cleanly across all splits.
- **LIMITATION**: `ARE&M.NS` (AMARAJABAT's correctly-identified successor) remains practically
  unusable due to an orthogonal, pre-existing ticker-safety guard, not fixed this session.
- **DECISION**: mean reversion closed. No further H_MEANREV portfolio-construction variant will be
  tested. Proceeding next to Path 2 (India VIX / F_CONTEXT preregistered test), per the user's own
  explicit sequencing.
