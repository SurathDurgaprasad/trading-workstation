# LLM Contribution Audit

Strategy science mission, Phase 10. Answers one question honestly, with
code-level evidence: **can LLM output ever influence a real trading
decision, risk approval, or order fill in this codebase — or is it
narration only?**

This is a point-in-time audit (dated against commit history at the time it
was written). Source of truth is always the code and tests, not this
document — re-verify before relying on a specific claim if the relevant
files have since changed.

## Verdict

**No.** Every code path that reaches `RiskEngine.evaluate()` or a real
`PaperTradingEngine`/backtester fill is driven by deterministic code, proven
both by direct reading and by automated tests (existing and new — see
below). Every place an LLM is actually invoked returns a schema with no
field capable of holding a price, quantity, or approval flag, and none of
those outputs are read back into the deterministic decision path.

## The two paths that can open a real (paper) position

1. **`strategy/baseline.py`'s `TrendMomentumBaseline`** — the strategy
   actually used by `backtest`, `paper run`, `live-sim`, `paper-live`
   (`main.py`'s own `--strategy` default everywhere is
   `trend_momentum_baseline`; `strategy/registry.py` has exactly one
   registered strategy). `generate_signal()` reads only indicator columns
   (`sma_20`, `sma_50`, `rsi_14`, `macd`, `macd_signal`, `atr_14`,
   `volume_trend`) and fixed constants (`STOP_ATR_MULTIPLIER`,
   `TARGET_RISK_REWARD`) — no I/O, no randomness, no LLM. Feeds
   `risk/engine.py`'s `RiskEngine.evaluate()` directly.

2. **`decision_engine` → `risk/sizing.py` bridge**, reachable only via the
   explicitly opt-in `shadow-run --paper-execute` (off by default, gated by
   three companion flags in `main.py`). `decision_engine/rules.py`'s
   `classify()` computes a `Decision.label` (BUY/WATCH/AVOID/EXIT/NO_ACTION)
   purely from `CandidateScore` (deterministic scanner output) and
   `RiskContext` — no LLM call in its own signature or body.
   `decision_engine/confidence.py`'s `compute_confidence()` is the same:
   pure arithmetic over `CandidateScore` factor fields. `risk/sizing.py`'s
   `build_signal_for_buy()`/`size_decision()` turn that label into a real
   `Signal`, which reaches the same `RiskEngine.evaluate()`.

Both paths terminate in the SAME deterministic `RiskEngine.evaluate()`
(`risk/engine.py`) and the SAME deterministic fill/exit mechanics
(`backtesting/execution.py`'s `check_exit`/`close_trade`, shared unmodified
by `paper/engine.py`) — neither of which imports `agents`, `llm`, `graph`,
or any LLM-derived value.

## Where the LLM actually IS invoked, and why it can't reach a decision

| LLM call site | Returns | Can it hold a price/quantity/approval? | Where its output goes |
|---|---|---|---|
| `agents/supervisor_agent.py` (`schemas.decision.TradingDecision`) | `action`, `confidence`, `reasoning` | No execution field | Printed by `main.py`'s `analyze` command only, under "AI market analysis only — not a validated trading signal." Never imported by `paper/`, `backtesting/`, `risk/`, `strategy/` (see `test_execution_packages_never_import_the_agents_graph_pipeline_schema`, added this phase). |
| `decision_engine/engine.py`'s `narrate_decision()` (deferred `agents.analyst` import) | `DecisionNarrative.narrative: str` | No — a single string field | Stored in `Decision.narrative`, rendered in the dashboard's separate "AI EXPLANATION" block; never read back by `classify()`, `build_signal_for_buy()`, or `size_decision()`. |
| `agents/signal_explainer.py`'s `explain_signal()` | `SignalExplanation` (`supporting_evidence`, `contradicting_evidence`, `narrative`) | No | Printed in `paper-live`'s human-approval loop; recorded via `live/pipeline.py`'s `mark_ai_explained()`, a lifecycle-state transition only. `approve_pending`/`reject_pending` take `(signal_id, reason)` — no quantity/price/approval override parameter exists to receive it even in principle. |

The signal lifecycle state machine (`live/approval.py`) structurally
forbids `AI_EXPLAINED → EXECUTED` — only `→ PENDING_HUMAN_APPROVAL →
HUMAN_APPROVED → EXECUTED` is legal
(`tests/test_approval_state_machine.py::test_human_approval_mode_forbids_ai_explained_shortcut_too`).

## What already proved this (before this phase)

- `tests/test_backtest_llm_independence.py` — AST-based import scan: none of
  `backtesting/`, `strategy/`, `risk/`, `market/` import `agents`, `llm`,
  `graph`, `langgraph`, `langchain_core`, `langchain_ollama`, `ollama`, or
  `rag` — a structural guarantee, not a runtime mock.
- `tests/test_e2e_deterministic_pipeline.py` — two independent runs of the
  real indicator math → real strategy → real `RiskEngine` → real
  `run_backtest`, on identical input, produce byte-identical output.
- `tests/test_signal_explainer.py`, `tests/test_mcp_server.py` — the AI
  explanation schema structurally cannot hold a revised entry/stop/target/
  quantity.
- `tests/test_approval_security.py` — `approve_pending`/`reject_pending`
  signatures have no execution-override parameter; passing `quantity=`
  raises `TypeError`.
- `tests/test_dashboard_intelligence.py` — the dashboard's AI narrative
  renders in a block visually and structurally separate from the
  deterministic rationale.

## Gaps this phase closed

The audit that produced this document found the deterministic/LLM boundary
held everywhere it checked, but flagged two specific gaps where the
guarantee existed only by inspection, not by a named, permanent test.
`tests/test_decision_engine_llm_independence.py` (added this phase) closes
both:

1. **`decision_engine` was not covered by the existing AST-import-scan.**
   The package is *mixed* — `decision_engine/engine.py`'s own
   `narrate_decision()` legitimately imports the LLM layer (deferred,
   inside the function) for narration, so the whole package cannot be
   scanned uniformly the way `backtesting`/`strategy`/`risk` are. This phase
   adds a scan scoped to the two files that actually determine
   `Decision.label` and feed the real-execution bridge —
   `decision_engine/rules.py` and `decision_engine/confidence.py` — plus a
   positive-control test confirming `engine.py` *does* still import the LLM
   layer (so the "why we scan only two files, not the package" reasoning
   stays correct if the code changes).

2. **No test asserted, by name, that `TradingDecision` never reaches
   execution.** True by inspection (nothing imports `schemas.decision`
   anywhere in `backtesting/`, `strategy/`, `risk/`, `paper/`), but not
   previously locked in as an explicit, named regression test.

3. **`classify()`'s signature was an unlocked structural guarantee.** It
   currently cannot be influenced by LLM output only because it doesn't
   accept a narrative/LLM-shaped parameter at all — true today, but nothing
   previously forced a deliberate decision if a future change added one.
   `test_classify_signature_has_no_llm_or_narrative_derived_parameter`
   fixes that.

## One honest caveat this document does not paper over

The guarantee above is a **code-enforced ceiling on what the LLM can
directly write** — not a guarantee against operator influence. A human
approving a `PENDING_HUMAN_APPROVAL` signal in `paper-live` may have just
read a persuasive AI narrative (`_try_ai_explain` in `main.py`) or the
dashboard's AI explanation before deciding APPROVE/REJECT. No code change
can rule out a human being swayed by AI-generated text; this audit only
establishes that the LLM cannot itself set price, quantity, or approval —
the human in the loop always can, by definition, since human approval is
the entire point of that gate.
