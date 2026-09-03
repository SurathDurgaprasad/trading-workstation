# Phase History

This project was built in numbered phases, each with a forensic audit and a
written report. This file is an index of that history and states plainly,
for each phase, whether its report exists as a file in this repository or
only as an externally-hosted Claude Artifact.

**Source of truth for behavior is always the code and tests in this
repository, not these reports.** The reports are narrative/audit records of
*why* something was built a given way and what was found at the time; they
are not re-verified each time the code changes.

## What "preserved" means here

The files under [`docs/phases/`](phases/) are the exact, original HTML
content authored for each report — copied byte-for-byte from the local
working files used to publish them, not re-typed, re-summarized, or
regenerated from memory. Each is a raw HTML content fragment (no
`<!doctype>`/`<html>`/`<body>` wrapper), matching how it was originally
written; open it in a browser and it renders correctly on its own — modern
browsers accept a bare fragment starting with `<title>`/`<style>` without
requiring the wrapper tags.

Rows marked "Claude Artifact only" were **not** reconstructed as part of
this reconciliation pass (scoped to Phase 8–15 reports only). Their content
still exists, hosted as Claude Artifacts, but per this project's own
standard: an artifact link is not repository preservation. A link is
provided for reference, not as a substitute for a committed file.

## Index

| Phase | Report | Status |
|---|---|---|
| Pre-phase | Forensic audit of the original repository | Claude Artifact only |
| Pre-phase | Intraday Workstation Gap Analysis (the pivot to a trading workstation) | Claude Artifact only |
| 1+2 | AI multi-agent market analysis, market-awareness extension | Claude Artifact only |
| 3 | Deterministic strategy + backtester | Claude Artifact only |
| 4 | Deterministic RiskEngine | Claude Artifact only |
| 4.5 | Hardening + autonomous-loop fixes | Claude Artifact only |
| 5 | MCP integration | Claude Artifact only |
| 6 | Paper trading + SQLite journal | Claude Artifact only |
| 7A | Continuous bar-driven replay | Claude Artifact only |
| 7B | TradingView investigation (Outcome C — nothing built; scraping violates TradingView's ToS) | Claude Artifact only |
| 8 | Strategy validation — 12 symbols, 5 years. Classification **C — no evidence of a durable edge** | [`docs/phases/phase-08-strategy-validation.html`](phases/phase-08-strategy-validation.html) |
| 9 | Regime-filter hypothesis test. Classification **C — rejected** | [`docs/phases/phase-09-regime-filter-test.html`](phases/phase-09-regime-filter-test.html) |
| 10 | Alpha discovery — 5 features, 15 hypotheses, none survived correction | [`docs/phases/phase-10-alpha-discovery.html`](phases/phase-10-alpha-discovery.html) |
| 11 | Volume signal confirmation study. Classification **C**, one variant **B** | [`docs/phases/phase-11-volume-confirmation.html`](phases/phase-11-volume-confirmation.html) |
| 12 | Live pipeline foundation — MarketDataSource, OHLCVBar metadata, MockMarketDataSource, freshness guard | [`docs/phases/phase-12-live-pipeline-foundation.html`](phases/phase-12-live-pipeline-foundation.html) |
| 13 | Human-operated intraday workstation — approval lifecycle, kill switch, mock broker, CLI, dashboard, MCP | [`docs/phases/phase-13-human-approval-workstation.html`](phases/phase-13-human-approval-workstation.html) |
| 14 | Real market data + broker integration investigation (research/design only, no code) | [`docs/phases/phase-14-broker-research.html`](phases/phase-14-broker-research.html) |
| 15 | Dhan live market data integration, read-only first | [`docs/phases/phase-15-dhan-integration.html`](phases/phase-15-dhan-integration.html) |
| &mdash; | GitHub Reconciliation Audit (this repository's own forensic audit, pre-Phase-16) | [`https://claude.ai/code/artifact/e44ea528-f8b2-4efb-bc60-3d15d77ca174`](https://claude.ai/code/artifact/e44ea528-f8b2-4efb-bc60-3d15d77ca174) — Claude Artifact only |
| 16 | Real Dhan connectivity verification — real REST calls, real WebSocket data, four real bugs found and fixed (including a reconnect storm and a timezone decoding bug), 10 real bars traced through the pipeline to strategy invocation. No natural signal occurred; risk/approval/paper remain deterministic-test-only, not real-service-verified | [`docs/phases/phase-16-dhan-real-connectivity.html`](phases/phase-16-dhan-real-connectivity.html) |
| 17 | Production readiness & operationalization audit — startup/shutdown lifecycle, dependency degradation, observability, security, and persistence reviewed against the running code. Two real bugs found and fixed: an Ollama-dependent test misclassified as a hard dependency, and the Dhan/mock market-data source never being closed on any CLI exit path (including Ctrl+C) | [`docs/phases/phase-17-production-readiness.html`](phases/phase-17-production-readiness.html) |
| 18 | Market data abstraction & market state modeling — the first phase under `PROJECT_GOAL_AND_ROADMAP.md`'s long-term direction. A `market_data/` package unifies the existing Yahoo/mock/Dhan sources behind one snapshot contract, without modifying any of them. No AI recommendations, no trading logic — foundation only | [`docs/phases/phase-18-market-data-foundation.html`](phases/phase-18-market-data-foundation.html) |
| 19 | Market scanner & candidate discovery — a `market_intelligence/` package ranks a configured watchlist by trend/momentum/breakout/relative-strength/sector-strength, with explainable, fully-audited scores and SQLite scan-history persistence. Reuses `market.indicators` and `market_data.universe` unchanged. Still no AI, no buy/sell/recommendation logic | [`docs/phases/phase-19-market-scanner.html`](phases/phase-19-market-scanner.html) |
| 20 | Research intelligence — the Phase 10/11 `research/` package is renamed `quant_research/`, freeing the name for a new `research/` package: real Yahoo Finance news + sector classification, plus an optional, never-blocking AI summary with a structurally-enforced Evidence/Source/Timestamp/Confidence/Unknowns shape. First phase to reuse the existing LLM infrastructure (`agents.analyst.invoke_structured`) outside the `analyze`/AI-explanation paths. One real bug found by testing and fixed (an unconditional heavy-import cost for `--no-ai-summary`). Still no buy/sell/recommendation logic | [`docs/phases/phase-20-research-intelligence.html`](phases/phase-20-research-intelligence.html) |
| 21 | Decision intelligence engine — a new `decision_engine/` package combines scanner evidence and open-position state into a deterministic BUY/WATCH/AVOID/EXIT/NO_ACTION label (sign-agreement across independent factors, no fabricated magnitude threshold), with every non-NO_ACTION label structurally required to carry recorded evidence and an optional, never-blocking AI narrative. A label only — no order, no `paper/` import anywhere in the package. One real bug found by self-audit and fixed before merge (a crash when holding a position with no scanner evidence) | [`docs/phases/phase-21-decision-intelligence.html`](phases/phase-21-decision-intelligence.html) |
| 22 | Dynamic risk & position sizing — reconciliation found `risk/engine.py`/`risk/config.py`/`risk/account.py` already implement everything the roadmap asks for (dynamic capital, risk-per-trade, daily-loss limit, exposure limit, fresh-every-call position sizing); neither was touched. A new `risk/sizing.py` bridges a Phase 21 BUY label to the unmodified `RiskEngine` by constructing the `Signal` it needs, reusing `strategy/baseline.py`'s own stop/target convention. Preview only — no order placed | [`docs/phases/phase-22-risk-position-sizing.html`](phases/phase-22-risk-position-sizing.html) |
| 23 | Shadow prediction & continuous evaluation — a new `predictions/` package records a BUY decision's entry/stop/target as an immutable prediction, then checks real subsequent market data against it (TARGET_HIT/STOP_HIT/EXPIRED/ACTIVE/INSUFFICIENT_DATA), whether or not the user traded it. Outcomes are always appended as new rows, never rewriting the original prediction. Reuses `backtesting.execution.check_exit` verbatim for the same-bar-ambiguity stop/target rule. No order placed anywhere in this phase | [`docs/phases/phase-23-shadow-prediction.html`](phases/phase-23-shadow-prediction.html) |
| 24 | Performance learning system — a new `learning/` package turns Phase 23's prediction history into a read-only report: strategy comparison (by decision config version), market-regime performance (reusing Phase 9's SMA200 convention), a composite-score median-split calibration check, and signal-quality (MFE/MAE) stats. Writes to no configuration anywhere, per the roadmap's own "no automatic strategy modification" rule. Completes the roadmap's core intelligence-pipeline build-out (Phases 18–24) | [`docs/phases/phase-24-performance-learning.html`](phases/phase-24-performance-learning.html) |
| 25 | AI multi-agent market research — reconciliation found 5 of the roadmap's 6 suggested agents already covered (Technical Analyst/Risk Critic by the original Phase 1/2 `analyze` pipeline; News/Sector Analyst by `research/summarizer.py`), with Market Analyst deferred to Phase 26's dashboard. The one genuine gap: `agents/decision_reviewer.py`, an independent adversarial second opinion on a `decision_engine.Decision`, for any label. Review only — cannot change the label, no order placed | [`docs/phases/phase-25-ai-multi-agent-research.html`](phases/phase-25-ai-multi-agent-research.html) |
| 26 | Live market decision dashboard — a new `/intelligence` page on the existing Phase 13 dashboard app (not a second app) shows a read-only snapshot of the latest scan's ranked candidates, their decision labels, and prediction performance, reusing `live/workstation.py`'s exact read-only facade pattern. No market-data fetch, LLM call, or store write on page load; the existing paper-live workstation view is untouched | [`docs/phases/phase-26-live-dashboard.html`](phases/phase-26-live-dashboard.html) |
| 27 | End-to-end shadow trading validation — a new `shadow-run` command orchestrates scan → research → decide → predict → evaluate → learn in one pass over a watchlist, calling only already-tested functions from each stage. One real end-to-end run against live Yahoo data confirmed the wiring; the roadmap's own "run for sufficient time" criterion is honestly classified NOT VERIFIED — that requires real elapsed operating time this session cannot fabricate | [`docs/phases/phase-27-shadow-trading-validation.html`](phases/phase-27-shadow-trading-validation.html) |
| 28 | Operational scheduling & continuous shadow mode — a new `scheduler/` package plus `python main.py schedule tick\|loop\|status` makes the existing, unchanged `shadow-run`/`evaluate`/`learn` commands safe to trigger unattended: a configurable 5-slot pre-market/market-open/intraday/pre-close/post-market schedule (YAML-overridable), market-session/weekend/holiday awareness, an atomic on-disk lock (verified under real concurrent contention) preventing overlapping runs and recovering from a crashed process on restart, and an explicit, never-default continuous loop with clean Ctrl+C shutdown. Two real bugs found and fixed by self-audit: `finished_at` silently using real wall-clock instead of the tick's own injected time, and a TOCTOU race that could let two scheduler processes both start an overlapping run | [`docs/phases/phase-28-operational-scheduling.html`](phases/phase-28-operational-scheduling.html) |
| 29 | Production market universe — symbol validation (rejects a comma-joined or whitespace-containing entry with a clear message, a real bug found by adversarial re-reading of Phase 18's own code), NSE/BSE exchange derivation, and best-effort Dhan broker-instrument-ID enrichment via the existing, credential-free `DhanInstrumentMap` (`python main.py universe --symbols X,Y,Z [--with-dhan-ids]`), plus a small, honestly-labeled starter watchlist. Deliberately did NOT implement `mode: nifty50`/100/200/500 — reasoned explicitly in the phase report: this project has no live, verifiable index-membership source, and shipping a static list under an official-sounding name would overclaim accuracy | [`docs/phases/phase-29-production-market-universe.html`](phases/phase-29-production-market-universe.html) |
| 30 | Provider resilience & rate control — a new `market_data/resilience.py` wraps any `MarketDataProvider` with a timeout, retry with exponential backoff + jitter, a circuit breaker, an optional minimum-interval rate limiter, and in-process metrics, opt-in via `--resilient` on `scan`/`shadow-run`/`evaluate`/`learn`/`schedule tick`/`schedule loop` (default off — existing behavior and every existing test's fixture-patching stay completely unchanged unless a caller explicitly opts in). One serious bug caught by reasoning through the design before writing it: a naive `ThreadPoolExecutor`-based timeout would have let a genuinely hung network call block the *whole process* at exit despite the fetch itself "timing out" — fixed with a plain `daemon=True` thread instead, proven under real concurrency | [`docs/phases/phase-30-provider-resilience.html`](phases/phase-30-provider-resilience.html) |
| 31 | Multi-source market data intelligence — reconciliation found Phase 18 had already built the roadmap's own "Provider Router / Canonical Model / Source Health" architecture (`market_data/provider.py`, `contracts.py`, `adapters/`) but nothing downstream ever consumed it; this phase wires it in rather than building a second one. `MarketContext` gained `data_source`/`data_status`/`data_freshness_seconds` (reusing the existing `DataSource`/`DataStatus` enums, never inventing new labels), `get_market_context` gained an optional live-snapshot overlay, and `size`/`predict` gained a real, credential-gated `--live-source dhan` flag reusing Phase 15/16's exact credential loading and Phase 18's exact, unmodified Dhan adapter. Explicitly reconciled why Dhan cannot simply become a second `MarketDataProvider` (streaming vs. batch-historical are genuinely different shapes) and why a real Dhan live check remains NOT VERIFIED — no credentials in this environment — while the composition logic itself was proven against a real service using `YahooSnapshotAdapter` as a stand-in live source | [`docs/phases/phase-31-multi-source-market-data.html`](phases/phase-31-multi-source-market-data.html) |
| 32 | Live intraday market intelligence — extends Phase 31's single-symbol live-price overlay to the bulk `shadow-run` loop (one Dhan adapter built for the whole run, reused per candidate, closed exactly once) and threads `--live-source`/`--resilient` through the Phase 28 scheduler; `shadow-run` now prints market session + live-overlay status in its header; the `/intelligence` dashboard shows each decision's real data source/status (or an honest "n/a" when a decision has no `market_context` at all, e.g. from standalone `decide`). Most of what this phase asked for (reconnect behavior, stale-feed detection, market-session handling) already existed from Phases 15-18/31 — the genuine gap closed here was reaching a whole watchlist instead of one symbol, and actually displaying provenance where a human looks | [`docs/phases/phase-32-live-intraday-intelligence.html`](phases/phase-32-live-intraday-intelligence.html) |
| 33 | Market regime & breadth intelligence — a new `market_intelligence/regime.py` turns an already-computed `ScanReport` into market breadth (free — pure aggregation over `candidates`) and a benchmark's own trend regime (reusing `learning.regime.classify_regime_at` verbatim) + volatility regime (current ATR14%-of-price vs. its own trailing average, an explicit named-threshold classification), plus optional sector strength; a new `regime` CLI command, and `scan` now prints breadth automatically. Found and fixed two real bugs: (1) `market.data_provider._to_timestamp`'s tzinfo-stripping logic was DEAD CODE for every real DataFrame index value (`pd.Timestamp` is a `datetime` subclass, so the `isinstance` branch above it always matched and returned the value as-is) — surfaced as a real crash scanning against the live `^NSEI` benchmark, whose Yahoo data carries an Asia/Kolkata-aware index while other symbols' didn't; (2) `regime --benchmark X` silently ignored the override, never passing it through to the report builder — fixed with an explicit sentinel disambiguating "inherit the scan's own" from "explicitly disable" | [`docs/phases/phase-33-market-regime-breadth.html`](phases/phase-33-market-regime-breadth.html) |
| 34 | Decision confidence & calibration — a new `decision_engine/confidence.py` gives every `Decision` a real, deterministic `confidence` score: the fraction of independent scanner factors (trend/momentum/breakout/relative-strength/sector-strength) that agree with the decision's own direction, computed for every label (not just BUY), structurally incapable of LLM influence (verified: identical whether or not Ollama was reachable). Surfaced in `decide`'s CLI output, the `/intelligence` dashboard, and a new real calibration section in `learn` (fixed LOW/MEDIUM/HIGH bands against actual outcomes, kept alongside the prior composite-score-median proxy Phase 24 explicitly flagged as "not literal probability calibration" — now labeled "legacy" rather than removed) | [`docs/phases/phase-34-decision-confidence-calibration.html`](phases/phase-34-decision-confidence-calibration.html) |

## Artifact-only reports (for reference; not committed as files)

These still exist and are readable, hosted as Claude Artifacts. They were
not brought into the repository in this pass because this reconciliation
was explicitly scoped to Phase 8–15.

- [Forensic audit of the original repository](https://claude.ai/code/artifact/198065e3-0239-4c62-8c58-d6e2de60ae14)
- [Intraday Workstation Gap Analysis](https://claude.ai/code/artifact/b5ca700f-f0d3-4238-b63f-a5ab530ff0ba)
- [Phase 1+2 Implementation Report](https://claude.ai/code/artifact/463a7d72-7659-4f32-ac7c-8675b851069e)
- [Phase 3 Backtest Report](https://claude.ai/code/artifact/7f79c7d2-f314-44d4-a7dd-248c9dae8067)
- [Phase 4 Risk Engine Report](https://claude.ai/code/artifact/f9b44cb9-1a64-4fbe-9ada-7b7b737e7523)
- [Phase 4.5 Hardening Report](https://claude.ai/code/artifact/9dda984f-8c0d-43b9-b68c-8823a05b7d91)
- [Phase 5 MCP Integration Report](https://claude.ai/code/artifact/7cac68b5-dd92-4116-85d1-68e8c9d4cbba)
- [Phase 6 Paper Trading Report](https://claude.ai/code/artifact/616bed92-747b-4a76-8855-0768f6fa10b8)
- [Phase 7A Continuous Replay Report](https://claude.ai/code/artifact/b687e60b-416b-41e1-8d1d-24c4b588e5bd)
- [Phase 7B TradingView Investigation](https://claude.ai/code/artifact/079899ee-1b92-42d5-ab4f-78e867c161bc)

Note: these links point to artifacts owned by the project's operator. They
may not be reachable by other people without being explicitly shared.

## What this project actually is, as of Phase 16

- A deterministic, rule-based intraday strategy and a fail-closed risk
  engine — the strategy itself is classified **unproven** (Phase 8–11); this
  has not changed and nothing here should be read as investment advice.
- A real-market-data-capable pipeline (`live/dhan/`) feeding the same
  unchanged strategy/risk/approval chain — as of Phase 16, this has
  actually been connected to the live DhanHQ v2 service: real REST account
  calls, a real WebSocket handshake, real market packets, and real OHLCV
  bars reaching the unmodified pipeline through strategy invocation. Four
  real bugs were found and fixed along the way (an undocumented Dhan
  `/holdings` empty-state response, a connection-lifecycle race, a
  reconnect storm that got the account rate-limited by Dhan, and a
  timezone decoding bug in Dhan's own "Last Trade Time" field) — see the
  Phase 16 report for full detail.
- Paper execution only. No code path in this repository can place a real
  order — see the Phase 15 and Phase 16 reports' explicit safety findings.
- A human-approval workflow with a second, independent risk check, a local
  CLI and dashboard, and read-only MCP tools. As of Phase 16, no natural
  real-market signal has yet been observed to exercise this workflow
  end-to-end against real data — that chain is verified only by the
  existing deterministic test suite, not yet by a live signal.
