# User Guide

Practical, task-oriented usage. For what each phase of development
added and why, see `README.md` and `docs/PHASE_HISTORY.md`. For system
design, see `ARCHITECTURE.md`. For unattended/scheduled operation, see
`OPERATIONS_GUIDE.md`.

Every command below is `python main.py <command> [options]`. Run
`python main.py <command> --help` for the full option list of any of
them — this guide covers what each is *for*, not every flag.

## Before you start

```bash
python main.py readiness-check
python main.py health
```

`readiness-check` checks: Dhan credentials configured (informational —
not required for anything below), kill switch state, leftover pending
approvals from a prior session, historical cache freshness, and a
disk-write probe. `health` is the newer, complementary check — the
same source the dashboard's `/health` page reads — and additionally
covers `PRAGMA integrity_check` across every SQLite store, Ollama
reachability, scheduler lock state, and a single overall
HEALTHY/DEGRADED/SAFE_STOP/FAILED status (exits non-zero on FAILED, so
it's script-friendly). Run either after any long gap since you last
used the system, and before starting an unattended `schedule loop`.

## The market-intelligence pipeline (no order ever placed)

This is the research/recommendation half of the system. Nothing in it
can place a real or paper order on its own.

**One pass, everything chained:**

```bash
python main.py shadow-run --symbols AAPL,MSFT,RELIANCE.NS
```

**Or one stage at a time**, each persisting to its own SQLite store the
next stage reads:

```bash
python main.py scan --symbols AAPL,MSFT,RELIANCE.NS   # rank by trend/momentum/breakout
python main.py research --symbol AAPL                  # real news + sector evidence
python main.py decide --symbol AAPL                     # deterministic BUY/WATCH/AVOID/EXIT/NO_ACTION
python main.py size --symbol AAPL --initial-capital 100000   # preview position size, no order
python main.py predict --symbol AAPL                     # record a shadow prediction
python main.py evaluate                                   # score predictions against real outcomes
python main.py learn                                       # read-only performance/calibration report
```

**To also submit a real (paper) order** when a decision is a
risk-approved, critic-approved BUY — the one deliberate bridge between
the two pipelines, opt-in, never automatic:

```bash
python main.py shadow-run --symbols AAPL --paper-execute \
  --initial-capital 20000 --paper-db data/paper_trading.db --state-db data/live_state.db
```

`--paper-execute` requires all three of `--initial-capital`,
`--paper-db`, and `--state-db` together (the kill switch must be
checkable before any order is submitted).

## The intraday paper-trading pipeline

**Deterministic backtest** over historical data (no live loop):

```bash
python main.py backtest --symbol AAPL
python main.py backtest-universe --watchlist-file market_data/watchlists/starter_nse.yaml
```

**Simulated live replay** (mock data, bar-by-bar):

```bash
python main.py live-sim --symbol AAPL --interval 1d --period 1y
```

**Interactive human-operated workstation** — every signal stops for an
APPROVE/REJECT decision:

```bash
python main.py paper-live --symbol AAPL --interval 1d --period 1y
```

**With the real Dhan market-data feed** instead of mock replay (still
paper execution — see `SECURITY.md`):

```bash
python main.py paper-live --symbol RELIANCE.NS --source dhan
```

**Check current state** without advancing anything:

```bash
python main.py paper status
```

**The dashboard** (read-only web view over the same state):

```bash
python main.py dashboard
```

## Experiments and controlled learning

```bash
python main.py experiment start --name my-experiment --config-type decision_engine
python main.py experiment end --experiment-id <id>
python main.py experiment list
python main.py experiment compare --baseline-id <id> --candidate-id <id>
python main.py experiment recommend --baseline-id <id> --candidate-id <id>
```

`experiment recommend` never edits any config and never promotes
anything automatically — it returns an advisory recommendation, gated
by fixed evidence thresholds (30+ resolved predictions on both sides, a
10-percentage-point win-rate margin). Promotion is always a manual
step you take yourself, by changing the relevant config file.

## Scheduling (unattended operation)

See `OPERATIONS_GUIDE.md` for the full operational treatment. Briefly:

```bash
python main.py schedule tick --symbols AAPL,MSFT,RELIANCE.NS   # one check-and-maybe-run cycle
python main.py schedule loop --symbols AAPL,MSFT,RELIANCE.NS   # continuous, Ctrl+C to stop
python main.py schedule status                                  # per-slot last-success/last-failure summary + run history
```

## Watchlists and universe

```bash
python main.py universe --symbols AAPL,MSFT,RELIANCE.NS
python main.py universe --watchlist-file market_data/watchlists/starter_nse.yaml --with-dhan-ids
```

Describes each symbol's exchange/instrument metadata. No trading logic.

## AI features (Ollama required)

```bash
python main.py analyze --symbol AAPL     # full multi-agent analysis — requires Ollama
python main.py review --symbol AAPL       # adversarial second opinion on the latest decision — requires Ollama
```

Every other command works with no Ollama installed. `research` and
`decide` return their real evidence/label even if Ollama is
unreachable when their optional AI summary/narrative is requested —
the AI step never blocks (pass `--no-ai-summary`/`--no-narrative` to
skip it outright).

## Reading the output

- `[PASS]` / `[WARN]` / `[INFO]` prefixes in `readiness-check` and
  `cache-status` output mean exactly what they say — `[WARN]` is
  something worth looking at, not necessarily something broken.
- A decision label of `BUY`/`WATCH`/`AVOID`/`EXIT`/`NO_ACTION` always
  comes with recorded evidence (`decide`'s own output, or the
  `/intelligence/<symbol>` dashboard page) — there is no
  unexplained label anywhere in this system.
- "No real or paper order was placed by this command" in `shadow-run`
  output is literal and load-bearing — it is false only when
  `--paper-execute` actually submitted one, and the output says so
  explicitly in that case.

## Where state lives

Every SQLite store defaults to `data/<name>.db` under the project
root. See `ARCHITECTURE.md`'s persistence section for the full list,
and `.env.example` for how to override any individual path.
