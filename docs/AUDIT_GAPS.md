# AUDIT_GAPS.md

Differences between **what the system is intended to do** (`PROJECT_GOAL_AND_ROADMAP.md`, the authoritative blueprint) and **what the system actually does** (verified by direct code reads, git history, and a five-way parallel source audit; full evidence with file:line citations is in `AUDIT_BASELINE.json`). No fixes are implemented here — this is a gap list only.

Each entry states the intent, the reality, and the size of the gap: **NONE** (fully met), **MINOR** (met with a disclosed limitation), **MODERATE** (partially met, real work remains), or **MAJOR** (not met / structurally absent).

---

## 1. Core product vision (roadmap §1–2: "continuously operating market intelligence platform")

**Intended**: continuous monitoring, real-time + historical data, NSE/other legitimate public sources, research, opportunity identification, deterministic analysis, AI reasoning, structured recommendations, dynamic sizing, full audit trail, continuous self-evaluation, learning, live dashboard.

**Actual**: every individual capability in this list exists in code and is exercised by the test suite (scanner, research, decision engine, sizing, prediction tracking, learning, dashboard). What does **not** exist is the "continuously operating" property itself — the system only runs when a human (or an external process supervisor not present in this repo) keeps `schedule loop` alive; there is no OS-level cron/daemon/systemd unit anywhere in the codebase.

**Gap: MODERATE.** Every building block is real; the "continuous" wrapper around them is a plain Python `while` + `sleep(interval)` loop with no restart-on-crash, no OS integration, and (in this environment) is not currently running at all.

---

## 2. "Monitoring NSE and other legitimate public market information sources" (roadmap §1, §10)

**Intended**: NSE official information, BSE official information, approved broker/data-provider APIs, tracked source reliability.

**Actual**: the sole real market-data/news/sector source anywhere in the codebase is `yfinance` (Yahoo Finance), plus Dhan for live NSE data (when credentials are configured). A repo-wide search for any NSE/BSE official API integration returns zero matches.

**Gap: MAJOR, but likely permanent, not a build gap.** No public official NSE/BSE/SEBI API is known to exist for a project at this scale — this constraint was already understood before this audit and is unlikely to close without a paid data-vendor relationship.

---

## 3. AI research agents (roadmap §14: "Market Research Agent, News Research Agent, Company Research Agent, Sector Research Agent, Macro Research Agent, Risk Analyst Agent")

**Intended**: six specialized AI research agents.

**Actual**: `README.md` itself states five of the six roadmap-suggested agents "turned out to already exist" under different names (the original `analyze` pipeline's technical/risk/critic/debate/supervisor agents, plus `research/summarizer.py`); `agents/decision_reviewer.py` (Phase 25) was built as the one genuine gap. A Macro Research Agent specifically was never built.

**Gap: MINOR.** Functionally covered under different naming; Macro Research remains unaddressed but was never flagged as high-priority.

---

## 4. AI output structure (roadmap §14: `bull_case`, `bear_case`, `risks`, `unknowns`, `evidence`, `confidence` fields)

**Intended**: every AI output structured with explicit bull/bear case, risks, unknowns, evidence, and a confidence score, distinguishing FACT / INFERENCE / UNCERTAINTY.

**Actual**: AI outputs (`DecisionNarrative`, `DecisionReview`, `SignalExplanation`, `ResearchSummary`) are real, structured Pydantic schemas, but none matches the roadmap's specific bull_case/bear_case/unknowns/confidence shape verbatim — they carry evidence and reasoning text but not that exact schema, and none is FACT/INFERENCE/UNCERTAINTY-tagged at the field level (the project's separate `[VERIFIED]/[TESTED]/[INFERENCE]/[HYPOTHESIS]` labeling discipline exists only in research *documentation*, not in the AI output data model itself).

**Gap: MINOR.** The spirit (structured, evidence-backed, non-hallucinated output) is met; the specific schema shape in the roadmap example is not.

