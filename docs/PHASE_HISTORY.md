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

## What this project actually is, as of Phase 15

- A deterministic, rule-based intraday strategy and a fail-closed risk
  engine — the strategy itself is classified **unproven** (Phase 8–11); this
  has not changed and nothing here should be read as investment advice.
- A simulated and, as of Phase 15, real-market-data-capable pipeline
  (`live/dhan/`) feeding the same unchanged strategy/risk/approval chain.
- Paper execution only. No code path in this repository can place a real
  order — see the Phase 15 report's explicit safety findings.
- A human-approval workflow with a second, independent risk check, a local
  CLI and dashboard, and read-only MCP tools.
