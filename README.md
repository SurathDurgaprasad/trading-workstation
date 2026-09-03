# Trading Workstation

A single-user, local-first paper-trading research workstation: deterministic strategy and risk logic, a simulated (and, as of Phase 15, real-market-data-capable) intraday pipeline, a human-approval workflow, a local CLI and dashboard, and an optional local-LLM (Ollama) explanation layer that can narrate a decision but never make one.

As of Phase 18–27, the project also has a second, complementary pipeline for market intelligence and evidence-backed recommendations, entirely separate from — and never touching — the paper-trading execution path above: scan a watchlist, gather real news/sector evidence, produce a deterministic BUY/WATCH/AVOID/EXIT/NO_ACTION label with recorded evidence, preview position sizing against your own (never-hardcoded) capital, record shadow predictions, evaluate them against real subsequent market data, and get a read-only performance report — all chainable in one pass via `shadow-run`. No command in this pipeline can place an order, real or paper.

**Execution is paper-only.** There is no real broker connection, no real credentials configured, and no code path anywhere in this repository capable of placing a real order — order-mutating methods raise unconditionally rather than being merely unimplemented (see `live/dhan/broker_adapter.py`).

**Real market data: verified live, as of Phase 16.** `live/dhan/` implements a real DhanHQ v2 WebSocket market-data feed. As of Phase 16, this has actually been connected to the live service with a real account: real REST calls (`/fundlimit`, `/positions`, `/holdings`), a real WebSocket handshake, real market packets, and real OHLCV bars have all been observed flowing through the unmodified pipeline into strategy invocation. Four real bugs were found and fixed in the process — including a reconnect storm that got the account temporarily rate-limited by Dhan, and a timezone decoding bug in Dhan's own data. **What has not been observed:** a natural trading signal from real market data — the risk engine, human-approval gate, and paper execution have not yet been exercised end-to-end by a real signal (only by the deterministic test suite). See [`docs/phases/phase-16-dhan-real-connectivity.html`](docs/phases/phase-16-dhan-real-connectivity.html) for the full, evidence-labeled breakdown of what is real-service-verified versus deterministic-test-only.

**The trading strategy is unproven.** A multi-symbol, multi-year validation study (documented in [`docs/PHASE_HISTORY.md`](docs/PHASE_HISTORY.md)) found no evidence of a durable edge. Nothing here should be read as investment advice, and nothing here should be represented as profitable.

## What exists today

```
Market Data
      |
Intraday simulation
      |
   Strategy
      |
 Risk Engine
      |
AI explanation (optional)
      |
Human approval
      |
Risk check again
      |
Paper execution
      |
Position monitoring
      |
   Journal
```