---

## 5. Decision auditability — "Model Version" field (roadmap §9)

**Intended**: every decision record includes a `Model Version` alongside Strategy Version, Risk Configuration, etc., so a historical decision can be traced to exactly which AI model/prompt produced it.

**Actual**: deterministic config is fully versioned (`RiskConfig.version_id()`, `DecisionConfig.version_id()`, `CriticConfig.version_id()`, each a SHA-256 hash recorded on every decision/critic-assessment). **No AI-output schema anywhere carries a `model_version` or `prompt_version` field** — confirmed by direct read of all four AI-output schemas. Prompts themselves are also unversioned (no `PROMPT_VERSION` constant anywhere).

**Gap: MODERATE.** A real, specific, roadmap-named requirement that is unimplemented. If `qwen2.5-coder:7b` were ever swapped for a different model, or a prompt's wording changed, no historical decision record would show which version narrated it.

---

## 6. Dynamic capital (roadmap §3.4: "Capital must never be hardcoded")

**Intended**: capital is always user-configurable; the recommendation engine is independent of it.

**Actual**: independently re-verified end-to-end this session — `--initial-capital` and every risk-parameter CLI flag thread through `_risk_config_from_args()`/`_size_if_requested()` into a real `RiskConfig`/`Account`; `Account.equity` is a computed property, never a stored constant; no hardcoded capital figure was found feeding `RiskEngine` in any production code path (only argparse *defaults*, which are overridable).

**Gap: NONE.** This principle is fully and verifiably honored.

---

## 7. Opportunity scoring (roadmap §15: combined Technical/Market-Context/Sector/Liquidity/Volatility-Risk/Research scores → one Overall Opportunity Score)

