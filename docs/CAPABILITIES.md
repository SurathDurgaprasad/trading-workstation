# Capabilities

What this system can actually do today, organized by category. Every row states its
real prerequisites — including whether it needs a broker credential, whether it can
consume paid API usage, and whether it works fully offline. See
[`LIMITATIONS.md`](LIMITATIONS.md) for the corresponding "what it cannot do."

Legend: **Credentials** = broker/LLM credential required. **Paid data** = can consume a
metered/rate-limited external API. **Offline-safe** = works with zero network
credentials configured.

## Historical research & backtesting

| Capability | Inputs | Outputs | Credentials | Paid data | Offline-safe |
|---|---|---|---|---|---|
| Single-symbol backtest (`python main.py backtest`) | Symbol, period, interval | Trade log, expectancy, profit factor | None | No (Yahoo, free/unofficial) | Yes |
| Universe backtest (`backtest-universe`) | Symbol list, period | Pooled trade statistics | None | No | Yes |
| Walk-forward validation (`backtesting/walk_forward.py`) | Symbol/universe, period | Per-fold verdicts | None | No | Yes |
| Monte Carlo execution-robustness / random-baseline comparison | Backtest result | Cost/random-entry sensitivity | None | No | Yes |
| Hypothesis registry report (`hypothesis-registry`) | None | The full 64-entry (pre-mission) / 69-entry (current) registry with verdicts | None | No | Yes |
| Cross-sectional / event-study research (`quant_research/`) | Symbol universe, score definition | Bucketed forward-return statistics | None | No | Yes |
| Point-in-time universe construction (`audit/edge_feasibility/scripts/`) | Cached NSE F&O bhavcopy archives | Survivorship-corrected symbol universe over time | None | No (public NSE archive, cached locally) | Yes, once cached |

## Paper trading (simulated or real-data-driven)

| Capability | Inputs | Outputs | Credentials | Paid data | Offline-safe |
|---|---|---|---|---|---|
| `paper` — replay cached history through the paper engine | Symbol, cached OHLCV | Simulated trades, SQLite-persisted | None | No | Yes |
| `live-sim` / `paper-live` (mock/Yahoo source) | Symbol, interval | Bar-by-bar simulated signals → paper orders | None | No | Yes |
| `paper-live --source dhan` | Symbol | Same, driven by real market data | **Dhan** (market-data read scope only) | Yes (Dhan API usage) | No |
| `fleet-supervise` / `fleet-summary` | Watchlist file | Multi-symbol supervised paper-trading fleet + consolidated report | **Dhan** (for `--source dhan`; mock source needs none) | Yes if `--source dhan` | Partial |
| Dashboard (`python main.py dashboard`) | None (reads existing stores) | Web UI: account, positions, pending approvals, kill switch | None | No | Yes |

Every paper-trading path — regardless of data source — writes only to a local SQLite
database. No path here can place a real order (see [`SAFETY.md`](SAFETY.md)).

## Market intelligence & decision pipeline (never touches execution)

| Capability | Inputs | Outputs | Credentials | Paid data | Offline-safe |
|---|---|---|---|---|---|
| `scan` — rank a watchlist | Symbol list | Trend/momentum/breakout scores, persisted | None | No | Yes |
| `research --symbol X` | Symbol | Real news + sector evidence, optional AI summary | Ollama optional; OpenAI opt-in | Only if `AI_PROVIDER=openai` | Yes without `--no-ai-summary` too — AI step degrades, never blocks |
| `decide --symbol X` | Scan + research evidence | Deterministic BUY/WATCH/AVOID/EXIT/NO_ACTION label | Same as above (narrative only) | Same | Yes |
| `size --symbol X --initial-capital N` | A BUY decision, capital | Position-sizing preview (no order) | None | No | Yes |
| `predict` / `evaluate` | A BUY decision | Immutable shadow prediction, later scored against real outcomes | None | No | Yes |
| `learn` | Prediction history | Win rate, calibration, profitability verdict (with honest INSUFFICIENT_DATA/STATISTICALLY_MEANINGLESS states) | None | No | Yes |
| `shadow-run` | Watchlist | One-pass scan→research→decide→predict→evaluate→learn | Same AI caveats as above | Same | Yes |
| `schedule tick/loop/status` | Watchlist, schedule config | Unattended, crash-recoverable scheduled runs of the above | Same | Same | Yes |

## Live Dhan integration

| Capability | Inputs | Outputs | Credentials | Paid data | Offline-safe |
|---|---|---|---|---|---|
| Real REST account reads (funds, positions, holdings) | None | Read-only account snapshot | **Dhan** | Yes | No |
| Real WebSocket market-data feed (NSE; BSE code-complete/tested, never live-verified) | Symbol(s) | Real tick/quote/bar stream into the same pipeline the mock feed uses | **Dhan** | Yes | No |
| Order placement/modification/cancellation | — | — | — | — | **Does not exist** (`DisabledDhanOrderExecutor` raises unconditionally — see [`SAFETY.md`](SAFETY.md)) |

## Data-quality & observability

| Capability | Inputs | Outputs | Credentials | Paid data | Offline-safe |
|---|---|---|---|---|---|
| Freshness/duplicate/out-of-order bar detection | Any data source | LIVE/DELAYED/HISTORICAL/SIMULATED/DHAN labeling, suppression of stale signals | None | No | Yes |
| Gap detection (`live/gap_monitor.py`) | Live feed | `[GAP DETECTED]`/`[GAP ONGOING]` events | Only meaningful with `--source dhan` | Yes if live | N/A |
| Heartbeat / liveness files | Running worker/supervisor | Crash-vs-clean-shutdown distinction | None | No | Yes |
| `health` / `readiness-check` | None | Unified HEALTHY/DEGRADED/SAFE_STOP/FAILED system status | None (checks credential *presence*, never their validity, without a real call) | No | Yes |

## Prediction tracking & research evidence storage

| Capability | Inputs | Outputs | Credentials | Paid data | Offline-safe |
|---|---|---|---|---|---|
| Shadow prediction ledger (`predictions/`) | A decision/signal | Immutable prediction record + later evaluation outcome | None | No | Yes |
| Experiment tracking (`experiments/`) | Named experiment + config version | Comparison isolated to that experiment's own dataset/time window | None | No | Yes |
| Hypothesis preregistration + evidence (`strategy/hypothesis_registry.py`) | None | 69-entry structured research ledger | None | No | Yes |

## Safety controls

| Capability | Inputs | Outputs | Credentials | Paid data | Offline-safe |
|---|---|---|---|---|---|
| Persistent kill switch | CLI/dashboard action | Halts new signal processing, read fresh on every check | None | No | Yes |
| `RiskEngine` fail-closed evaluation | Any proposed trade | APPROVE/veto with a named reason, NaN/Infinity guarded | None | No | Yes |
| `CriticGate` (13-check deterministic re-examination) | A proposed BUY | APPROVE/REJECT/DOWNGRADE/INSUFFICIENT_EVIDENCE | None | No | Yes |
| Human-approval workflow | A pending signal | Approve/reject with a second, independent risk check | None | No | Yes |