- Historical + simulated intraday market data (1m / 5m / 15m), with explicit LIVE/DELAYED/HISTORICAL/SIMULATED/DHAN labeling and freshness/duplicate/out-of-order protection
- A real DhanHQ v2 WebSocket market-data adapter (`live/dhan/`) implementing the same `MarketDataSource` interface the simulated feed uses — code-complete, unit/integration-tested, and **verified against the live DhanHQ v2 service** (Phase 16): real REST account calls, a real WebSocket connection, real market packets and OHLCV bars reaching the unmodified pipeline
- A deterministic, rule-based strategy engine and a fail-closed `RiskEngine` (unchanged by the Dhan work — the adapter only supplies market data, it does not touch strategy or risk logic)
- Paper trading with SQLite persistence, restart recovery, and reconciliation
- A human-approval workflow with a *second*, independent risk check at the moment of approval
- A persistent local kill switch
- A mock broker adapter (`BrokerAdapter` protocol) for execution, and a read-only real-Dhan-account reader (funds/positions/holdings) kept structurally incapable of placing, modifying, or cancelling a real order
- A local CLI (`paper-live`, with a `--source dhan` flag for the real feed — paper execution either way) and a minimal local dashboard
- MCP tools for observing paper-live and real Dhan account state (read-only), plus unmistakably-named paper-only approval-action tools — no order-placement tool exists anywhere
- Optional AI explanation via a local Ollama model — narration only; it cannot resize a position, change a price level, or approve a trade. Nothing else in this project requires Ollama; every other feature works with it absent
- `market_data/` (Phase 18): a unifying snapshot interface over the existing Yahoo/mock/Dhan sources — `InstrumentSnapshot`/`MarketSnapshot` state models, a source-agnostic freshness/health model, and a configurable (watchlist-mode) instrument universe. Foundation only: no recommendations, no trading logic. See [`docs/phases/phase-18-market-data-foundation.html`](docs/phases/phase-18-market-data-foundation.html) and [`PROJECT_GOAL_AND_ROADMAP.md`](PROJECT_GOAL_AND_ROADMAP.md) for the long-term direction this serves
- `market_intelligence/` (Phase 19): a market scanner (`python main.py scan`) that ranks a configured watchlist by trend/momentum/breakout/relative-strength/sector-strength, with every score traced to a plain-language explanation and every scan persisted to SQLite. Screening gates (liquidity/price/volume/volatility) default to no-ops until given real, evidence-based thresholds. Still no AI, no buy/sell/recommendation logic — see [`docs/phases/phase-19-market-scanner.html`](docs/phases/phase-19-market-scanner.html)
- `research/` (Phase 20): real Yahoo Finance news + sector classification for a symbol (`python main.py research --symbol X`), plus an optional, never-blocking AI summary (narration only — confidence and stated unknowns, no recommendation, same "cannot mutate a decision" type-level guarantee as the existing AI explanation feature). The unrelated Phase 10/11 quant-research package was renamed `quant_research/` to free this name. Still no buy/sell/recommendation logic — see [`docs/phases/phase-20-research-intelligence.html`](docs/phases/phase-20-research-intelligence.html)
- `decision_engine/` (Phase 21): combines the latest scanner + research evidence into a BUY/WATCH/AVOID/EXIT/NO_ACTION label (`python main.py decide --symbol X`) — a deterministic rule (no fabricated score threshold), every recommendation structurally required to carry recorded evidence, plus an optional AI narrative that can only explain the label, never choose it. **A label only — no order is placed, and the package never imports `paper/` or a broker adapter.** See [`docs/phases/phase-21-decision-intelligence.html`](docs/phases/phase-21-decision-intelligence.html)
- `risk/sizing.py` (Phase 22): previews how the existing, unmodified `RiskEngine` would size a Phase 21 BUY decision against your current (never-hardcoded) capital (`python main.py size --symbol X --initial-capital N`) — reuses `strategy/baseline.py`'s own ATR-based stop/target convention, adds no new risk methodology. **A preview only — no order is placed.** See [`docs/phases/phase-22-risk-position-sizing.html`](docs/phases/phase-22-risk-position-sizing.html)
- `predictions/` (Phase 23): records a BUY decision's entry/stop/target as an immutable shadow prediction (`python main.py predict --symbol X`) and later checks real market data against it (`python main.py evaluate`) — TARGET_HIT/STOP_HIT/EXPIRED/ACTIVE, plus a win-rate/return/profit-factor summary. The system keeps score whether or not you actually trade. Outcomes are always appended as new rows, never rewriting a prediction. **No order is placed.** See [`docs/phases/phase-23-shadow-prediction.html`](docs/phases/phase-23-shadow-prediction.html)
- `learning/` (Phase 24): a read-only report over prediction history (`python main.py learn`) — strategy comparison by decision config version, market-regime performance, a composite-score calibration check, and signal-quality stats. Writes to no configuration, ever. Completes the roadmap's core intelligence pipeline (Phases 18–24: market data → scanner → research → decision → sizing → prediction → learning). See [`docs/phases/phase-24-performance-learning.html`](docs/phases/phase-24-performance-learning.html)
- `agents/decision_reviewer.py` (Phase 25): an independent, adversarial AI second opinion on the latest decision for a symbol (`python main.py review --symbol X`) — five of the roadmap's six suggested research agents turned out to already exist (the original `analyze` pipeline, `research/summarizer.py`); this is the one genuine gap. **Review only — cannot change the label, no order is placed.** See [`docs/phases/phase-25-ai-multi-agent-research.html`](docs/phases/phase-25-ai-multi-agent-research.html)
- `/intelligence` dashboard page (Phase 26): a new read-only view on the existing `python main.py dashboard` app — the latest scan's ranked candidates with their decision labels, plus prediction performance. No market-data fetch, LLM call, or write happens on page load. See [`docs/phases/phase-26-live-dashboard.html`](docs/phases/phase-26-live-dashboard.html)
- `shadow-run` (Phase 27): one command chaining scan → research → decide → predict → evaluate → learn over a watchlist (`python main.py shadow-run --symbols X,Y,Z`) — pure orchestration over already-tested functions, one symbol's failure never aborts the rest. **This is infrastructure for validation, not validation itself** — the roadmap's own "run for sufficient time" criterion requires real elapsed operating time and is honestly reported as not yet met. See [`docs/phases/phase-27-shadow-trading-validation.html`](docs/phases/phase-27-shadow-trading-validation.html)
- `scheduler/` (Phase 28): makes `shadow-run`/`evaluate`/`learn` safe to trigger unattended (`python main.py schedule tick|loop|status`) — a configurable pre-market/market-open/intraday/pre-close/post-market schedule (YAML-overridable), market-session/weekend/holiday awareness, an on-disk lock (atomic under real concurrent contention) that prevents overlapping runs and survives a crashed process on restart, and an explicit, never-default continuous loop mode. Calls the exact same, unchanged `shadow-run`/`evaluate`/`learn` command functions — no new business logic. See [`docs/phases/phase-28-operational-scheduling.html`](docs/phases/phase-28-operational-scheduling.html)
- Production market universe (Phase 29): symbol validation, NSE/BSE exchange derivation, and best-effort Dhan broker-instrument-ID enrichment for any watchlist (`python main.py universe --symbols X,Y,Z [--with-dhan-ids]`), plus a small, honestly-labeled starter watchlist (`market_data/watchlists/starter_nse.yaml` — explicitly NOT a claimed NIFTY 50/100/500 constituent list; see the phase report for why index-membership modes remain deliberately unimplemented). See [`docs/phases/phase-29-production-market-universe.html`](docs/phases/phase-29-production-market-universe.html)
- Provider resilience (Phase 30): `market_data/resilience.py` wraps any market-data provider with a timeout, retry with exponential backoff + jitter, a circuit breaker, an optional rate limiter, and metrics — opt-in via `--resilient` on `scan`/`shadow-run`/`evaluate`/`learn`/`schedule tick`/`schedule loop` (default off, so existing behavior is unchanged unless requested). See [`docs/phases/phase-30-provider-resilience.html`](docs/phases/phase-30-provider-resilience.html)
- Multi-source market data (Phase 31): `MarketContext` now labels its own data source/status/freshness (reusing the existing `DataSource`/`DataStatus` enums), and `get_market_context` accepts an optional live-snapshot overlay — wired to a real, credential-gated `--live-source dhan` flag on `size`/`predict`, reusing Phase 18's `market_data/` router/adapter architecture (built then, never consumed by anything downstream until now). See [`docs/phases/phase-31-multi-source-market-data.html`](docs/phases/phase-31-multi-source-market-data.html)
- Live intraday intelligence (Phase 32): the live-overlay mechanism now covers a whole watchlist (`shadow-run`/`schedule --live-source dhan`, one adapter for the whole run), `shadow-run` prints market session + live-overlay status, and the `/intelligence` dashboard shows each decision's data source/status honestly (or "n/a" when absent — never fabricated). See [`docs/phases/phase-32-live-intraday-intelligence.html`](docs/phases/phase-32-live-intraday-intelligence.html)

