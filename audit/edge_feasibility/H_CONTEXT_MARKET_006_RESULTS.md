# H_CONTEXT_MARKET_006 — Results: NIFTY Volatility Regime Does NOT Explain the Era Sign Reversal

Executed exactly per `docs/research/H_CONTEXT_MARKET_006_VOLATILITY_REGIME_PREREGISTRATION.md`, no
deviation. Script: `audit/edge_feasibility/scripts/h_context_market_006_volatility_regime.py`.

## Cross-check (validity confirmation)

The unconditioned `H_CONTEXT_MARKET_002` control was independently recomputed by this script and
matches `H_CONTEXT_MARKET_005`'s own already-recorded numbers **exactly**: development n=1068
-0.475%/-0.904% (CI-decisive negative), validation n=537 +0.794%/+1.496% (CI-decisive positive),
out-of-sample n=760 +0.531%/+0.946% (CI-decisive positive). This confirms the script faithfully
reuses the frozen condition/universe/splits with zero silent deviation.

## Primary table — bucketed by NIFTY's own volatility regime (h10, the pre-declared primary horizon)

| Split | HIGH_VOLATILITY | NORMAL_VOLATILITY | LOW_VOLATILITY |
|---|---|---|---|
| development | n=63, **-3.895%** [-5.66%,-2.13%] (uncorrected) — even MORE negative than control | n=966, **-0.743%** [-1.13%,-0.35%] — same sign/magnitude as control | n=0 — INSUFFICIENT_DATA |
| validation | n=0 — INSUFFICIENT_DATA | n=537, **+1.496%** [+1.12%,+1.87%] — identical to control (bucket ≈ full sample) | n=0 — INSUFFICIENT_DATA |
| out_of_sample | n=115, -0.107% [-1.05%,+0.84%] — NOT decisive, flat | n=645, **+1.134%** [+0.75%,+1.52%] — same sign/magnitude as control | n=0 — INSUFFICIENT_DATA |

All figures also computed at a `family_size=3` Bonferroni-corrected CI (see script output) — every
CI-decisive cell above remains CI-decisive under that correction; the finding below does not depend
on which correction level is used.

## Interpretation

**LOW_VOLATILITY is structurally, near-tautologically empty in every split** (n=0 across all three):
NIFTY TRENDING_DOWN and NIFTY LOW_VOLATILITY are, unsurprisingly, close to mutually exclusive —
falling markets are rarely calm markets. This specific joint condition cannot be tested with this
regime variable at all, a real, disclosed structural limitation of testing a volatility bucket
inside an already-trend-conditioned population, not a data-availability failure.

**NORMAL_VOLATILITY — the dominant, best-powered bucket in every split (966/537/645 of the
1068/537/760 total observations, i.e. it essentially IS the control population)** — reproduces
`H_CONTEXT_MARKET_002`'s own exact era-instability pattern unchanged: decisively negative in
development, decisively positive in validation and out-of-sample. **The regime variable does not
alter the already-observed instability inside the population that carries almost the entire
result.**

**HIGH_VOLATILITY — where powered (development n=63, out-of-sample n=115; validation n=0)** —
points AWAY FROM, not toward, a stabilizing explanation: in development it is CI-decisively MORE
NEGATIVE than the control (-3.90% vs. -0.90%), and in out-of-sample it is flat/non-decisive
(-0.11%, CI includes zero) rather than reproducing the control's own decisive positive out-of
-sample result. There is no consistent cross-split direction for this bucket either.

## Verdict, against the pre-registered decision rule (§7)

- **Outcome 1 (genuine stable conditional effect)**: NOT MET. No bucket shows a consistent
  cross-split direction that would explain (rather than merely reproduce) the era instability;
  the one bucket with a clean signal (HIGH_VOLATILITY in development) points the wrong direction.
- **Outcome 4 (insufficient sample)**: applies ONLY to the `LOW_VOLATILITY` cell specifically (a
  structural near-emptiness, disclosed above) — it does NOT apply to the entry as a whole, since
  the dominant `NORMAL_VOLATILITY` bucket is well-powered in all three splits and gives a clear,
  decisive answer.
- **Outcome 2 (unstable effect with no explanatory regime): MET.** The dominant, best-powered
  bucket reproduces the exact same unexplained sign-reversal pattern `H_CONTEXT_MARKET_005` already
  found in the unconditioned data. NIFTY's own realized-volatility regime does not explain it.

**Per the user's own B5 instruction ("If OOS fails, close the hypothesis"): this specific
explanatory hypothesis is closed.** NIFTY's own volatility regime is REJECTED as the explanation for
F_CONTEXT's era sign reversal. This does **not** reopen or rewrite `H_CONTEXT_MARKET_002`'s,
`_004`'s, or `_005`'s own historical verdicts — it answers a narrower, genuinely new question this
entry alone was designed to ask.

## What was NOT pursued (disclosed, not silently abandoned)

India VIX regime (`build_india_vix_regime_series`, already-existing, already-tested infrastructure,
named explicitly in this entry's own preregistration as a reserved, not-yet-tested alternative) was
NOT tested in this entry, per the preregistration's own explicit "no second regime variable added
if this one is inconclusive — a follow-up entry, separately preregistered, would be required"
constraint. Testing it now, in the same breath as this negative result, would be exactly the kind of
post-hoc pivot this project's own discipline exists to prevent. It remains available for a future,
separately-scoped, separately-preregistered follow-up if a human decision is made to pursue it —
matching how Phase A's own engineering gap was left as an explicit, disclosed, not-automatically
-pursued option rather than a silently dropped one.