**Intended**: a multi-factor composite score (Technical 82, Market Context 75, Sector 88, Liquidity 95, Volatility Risk 60, Research 72 → Overall 81/100, in the roadmap's own worked example).

**Actual**: `decision_engine/confidence.py` computes a real, deterministic confidence score (fraction of independent scanner factors agreeing with direction), and `market_intelligence/scanner.py` produces a `composite_score`/`trend_score`/`momentum_score`. There is **no single named "Liquidity Score"** in the scoring model — liquidity screening is a pass/fail gate that currently defaults to a no-op (per `README.md`), not a 0–100 sub-score contributing to a composite. Research evidence factors into the `decide` rule's corroboration check but is not itself a numeric sub-score.

**Gap: MODERATE.** A working composite/confidence mechanism exists; it does not match the roadmap's specific six-named-sub-score architecture, and liquidity is a disclosed no-op gate rather than a real, weighted input.

---

## 8. Dashboard "Live Market Overview" (roadmap §22: "Market: OPEN, NIFTY: Trend, BANK NIFTY: Trend, Market Regime: BULLISH")

**Intended**: a live top-of-dashboard market snapshot including both NIFTY and BANK NIFTY trend.

**Actual**: the dashboard (`dashboard/app.py`) shows market status, account state, positions, pending approvals, and (via `/intelligence`) scan candidates + decision labels + regime; `market_intelligence/regime.py` computes benchmark trend/volatility regime and sector strength. There is no confirmed dedicated BANK NIFTY-specific trend display distinct from the general regime report (not independently verified as present or absent by this audit — flagged as **unverified**, not confirmed missing).

**Gap: MINOR, partially unverified.** The regime/trend machinery exists; whether the dashboard specifically surfaces a BANK NIFTY line item was not confirmed either way.

---

## 9. "Live, understandable recommendations through a dashboard" — real-time push (roadmap §1, implicit in "live")

**Intended**: a live dashboard.

**Actual**: the dashboard is entirely server-rendered, read-on-page-load HTML with **no server-side WebSocket** anywhere in the codebase (confirmed by repo-wide grep — zero `WebSocketRoute`/`app.websocket` matches outside the unrelated outbound Dhan feed client). Every view requires a manual browser refresh to see updated state.

**Gap: MODERATE.** "Live" in the sense of "reflects current data when viewed" is true; "live" in the sense of "pushes updates without a refresh" is not implemented anywhere.

---

## 10. Prediction outcome states (roadmap §7.3: `PENDING, ACTIVE, TARGET_HIT, STOP_HIT, EXPIRED, INVALIDATED, PARTIAL_SUCCESS, MISSED_ENTRY, CANCELLED, INSUFFICIENT_DATA`)

**Intended**: 10 named outcome states.

**Actual**: `PredictionOutcomeState` (`predictions/models.py`) declares all of them, but `INVALIDATED`, `PARTIAL_SUCCESS`, `MISSED_ENTRY`, and `CANCELLED` are **never produced** by the actual evaluation logic — only `PENDING`/`ACTIVE`/`TARGET_HIT`/`STOP_HIT`/`EXPIRED`/`INSUFFICIENT_DATA` are ever assigned in practice. This is disclosed directly in the module's own docstring as a deliberate deferral (each remaining state requires a judgment call with no evidence-based rule yet), not a silent gap.

**Gap: MODERATE, but honestly disclosed in code, not hidden.** 4 of 10 roadmap states are structurally present but functionally dormant.

---

## 11. Continuous learning — Level 4/5 (roadmap §8: "adjust confidence estimation over time"; "Strategy weighting, Signal ranking, Confidence calibration... any automated model adaptation must be Versioned/Auditable/Reversible/Measured")

**Intended**: the system measures confidence calibration AND adjusts its own confidence estimation over time (Level 4), with any further adaptive behavior versioned/auditable/reversible.

**Actual**: `learning/profitability.py` and `decision_engine/confidence.py` genuinely **measure** calibration (fixed LOW/MEDIUM/HIGH bands checked against real outcomes) — this part is real and roadmap-compliant. `learning/adaptation.py` (Phase 38) produces an advisory-only `PromotionRecommendation` gated by two fixed thresholds (30+ resolved predictions, 10pp win-rate margin) and **explicitly never edits any config automatically** — promotion stays a manual step, correctly matching the roadmap's own "never silently modify production logic" rule (§8, §26). Whether confidence *estimation itself* (not just measurement) is ever adjusted based on this calibration data was not confirmed with high confidence by this audit.

**Gap: MINOR–MODERATE (partially unverified).** Level 1–3 (tracking, comparison, contextual learning) are solidly real. Level 4 (calibration measurement) is real; whether it closes the loop into adjusted confidence output requires a deeper read of `learning/adaptation.py` to confirm either way. Level 5 (feature importance, model comparison) is not implemented — consistent with the roadmap treating it as aspirational future work.

---

## 12. Market universe (roadmap §18: "NIFTY 50, NIFTY 100, NIFTY 500, Configured Watchlists")

**Intended**: index-membership-based universe modes alongside custom watchlists.

**Actual**: `market_data/universe.py` explicitly recognizes and **rejects** `nifty50`/`nifty100`/`nifty200`/`nifty500` mode strings via `UnsupportedUniverseModeError`, with the module's own docstring stating no live, verifiable index-membership source exists. Only a hand-curated "starter" watchlist and arbitrary symbol lists work today, explicitly labeled as not claiming NIFTY constituency.

**Gap: MODERATE, deliberately disclosed.** A named roadmap capability that is structurally recognized-but-refused rather than silently faked — an intentional, documented design choice, not an oversight, but still a real gap versus intent.

---

## 13. "No Blind AI Decisions" / "Required architecture" (roadmap §3.1)

**Intended**: every recommendation is Real Data + Deterministic Analysis + Historical Evidence + Market Context + Research Evidence + AI Reasoning + Risk Constraints → Structured Recommendation, with AI never itself deciding.

**Actual**: independently re-verified this session at the code level — `decision_engine/rules.py::classify()` is a pure function that sets `Decision.label` before any AI call happens; `narrate_decision()` takes the already-decided `Decision` as input and returns only a `str`, consumed via `model_copy(update={"narrative": ...})`, never `update={"label": ...}`. The same "narrate, never decide" boundary holds for `explain_signal`, `review_decision`, and `summarize_research` (each type-checked to be incapable of returning a decision-altering value). The one place an LLM *does* produce something decision-shaped is the legacy `analyze` pipeline's `supervisor_agent` (a `TradingDecision`) — but that pipeline is confirmed never wired into `paper/` or any broker adapter.

**Gap: NONE.** This is the project's most rigorously enforced architectural principle and it holds under direct code inspection.

---

## 14. "No Accidental Real Orders" / real order execution (roadmap §26, §27)

**Intended**: real order execution remains structurally disabled; this is a hard non-goal, not deferred work.

**Actual**: independently, exhaustively re-verified this session across every plausible code path (`live/dhan/broker_adapter.py`, `live/dhan/rest_client.py`, `live/pipeline.py`, `live/broker.py`, `live/approval.py`, `live/critic_gate.py`, `mcp_server/server.py`) — every order-mutating method raises unconditionally, no HTTP verb beyond GET exists in the Dhan REST client, a repo-wide grep for `requests.post/put/delete` returns zero matches anywhere in the entire repository, and a dedicated structural test (`tests/test_dhan_no_real_orders.py`) statically greps for both the disabled-adapter wiring and real Dhan order-endpoint URL fragments.

**Gap: NONE.** Fully, verifiably met — the single most safety-critical claim in the project checks out completely.

---

## 15. Data source tracking (roadmap §10: "Every external source should track: Source Name, Source Type, URL/API, Timestamp, Data Freshness, Reliability Status, Failure Status")

**Intended**: every external source's own health/freshness/reliability is tracked as first-class metadata.

**Actual**: `market_data/quality.py`, `live/freshness.py`, and `live/state_store.py`'s `feed_status` table genuinely track freshness/connection-state/last-price per source; `market_data/resilience.py` tracks retry/circuit-breaker metrics when `--resilient` is opted in. This is real, working infrastructure — not fully universal (the `--resilient` metrics layer is opt-in, not applied to every source uniformly; Dhan's own health tracking is bespoke rather than routed through the same `ProviderMetrics` shape).

