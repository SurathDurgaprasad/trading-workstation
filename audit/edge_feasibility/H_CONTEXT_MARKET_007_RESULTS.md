# H_CONTEXT_MARKET_007 — Results: India VIX Regime Does NOT Explain the Era Sign Reversal Either

Executed exactly per `docs/research/H_CONTEXT_MARKET_007_VIX_REGIME_PREREGISTRATION.md`, no
deviation. Script: `audit/edge_feasibility/scripts/h_context_market_007_vix_regime.py`.

## Cross-check (validity confirmation)

The unconditioned `H_CONTEXT_MARKET_002` control reproduces `H_CONTEXT_MARKET_005`'s/`006`'s own
already-recorded numbers **exactly**: development n=1068 -0.475%/-0.904%, validation n=537
+0.794%/+1.496%, out-of-sample n=760 +0.531%/+0.946%.

## Primary table — bucketed by India VIX regime (h10, primary)

| Split | ELEVATED | NORMAL | DEPRESSED |
|---|---|---|---|
| development | n=59, **-4.273%** [-6.54%,-2.01%] — even MORE negative than control | n=951, **-0.705%** [-1.09%,-0.32%] — matches control | n=19 — INSUFFICIENT_DATA |
| validation | n=0 — INSUFFICIENT_DATA | n=537, **+1.496%** [+1.12%,+1.87%] — identical to control | n=0 — INSUFFICIENT_DATA |
| out_of_sample | n=47, **-2.893%** [-3.58%,-2.21%] — CI-decisively NEGATIVE, opposite of control's own positive | n=695, **+1.284%** [+0.91%,+1.66%] — matches control | n=18 — INSUFFICIENT_DATA |

All CI-decisive cells above remain CI-decisive under both `family_size=2` and `family_size=17`
corrections (see script output) — the finding does not depend on correction stringency.

## Interpretation

**DEPRESSED VIX is structurally near-empty in every split** (n=19/0/18) — India VIX rarely sits
meaningfully below its own trailing average while NIFTY is simultaneously trending down, an
unsurprising co-occurrence pattern, not a data gap.

**NORMAL — the dominant, best-powered bucket (951/537/695, i.e. ~89-100% of the population in every
split) — reproduces the control's own exact era-instability pattern unchanged**: negative
development, positive validation and out-of-sample. As with the volatility-regime test, the
population that carries almost the entire result remains unexplained by this variable.

**ELEVATED — the one genuinely interesting observation**: where measurable (development n=59,
out-of-sample n=47), ELEVATED VIX is CI-decisively NEGATIVE in BOTH splits — a directionally
CONSISTENT pattern, unlike NORMAL's own instability. This is a real, disclosed, intriguing signal.
**However, validation is entirely unmeasurable for this bucket (n=0)** — the pre-registered decision
rule (§7) explicitly requires "at least validation and out-of-sample CI-decisive in that direction"
for Outcome 1, and validation simply cannot be evaluated here. The pattern cannot be confirmed across
all three splits as pre-specified, regardless of how suggestive the two measurable splits look.

## Verdict, against the pre-registered decision rule (§7)

- **Outcome 1 (genuine stable conditional effect)**: NOT MET. ELEVATED's own consistent-negative
  pattern is suggestive but fails the explicit "validation CI-decisive" requirement (validation is
  unmeasurable, not merely inconclusive) — the rule was written to require confirmable evidence in
  all three splits, not two out of three plus a gap.
- **Outcome 4 (insufficient sample)**: applies only to the `DEPRESSED` cell specifically (structural
  near-emptiness) and to `ELEVATED`'s own validation cell — not to the entry as a whole, since
  `NORMAL` is well-powered in all three splits and gives a clear, decisive answer.
- **Outcome 2 (unstable effect with no explanatory regime): MET**, on the strength of the dominant
  bucket. India VIX regime does not explain F_CONTEXT's era sign reversal any more than NIFTY's own
  realized-volatility regime did.

**Per the user's own explicit instruction ("if it fails: close F_CONTEXT"): this is the second and
final pre-declared regime variable to fail. F_CONTEXT is now CLOSED.** No third regime variable will
be sought, matching the user's own explicit "not: try different regimes until something works"
instruction. `H_CONTEXT_MARKET_002/004/005/006`'s own historical verdicts remain unmodified.

## Disclosed, unresolved secondary observation (not pursued further)

ELEVATED VIX's own consistent-negative pattern across the two measurable splits is a genuinely
interesting, real finding that this entry cannot fully confirm or refute given validation's own
missing data. It is disclosed here as an open curiosity, not as grounds for a third test — pursuing
it further would require either a longer history (more validation-period ELEVATED-VIX observations)
or a different universe, both out of this entry's own frozen scope, and both would require a fresh,
separately-scoped, separately-preregistered follow-up if ever pursued — a human resourcing decision,
not an automatic next step.
