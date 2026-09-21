# Mean-Reversion Chain Audit (Priority 1) — H_MEANREV_006 through H_MEANREV_012

Verified directly against `quant_research/mean_reversion_portfolio.py`,
`docs/research/H_MEANREV_011_PORTFOLIO_CONSTRUCTION_PREREGISTRATION.md`, and the registry's own
`H_MEANREV_011`/`H_MEANREV_012` evidence text.

## Scheduling mechanism — read directly against source, VERIFIED sound

`_run_schedule` (the shared accept/reject engine both `schedule_portfolio` and
`schedule_portfolio_ranked` delegate to): for each chronologically-ordered candidate event, first
releases any position whose already-precomputed exit time has passed, then accepts iff (a) the symbol
has no open position, (b) fewer than `MAX_CONCURRENT_POSITIONS` are open, (c) `capital_per_position`
does not exceed current cash — using **only information available at the candidate's own signal_date**.
The trade's own outcome (`compute_fixed_notional_trade`) is computed **only after acceptance**, never
consulted during the accept/reject decision. This is the correct no-look-ahead pattern; confirmed
directly against the function body, not just the docstring's own claim about itself.

## Reproducibility — partially resolved

No standalone runner script for H_MEANREV_011/012 is committed to the repo (only the module + tests +
preregistration doc + registry text exist) — flagged in STATE.json as an open reproducibility gap.
However: **H_MEANREV_012's own Candidate A (the unmodified control) independently re-derived
H_MEANREV_011's exact cited numbers** — 555/111/105 accepted trades, +43460.67/-7852.26/-4789.98 gross
P&L, `PromotionVerdict.REJECTED` in all three splits — a genuine independent reproduction, done by a
DIFFERENT experiment's own code path, not a copy-paste of the same run. This materially reduces (does
not eliminate) the reproducibility concern: the *result* has been cross-checked twice, even though the
exact script that first produced it in H_MEANREV_011 is not itself preserved as a runnable artifact.

## THE central question: are rejected candidates systematically different from accepted ones?

This is answered **indirectly but with a real, controlled, pre-registered experiment** — not directly
by comparing individual rejected-vs-accepted candidates' own forward returns (that specific analysis
was not run and remains open, see below), but by testing the most obvious candidate explanation head-on:

**H_MEANREV_012's test**: replace H_MEANREV_011's arbitrary chronological+alphabetical tie-break
(among same-day candidates competing for the same slot) with `zscore_close_20` ranking — i.e.,
deliberately prefer the MORE OVERSOLD (by this family's own established measure of signal strength)
candidate when multiple compete for one slot.

**Result: ranking made validation performance MATERIALLY WORSE, not better.**

| Split | Candidate A (alphabetical) net mean | Candidate B (zscore-ranked) net mean | Direction |
|---|---:|---:|---|
| development | +0.10% | +0.26% | slightly better, CIs overlap (not distinguishable) |
| validation | -0.51% | -1.13% | **materially worse** (gross P&L -7852 -> -22473, ~3x more negative) |
| out-of-sample | -0.42% | -0.46% | essentially flat |

Win rate fell under ranking in **every** split (50.1%->49.0% dev, 42.3%->34.6% val, 48.6%->40.4% oos).

**What this tells us**: the specific hypothesis "rejected candidates are simply the WEAKER signals by
the family's own established strength measure, and accepting the strongest ones instead would recover
the edge" is **directly tested and does not hold** — it makes the primary forward-looking split (val)
worse. This means the accepted-vs-rejected difference the audit brief asked about is **not primarily a
"we're keeping the mediocre ones and discarding the good ones" problem along the zscore dimension.**

**What remains genuinely open, not yet tested**: whether accepted-vs-rejected differs along a
*different* dimension — specifically the DAY-LEVEL clustering context itself. The preregistration's own
[INFERENCE] (not yet [TESTED]) is that heavy capacity-driven rejection (45-50% of all candidates,
before cash) implies many symbols become oversold SIMULTANEOUSLY, consistent with broad market-wide
stress rather than independent idiosyncratic dips — and if true, whichever 4 candidates happen to win
the slot on a heavily-clustered day are themselves likely correlated with each other (all weak in the
same bad environment), not genuinely diversified. This is stated as inference in the preregistration and
explicitly **not** measured directly (pairwise correlation of concurrently-open positions was never
computed — disclosed as a real scope gap, not hidden). **This is the one genuinely new, well-motivated,
not-yet-run analysis this audit identifies**: bucket ALL candidate events (accepted and rejected alike)
by same-day cluster size (how many symbols fired the signal on that date) and compare mean forward
h10 return between low-clustering days and high-clustering days. If high-clustering-day candidates
underperform low-clustering-day candidates regardless of which specific symbol wins the slot, that
would directly confirm the clustering/correlation inference and explain why neither the arbitrary
tie-break NOR a strength-based re-ranking fixes the portfolio-level result — the problem would be which
DAYS get selected into the portfolio, not which SYMBOLS. This analysis uses only already-computed
signal/return data (`collect_candidate_events` + each candidate's own forward return, available without
running a new backtest architecture) and would be a genuinely incremental, non-curve-fitting piece of
evidence, not a parameter retune.

## Verdict-mapping precision (spot-checked)

`H_MEANREV_011`'s own text is careful to distinguish itself from `H_MEANREV_009`: "every split's CI
straddles zero substantially... the honest characterization is 'underpowered and mixed-direction,' not
'confirmed harm.'" Confirmed this distinction is real and load-bearing, not just softening language —
`PromotionVerdict.REJECTED` here stems from the mechanical rule ("no split confidently
NEGATIVE_PERFORMANCE, but point estimates mixed in sign") which is a **different** decision path than
`H_MEANREV_009`'s `NEGATIVE` (all three splits CI-decisively negative). Both map to
`HypothesisStatus.REJECTED` in the registry, which is accurate per that status's own definition
("results contradict the hypothesis") but **does lose this distinction at the one-word-status level** —
a reader scanning only statuses, not evidence text, would not see that H_MEANREV_009 and H_MEANREV_011
represent very different strengths of evidence. Not a bug, but worth naming for the final report's
own "how were multiple hypotheses handled / how confident should we be" section.

## Tail-risk finding — VERIFIED, a genuine, disclosed improvement

H_MEANREV_010 Candidate 2 (single position, 100% capital): worst trade -65% of TOTAL portfolio capital.
H_MEANREV_011 (4-position, 25%-capital-per-slot): worst trade -9.68% of TOTAL portfolio capital
(-38.7% of that one position's own capital — the position-level fat tail is unchanged, consistent with
`H_MEANREV_008`'s own risk-characterization finding; only the portfolio-level concentration improved).
This is a real, quantified, and correctly-attributed improvement — not conflated with "the strategy
works now," which the evidence does not support.

## Priority-1 status: substantially advanced, one clear next step identified

Not yet done: the day-level clustering/correlation analysis described above. This is the single
highest-value next action for the mean-reversion thread specifically — it directly tests the
preregistration's own [INFERENCE] (currently unverified) that clustering, not the tie-break rule or
signal strength, is the actual mechanism, and it requires no new backtest engine, no strategy change,
and no capital-constraint loosening (respecting the user's own explicit "don't loosen 25% until trades
get through" and "don't curve-fit" instructions).