**Gap: MINOR.** The intent is substantially met; consistency across all sources (opt-in vs. always-on, and a shared metrics shape) is not fully uniform.

---

## 16. Continuous background operation schedule (roadmap §19: "Pre-Market / Market Open / Market Hours / After Market / Night" 24-hour intelligence cycle)

**Intended**: a conceptual 24-hour intelligence cycle.

**Actual**: `scheduler/config.py` implements exactly this shape — `pre_market` (08:45–09:15), `market_open` (09:15–09:30), `intraday` (09:30–15:15, hourly), `pre_close` (15:15–15:30), `post_market` (15:30 onward, evaluate+learn) — a faithful, working match to the roadmap's own named windows. What's missing is the "Night: Research + analytics + learning" slot specifically, and (as covered in gap #1) the OS-level always-on wrapper around the whole cycle.

**Gap: MINOR** for the slot design itself (very close to roadmap intent); **MODERATE**, restated from gap #1, for the missing OS-level continuity wrapper.

---

## 17. Phase Execution Rules — branch hygiene (roadmap §24, Step 3/11: "Create Branch... Never merge automatically unless explicitly authorized")

**Intended**: implicit expectation of a normal branch lifecycle (create, work, merge/close).

**Actual**: 150+ branches exist locally and on the remote, the overwhelming majority corresponding to already-completed, already-merged phases and features, never deleted.

**Gap: MINOR, hygiene only.** No functional impact; a housekeeping gap against normal branch-lifecycle expectations, not against any roadmap requirement stated in words.

---

## 18. Evidence classification discipline (roadmap §25: `REAL SERVICE VERIFIED / LOCAL-INTEGRATION VERIFIED / LOCAL-DETERMINISTIC-TEST VERIFIED / STRUCTURALLY VERIFIED / NOT VERIFIED / BLOCKED`)

**Intended**: every report distinguishes evidence by exactly these six levels.

**Actual**: `README.md` and `docs/PHASE_HISTORY.md` consistently use this exact vocabulary (e.g., "REAL SERVICE VERIFIED" for the Phase 16 Dhan connectivity claims, "NOT VERIFIED" for the Dhan live-signal end-to-end claim). This discipline is genuinely followed in practice, not just stated.

**Gap: NONE.**

---

## 19. Orphaned/incomplete infrastructure not named in the roadmap but discovered during this audit

These are implementation-level gaps the roadmap doesn't explicitly name (since the roadmap describes intended behavior, not internal code organization) but are worth recording because they represent **built-but-disconnected** work — the closest thing to "broken promises" at the code level:

- `strategy/experiment_store.py::ExperimentRegistryStore` — fully implemented and tested, never wired into any CLI command. `data/experiment_registry.db` exists on disk with no traceable code path that could have produced it.
- `experiments/store.py`'s default database path (`data/experiments.db`) does not exist on disk even though its CLI commands (`experiment start/end/list/compare/recommend`) are fully wired — suggesting this specific pipeline has never actually been run end-to-end against its own default configuration in this checkout.
- RAG/ChromaDB (`rag/`, `vectorstore/`) is real, populated, and working — but reachable only from the legacy `analyze` command; none of the Phase 18-onward market-intelligence/decision pipeline uses it, despite the roadmap's own AI Research Layer (§14) implying research evidence and AI reasoning are integrated together.

**Gap: MODERATE**, purely at the "does every built thing actually connect to something" level, separate from whether the roadmap's stated *capabilities* exist.

---

## Summary table

| # | Area | Gap size |
|---|---|---|
| 1 | Continuous operation (OS-level always-on) | MODERATE |
| 2 | Official NSE/BSE data source | MAJOR (structural, likely permanent) |
| 3 | Six named AI research agents | MINOR |
| 4 | AI output schema shape (bull/bear/unknowns/confidence) | MINOR |
| 5 | AI model/prompt versioning on decision records | MODERATE |
| 6 | Dynamic capital, never hardcoded | NONE |
| 7 | Multi-factor named opportunity score (incl. Liquidity Score) | MODERATE |
| 8 | Dashboard BANK NIFTY-specific display | MINOR (unverified) |
| 9 | Live (push-based) dashboard updates | MODERATE |
| 10 | Full prediction-outcome state set | MODERATE (disclosed) |
| 11 | Closed-loop confidence-estimation adjustment | MINOR–MODERATE (partially unverified) |
| 12 | NIFTY 50/100/200/500 universe modes | MODERATE (disclosed) |
| 13 | No-blind-AI-decisions architecture | NONE |
| 14 | Real order execution disabled | NONE (fully met, by design) |
| 15 | Uniform external-source health/freshness tracking | MINOR |
| 16 | 24-hour intelligence-cycle schedule shape | MINOR (slots) / MODERATE (always-on wrapper) |
| 17 | Branch hygiene | MINOR |
| 18 | Evidence-classification vocabulary discipline | NONE |
| 19 | Orphaned/disconnected built infrastructure | MODERATE |

**Overall assessment**: the project's safety-critical intent (no real orders, no blind AI decisions, capital never hardcoded, evidence-classified reporting) is **fully and verifiably met**. The largest genuine gaps are architectural/operational rather than safety-related: no OS-level continuous-operation wrapper, no AI-output versioning, a few pieces of fully-built infrastructure never wired to a live entry point, and several roadmap capabilities (index-membership universes, some prediction-outcome states, a uniform multi-factor opportunity score) that are deliberately and honestly deferred rather than silently faked.
