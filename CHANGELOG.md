# Changelog

A phase-level summary of this project's development, from first commit to the public
release. This is not a line-by-line commit log — see `git log` for that, or
[`docs/PHASE_HISTORY.md`](docs/PHASE_HISTORY.md) for the itemized numbered-phase index.
Dates and commit references below are real, taken from `git log`, not reconstructed
from memory.

## 2026-09-01 — Initial build (`b7dcfb0`)

Human-operated paper-trading workstation: deterministic strategy and risk engine, a
CLI, paper execution with SQLite persistence, and a human-approval workflow (Phases
0–13).

## 2026-09-03 to 2026-09-05 — Scientific research foundation

Hypothesis registry (`strategy/hypothesis_registry.py`), the promotion gate
(`strategy/promotion_gate.py`), walk-forward validation, and Monte Carlo
execution-robustness testing — the methodology every later research program reuses. The
first formal hypothesis (`H_BASELINE_001`, the `TrendMomentumBaseline` strategy itself)
returns a NEGATIVE promotion-gate verdict.

## 2026-09-05 to 2026-09-13 — Market intelligence pipeline & Phase 0.5 audit

A second, separate pipeline (`market_intelligence/`, `research/`, `decision_engine/`,
`predictions/`, `learning/`) for scanning, evidence-backed recommendations, and
outcome tracking — deliberately never touching real or paper order execution. A
comprehensive, independent forensic audit (Phase 0.5, `AUDIT_BASELINE.json`) establishes
a machine-readable capability baseline.

## 2026-09-13 — ML Phase 1

A triple-barrier-labeled logistic-regression baseline (`ml_research/`). Result: **no
evidence of economic edge** (`docs/research/ML_PHASE1_TRIPLE_BARRIER_BASELINE_PREREGISTRATION.md`,
`PHASE_1_REPORT.md`) — the first of what would become 69 total tested-and-rejected
hypotheses.

## 2026-09-07 — First live Dhan session

Real DhanHQ v2 REST + WebSocket connectivity verified for the first time against a live
NSE market. Paper execution only. See
[`docs/LIVE_VALIDATION.md`](docs/LIVE_VALIDATION.md).

## 2026-09-13 to 2026-09-15 — "Build the real trading brain" research campaign

Mean-reversion, breakout-quality, and cross-sectional relative-strength hypothesis
families (`H_MEANREV_*`, `H_BREAKOUT_001`, `H_RELSTRENGTH_001`), plus the Indian-market
transmission research (Nasdaq/USD-INR → NIFTY sectors). Independent adversarial audit,
`FINAL_ADVERSARIAL_ENGINEERING_AUDIT.md`: **PASS WITH RISKS**.

## 2026-09-15 to 2026-09-17 — Multi-symbol fleet, market-context research, second/third live sessions

Fleet supervision (`fleet-supervise`/`fleet-summary`, per-symbol isolated runtime
directories), market/sector/VIX regime-conditioning research (`H_CONTEXT_*`), gap/
calendar/breadth research (`H_GAP_*`, `H_CALENDAR_*`, `H_BREADTH_001`). Live sessions on
2026-09-15 (322 bars, one real feed gap correctly suppressed) and 2026-09-16/17
(15-symbol fleet; a real `CandleBuilder` cold-start defect found and fixed).

## 2026-09-16 to 2026-09-18 — Derivatives research program

Futures basis/OI and options IV/skew tested for incremental predictive information
beyond OHLCV (`audit/derivatives_research/`, `DERIV_001`–`004`). Terminal result: **no
meaningful incremental information** at any of the four tested angles.

## 2026-09-18 to 2026-09-21 — 35 autonomous hardening cycles

A sustained adversarial engineering campaign: concurrency races (TOCTOU), resource
exhaustion, crash-boundary reconciliation, kill-switch/risk-halt races, scheduler
zombie states — each cycle finds and fixes one real defect with a regression test. This
is where most of the safety invariants documented in `ARCHITECTURE.md` were established.

## 2026-09-16 to 2026-09-22 — Edge-feasibility audit & point-in-time universe

A point-in-time, survivorship-bias-corrected NSE F&O universe built from real bhavcopy
archives (`audit/edge_feasibility/`). Applied to the mean-reversion chain
(`H_MEANREV_010`→`H_MEANREV_014`), it flips a previously-inconclusive result to
CI-decisively negative at the point of correction — real survivorship bias, found and
disclosed rather than left uncorrected. Both remaining open research paths (mean
reversion, market-context regime) are formally closed
(`audit/edge_feasibility/CAPITAL_ALLOCATION_DECISION_FINAL.md`).

## 2026-09-22 to 2026-09-23 — Full-system red-team, remediation, and final live validation

Two full-system adversarial red-team passes (`docs/FULL_SYSTEM_RED_TEAM_2026-09-22.md`,
`docs/CONTINUOUS_FULL_SYSTEM_RED_TEAM_FINAL_2026-09-22.md`) followed by an open-issues
remediation pass (`0f7efbf`–`6cf86f3`) that closes the dashboard/CLI dual-writer race
(`G9`), a missing exception handler (`G10`), a dormant `CandleBuilder` cross-thread read
(`G12`), and a missing DB uniqueness constraint (`G14`). A final live-market validation
session (`d8ae04f`, 2026-09-23) confirms the repaired build against real NSE data: 4,995
bars, 99.7% fresh, one self-healing ~15-minute feed gap, zero strategy/risk changes
during market hours.

## 2026-09-23 — Final edge-discovery mission (`540651d`)

Five new, genuinely-novel hypotheses (corporate dividend events, cross-sectional
momentum, relative volume, relative volatility) tested against the two families the
project had not yet touched (Family A: corporate/event information; Family C:
cross-sectional/relative information distinct from the closed laggard-reversal family).
Market microstructure (Family B) closed on a confirmed data-availability gap, without
writing a hypothesis. All five REJECTED. **Terminal conclusion, 69 hypotheses tested
across this project's full history: 0 promoted.** See
[`docs/EDGE_DISCOVERY_FINAL_REPORT.md`](docs/EDGE_DISCOVERY_FINAL_REPORT.md).

## 2026-09-23 — Public release preparation

Security audit (current tree + full git history, multiple independent methods — zero
real credentials found at any point in this project's history), private-data
sanitization (hardcoded local paths, a personal email in an audit artifact), new
public-facing documentation (`docs/CAPABILITIES.md`, `docs/LIMITATIONS.md`,
`docs/SAFETY.md`, `docs/RESEARCH_METHODOLOGY.md`, `docs/RESEARCH_RESULTS.md`,
`docs/LIVE_VALIDATION.md`, `docs/OPERATIONS.md`), a license, a CI workflow, and this
changelog. See [`docs/PUBLIC_RELEASE_AUDIT.md`](docs/PUBLIC_RELEASE_AUDIT.md) for the
full release audit.
