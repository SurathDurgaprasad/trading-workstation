# Trading Workstation

A single-user, local-first paper-trading research workstation: deterministic strategy and risk logic, a simulated intraday pipeline, a human-approval workflow, a local CLI and dashboard, and an optional local-LLM (Ollama) explanation layer that can narrate a decision but never make one.

**This project is simulation-only.** There is no real broker connection, no real market-data feed, no real credentials, and no code path capable of placing a real order anywhere in this repository.

**The trading strategy is unproven.** A multi-symbol, multi-year validation study (documented in the project's phase reports) found no evidence of a durable edge. Nothing here should be read as investment advice or a signal to trade with real money.

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

- Historical + simulated intraday market data (1m / 5m / 15m), with explicit LIVE/DELAYED/HISTORICAL/SIMULATED labeling and freshness/duplicate/out-of-order protection
- A deterministic, rule-based strategy engine and a fail-closed `RiskEngine`
- Paper trading with SQLite persistence, restart recovery, and reconciliation
- A human-approval workflow with a *second*, independent risk check at the moment of approval
- A persistent local kill switch
- A mock broker adapter (`BrokerAdapter` protocol) and broker-shaped reconciliation, with no real broker implemented yet
- A local CLI (`paper-live`) and a minimal local dashboard
- MCP tools for observing and (in mock-only, unmistakably-named form) acting on the paper-live workstation
- Optional AI explanation via a local Ollama model — narration only; it cannot resize a position, change a price level, or approve a trade

## Running it

```bash
python -m venv venv
venv\Scripts\activate        # Windows
pip install -r requirements.txt

python main.py backtest --symbol AAPL
python main.py paper-live --symbol AAPL --interval 1d --period 1y
python main.py dashboard
```

Full test suite:

```bash
pytest
```

Some tests use cached historical market data (`data/market/`) that is intentionally not committed to this repository (redistributing bulk third-party market data publicly is outside the scope of what this project wants to do). Those tests skip cleanly when the cache is absent; the caching layer will re-fetch on demand where the code path calls for it.

## Project status

Development has proceeded in numbered phases, each with its own audit and report. As of the most recent phase, the human-operated simulated workstation is complete: CLI, dashboard, and MCP surfaces all read and act through one shared, tested domain layer, with 400+ tests passing.

Real broker and live-feed integration is a research question under active investigation, not an implemented capability. See the phase reports for the current state of that investigation.
