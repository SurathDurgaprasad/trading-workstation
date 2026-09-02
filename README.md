# Trading Workstation

A single-user, local-first paper-trading research workstation: deterministic strategy and risk logic, a simulated (and, as of Phase 15, real-market-data-capable) intraday pipeline, a human-approval workflow, a local CLI and dashboard, and an optional local-LLM (Ollama) explanation layer that can narrate a decision but never make one.

**Execution is paper-only.** There is no real broker connection, no real credentials configured, and no code path anywhere in this repository capable of placing a real order — order-mutating methods raise unconditionally rather than being merely unimplemented (see `live/dhan/broker_adapter.py`).

**Real market data: code exists, not yet verified live.** `live/dhan/` implements a real DhanHQ v2 WebSocket market-data feed — wire-format parsing, symbol mapping, and read-only account access were all verified against current official Dhan documentation and real (but non-live) data (a downloaded instrument master CSV). No live WebSocket connection has actually been made and no real Dhan account has been used — that requires real credentials, which have not been provided. See [`docs/phases/phase-15-dhan-integration.html`](docs/phases/phase-15-dhan-integration.html) for exactly what was and wasn't tested.

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
- A real DhanHQ v2 WebSocket market-data adapter (`live/dhan/`) implementing the same `MarketDataSource` interface the simulated feed uses — code-complete and unit/integration-tested against the documented wire format, **not yet run against a live connection**
- A deterministic, rule-based strategy engine and a fail-closed `RiskEngine` (unchanged by the Dhan work — the adapter only supplies market data, it does not touch strategy or risk logic)
- Paper trading with SQLite persistence, restart recovery, and reconciliation
- A human-approval workflow with a *second*, independent risk check at the moment of approval
- A persistent local kill switch
- A mock broker adapter (`BrokerAdapter` protocol) for execution, and a read-only real-Dhan-account reader (funds/positions/holdings) kept structurally incapable of placing, modifying, or cancelling a real order
- A local CLI (`paper-live`, with a `--source dhan` flag for the real feed — paper execution either way) and a minimal local dashboard
- MCP tools for observing paper-live and real Dhan account state (read-only), plus unmistakably-named paper-only approval-action tools — no order-placement tool exists anywhere
- Optional AI explanation via a local Ollama model — narration only; it cannot resize a position, change a price level, or approve a trade. Nothing else in this project requires Ollama; every other feature works with it absent

## Running it

```bash
python -m venv venv
venv\Scripts\activate        # Windows
pip install -r requirements.txt

python main.py backtest --symbol AAPL
python main.py paper-live --symbol AAPL --interval 1d --period 1y
python main.py dashboard
```

To try the real Dhan market-data feed instead of the mock replay (still paper execution — see the two caveats above), copy `.env.example` to `.env`, fill in `DHAN_CLIENT_ID`/`DHAN_ACCESS_TOKEN` (never commit that file — it's already gitignored), and:

```bash
python main.py paper-live --symbol RELIANCE.NS --source dhan
```

Full test suite:

```bash
pytest
```

Some tests use cached historical market data (`data/market/`) or a downloaded Dhan instrument master (`data/dhan/`) that are intentionally not committed to this repository (redistributing bulk third-party market data publicly is outside the scope of what this project wants to do). Those tests skip cleanly when the cache is absent; the caching layer will re-fetch on demand where the code path calls for it. No test requires real Dhan credentials or a live connection.

## Project status

Development has proceeded in numbered phases, each with its own forensic audit and report — see [`docs/PHASE_HISTORY.md`](docs/PHASE_HISTORY.md) for the full index, including the original phase reports preserved under `docs/phases/`. As of Phase 15, 519 tests pass (1 pre-existing failure, unrelated to any of this — a local Ollama daemon isn't running in every environment). The human-operated workstation (CLI, dashboard, MCP, approval workflow, kill switch, reconciliation) and the real Dhan market-data adapter are both code-complete and tested.

What remains before real trading could even be considered: an actual live connectivity test against a real Dhan account (deliberately not attempted — no credentials were available), a real order-placement adapter (does not exist — only a structurally-disabled stub does), and, independently of any of that, actual evidence the strategy has an edge (it doesn't, as of the last validation study).