## Running it

```bash
python -m venv venv
venv\Scripts\activate        # Windows
pip install -r requirements.txt

python main.py backtest --symbol AAPL
python main.py paper-live --symbol AAPL --interval 1d --period 1y
python main.py dashboard
```

The market-intelligence/recommendation pipeline (Phase 18–27, no order ever placed) in one pass:

```bash
python main.py shadow-run --symbols AAPL,MSFT,RELIANCE.NS
```

...or one stage at a time, each persisting its own SQLite history the next stage reads:

```bash
python main.py scan --symbols AAPL,MSFT,RELIANCE.NS
python main.py research --symbol AAPL
python main.py decide --symbol AAPL
python main.py size --symbol AAPL --initial-capital 100000
python main.py predict --symbol AAPL
python main.py evaluate
python main.py learn
```

To run that pipeline unattended (Phase 28), on a configurable schedule, with overlap prevention and crash recovery:

```bash
python main.py schedule tick --symbols AAPL,MSFT,RELIANCE.NS   # one check-and-maybe-run cycle, safe from cron
python main.py schedule loop --symbols AAPL,MSFT,RELIANCE.NS   # explicit continuous mode, Ctrl+C to stop
python main.py schedule status                                  # read-only run-history audit
```

To try the real Dhan market-data feed instead of the mock replay (still paper execution — see the two caveats above), copy `.env.example` to `.env`, fill in `DHAN_CLIENT_ID`/`DHAN_ACCESS_TOKEN` (never commit that file — it's already gitignored), and:

```bash
python main.py paper-live --symbol RELIANCE.NS --source dhan
```

**Ollama (required only for `analyze` and `review`; optional for `research`'s AI summary and `decide`'s AI narrative):** every other command (`backtest`, `paper`, `paper-live`, `dashboard`, `scan`, `research --no-ai-summary`, `decide --no-narrative`, `size`, `predict`, `evaluate`, `learn`) works with no Ollama installed at all, and `research`/`decide` without their `--no-*` flags still return their real evidence and deterministic label even if Ollama is unreachable — the AI step never blocks. `review`'s entire purpose is the AI critique, so it fails clearly (no silent fallback) if Ollama is unreachable, the same posture as `analyze`. If you do want `analyze`/`review`/AI explanations/AI research summaries/AI decision narratives, install [Ollama](https://ollama.com), start it (`ollama serve`), and pull the two models this project uses by default (see `core/config.py`'s `Settings` for the exact names if you've changed them):

```bash
ollama pull qwen2.5-coder:7b
ollama pull nomic-embed-text
```

Without Ollama running, `analyze` and any AI-explanation step fail with a clear, one-line error (`Ollama is not reachable at http://localhost:11434...`) — never a crash or a silent hang.

Full test suite (no Ollama required — the suite runs standalone by design):

```bash
pytest
```

Some tests use cached historical market data (`data/market/`) or a downloaded Dhan instrument master (`data/dhan/`) that are intentionally not committed to this repository (redistributing bulk third-party market data publicly is outside the scope of what this project wants to do). Those tests skip cleanly when the cache is absent; the caching layer will re-fetch on demand where the code path calls for it. No test requires real Dhan credentials or a live connection.

## Project status

Development has proceeded in numbered phases, each with its own forensic audit and report — see [`docs/PHASE_HISTORY.md`](docs/PHASE_HISTORY.md) for the full index, including the original phase reports preserved under `docs/phases/`. As of Phase 27, all 793 tests pass standalone — the full suite has no external-service dependency (a previously Ollama-dependent test was corrected to mock that dependency, matching its actual intent; see the Phase 17 report). The human-operated workstation (CLI, dashboard, MCP, approval workflow, kill switch, reconciliation) and the real Dhan market-data adapter are both code-complete, tested, and — as of Phase 16 — verified against the live Dhan service.

What remains before real trading could even be considered: a naturally-occurring real trading signal traced end-to-end through the risk engine, human approval, and paper execution (not yet observed — real market data has flowed through the pipeline as far as strategy invocation, but no signal has occurred yet to exercise the rest of the chain against real data), a real order-placement adapter (does not exist — only a structurally-disabled stub does), and, independently of any of that, actual evidence the strategy has an edge (it doesn't, as of the last validation study).
