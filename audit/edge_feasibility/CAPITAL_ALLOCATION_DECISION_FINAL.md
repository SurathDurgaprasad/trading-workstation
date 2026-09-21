# Capital-Allocation Decision: Both Remaining Paths Closed — Stop This Research Tree

Executed per the user's own explicit sequence (2026-09-21, continuing from `a62f58b`):

```text
Corporate-action / security-identity layer
  └── Can reconstruct (partially, disclosed) → H_MEANREV_010 exact frozen replay
        ├── survives (validation + out-of-sample remain CI-decisive positive)
        └── portfolio realism → FAILS (all three splits statistically meaningless)
              └── CLOSE MEAN REVERSION

India VIX / F_CONTEXT preregistered test
  └── FAILS (dominant bucket reproduces the same unexplained instability)
        └── CLOSE F_CONTEXT

BOTH FAIL → STOP THIS RESEARCH TREE
```

## Path 1 — Mean reversion: CLOSED

Full writeup: `PATH1_MEAN_REVERSION_POINT_IN_TIME_CLOSURE.md`. Summary: a real corporate-action/
security-identity layer was built and verified (`quant_research/security_identity_map.py`, 8 of 14
sampled symbols recoverable via a web-search-confirmed rename/merger-survivor mapping, 3 confirmed
genuinely non-recoverable, 3 unresolved). The frozen H_MEANREV_010 single-symbol replay, run once
against a real, dated, identity-resolved point-in-time universe, **survived** its own pre-registered
decision rule (validation +1.24%, out-of-sample +0.82%, both still CI-decisive) — with a genuinely
new, economically coherent finding along the way: development flips to CI-decisively NEGATIVE
(-0.89%) once formerly-eligible-but-later-defaulted companies (DHFL, JP Associates, Reliance
Capital, several PSU banks) are correctly included, exposing survivorship bias the original analysis
had silently benefited from. But realistic portfolio construction (H_MEANREV_011's own frozen
4-position scheduler, unmodified, applied to the same corrected universe) **failed cleanly** — no
split reaches CI-decisive significance. Registry: `H_MEANREV_014`, REJECTED.

## Path 2 — F_CONTEXT: CLOSED

Full writeup: `H_CONTEXT_MARKET_007_RESULTS.md`. Summary: India VIX regime, the one explanatory
variable explicitly reserved after NIFTY's own realized-volatility regime failed
(`H_CONTEXT_MARKET_006`), was tested once, preregistered, corrected for the research family. Result:
the dominant bucket (NORMAL, ~90-100% of the population) reproduces the exact same unexplained era
-instability found before. One bucket (ELEVATED VIX) showed a genuinely interesting, directionally
-consistent negative pattern in the two splits where it was measurable — disclosed honestly, not
suppressed — but validation was entirely unmeasurable for that bucket, so it does not satisfy the
pre-registered decision rule's explicit confirmability requirement. Per the user's own instruction,
this is the final pre-declared regime variable; no third one is sought. Registry:
`H_CONTEXT_MARKET_007`, REJECTED.

## Decision

**Both paths the user identified as worth serious effort have now reached a defensible, decisive,
negative conclusion, each independently verified rather than assumed.** This is not a weaker version
of the prior session's "no demonstrated edge" finding — it is a stronger one: the two open
dependencies that prior finding rested on (an unresolved universe-membership question for
H_MEANREV; an untested regime explanation for F_CONTEXT) have now been directly, empirically
resolved, and neither resolution changed the outcome.

**Per the user's own explicit instruction: do not create H_MEANREV_015/H_CONTEXT_MARKET_008, do not
tune the baseline strategy, do not loosen risk controls, do not keep testing regime variables.**
None of those actions are taken. This research tree stops here.

## What this means for the project going forward

The registry now stands at 59 hypotheses: 36 REJECTED, 22 INCONCLUSIVE, 1 SUPPORTED (a confirmed
non-edge). Both hypothesis families that ever showed genuinely promising raw statistics
(`F_MEANREV`, `F_CONTEXT`) have been carried to their own honest, evidence-based termination —
`F_MEANREV` on portfolio-construction and (now-resolved) universe-integrity grounds; `F_CONTEXT` on
temporal/regime-instability grounds that two independent, pre-registered explanatory attempts could
not resolve.

Per the user's own framing, the project's research question has now been answered as precisely as
this data/market/timeframe combination allows: **this specific research problem does not currently
contain a demonstrated edge sufficient to justify further engineering or capital investment.** A
genuinely different research program — a materially different information source (order-flow/
microstructure, options-derived signals, higher-resolution breadth data, corporate-event/news
information, cross-asset signals, or a different holding horizon) — would be a new research program,
not a variant of this one, and is a decision for the user to make, not something this session starts
on its own initiative.

## Engineering summary

- New, tested infrastructure (reusable regardless of this conclusion): `quant_research/
  point_in_time_fno_universe.py` (14 tests), `quant_research/security_identity_map.py` (14 tests).
- Zero production strategy/RiskEngine/order-execution code modified. Real order execution remains
  disabled throughout.
- Live fleet: unchanged, not the research objective, checked non-disruptively only.
- Full regression run before committing (see commit message for pass/fail counts).

## The project remains paper-only until a new research premise or materially better data emerges.
