# Safety: why real-money execution is structurally impossible

This document exists to answer one question precisely: **can this codebase ever place a
real order?** The answer is no, and this page explains exactly why, how that is
verified, and why the guarantee cannot be configured away.

This is a narrower, trading-specific companion to [`SECURITY.md`](../SECURITY.md) (which
covers the full security posture — credentials, dependencies, application-layer
findings). Read this page if the only question you have is "can this system lose me
real money," and `SECURITY.md` for everything else.

## The guarantee

There is no code path anywhere in this repository that can submit, modify, or cancel a
real brokerage order. This is not a configuration flag, a default that happens to be
off, or a missing feature — it is a structural property of the code:

```
live/dhan/broker_adapter.py
  class DisabledDhanOrderExecutor:
      def place_order(...):   raise RealOrderPlacementDisabledError(...)
      def modify_order(...):  raise RealOrderPlacementDisabledError(...)
      def cancel_order(...):  raise RealOrderPlacementDisabledError(...)
```

Every order-mutating method **raises unconditionally, before any other logic runs**.
There is no branch, flag, or code path that reaches a real HTTP call from any of these
three methods. This is a deliberate design choice, not an unimplemented feature: a real
executor was never written, so there is nothing to accidentally enable.

## How this is verified, not just asserted

1. **`RealOrderPlacementDisabledError`** is a dedicated exception type — a caller cannot
   mistake it for a transient failure and retry past it.
2. **A repository-wide search finds zero `requests.post` / `requests.put` /
   `requests.delete` calls anywhere in the codebase.** The only HTTP methods used
   against Dhan are `requests.get`, in `live/dhan/rest_client.py` (read-only account
   endpoints: funds, positions, holdings) and `live/dhan/clock_skew.py`. There is
   structurally no HTTP verb in this codebase capable of writing to Dhan's order
   endpoints.
3. **`DisabledDhanOrderExecutor` is constructed only in
   `tests/test_dhan_no_real_orders.py`** — it never appears in `main.py`,
   `live/pipeline.py`, `live/workstation.py`, `mcp_server/server.py`, or any other
   production code path. The paper-trading engine (`paper/engine.py`) is the only thing
   that ever "fills" an order, and it only ever writes to its own local SQLite database.
4. **The MCP tool server exposes 23 tools — all read-only or paper-only.** No
   `place_order`-shaped tool exists anywhere; an AI assistant connected via MCP has the
   same structural inability to place a real order as the CLI or dashboard.
5. **A dedicated regression test, `tests/test_dhan_no_real_orders.py`, asserts this
   directly** (not by inference from the above, but by calling each of the three
   methods and asserting `RealOrderPlacementDisabledError` is raised) and is re-run on
   every change to this codebase.

## Why a configuration change cannot bypass this

There is no environment variable, CLI flag, or config file value that swaps
`DisabledDhanOrderExecutor` for a real implementation, because **no real implementation
exists in this repository.** "Enabling real orders" is not a switch to flip — it would
require *writing new code*: a new class implementing the same interface with real
`POST`/`PUT`/`DELETE` calls to Dhan's order endpoints, then wiring it in place of
`DisabledDhanOrderExecutor` at every call site. That code does not exist today, has
never existed, and is not part of this project's roadmap. Populating `DHAN_CLIENT_ID`/
`DHAN_ACCESS_TOKEN` with real credentials only enables the **read-only** account/market-
data calls (`live/dhan/rest_client.py`'s three `GET` endpoints, and the market-data
WebSocket) — it has no effect on the order-execution boundary, because nothing on that
boundary reads those credentials in the first place.

## What "paper trading" actually means here

Every trade this system ever "executes" is a row written to a local SQLite database
(`paper/store.py`), simulating a fill against real or simulated market data with no
brokerage interaction at all. Paper trading is not a mode that happens to be selected by
default — it is the only mode that exists. The account balance, positions, and P&L you
see in the dashboard or CLI are entirely local bookkeeping; they never touch a real
account anywhere.

## Human-approval and risk layers (defense in depth, not the primary guarantee)

Even though real execution is structurally impossible, the system still enforces a real
risk-control chain on every paper signal, so that the *simulation* behaves like a
disciplined trading system rather than an unconstrained one:

- **`RiskEngine`** (`risk/engine.py`) evaluates every signal against position sizing,
  exposure limits, and a NaN/Infinity guard on every safety-relevant numeric input,
  before a signal can become an order — fail-closed by design (a malformed or
  out-of-range input is rejected, never silently approved).
- **`CriticGate`** (`critic/engine.py`) independently re-examines a proposed trade
  across 13 named checks (kill switch, data freshness, duplicate exposure, evidence
  completeness, regime conflict, risk/reward, confidence integrity, and more) before it
  reaches risk sizing.
- **A persistent, disk-backed kill switch** — read fresh on every check, never cached —
  can halt all new signal processing at any time, and every activation/reset is logged.
- **The optional human-approval workflow** (`--require-human-approval`, the default for
  interactive use) requires an explicit human decision before a signal becomes an order,
  with a *second*, independent risk check at the moment of approval (closing a
  time-of-check/time-of-use gap where market or account state could have changed between
  signal generation and approval).
- **No LLM output can ever influence a trade.** The optional AI narration/explanation
  layer (Ollama or OpenAI, see `SECURITY.md`) produces schemas with no field that could
  carry a quantity, price, stop, target, or approval — proven by field-set inspection
  and a dedicated poison-field test (`tests/test_ai_output_cannot_carry_trading_authority.py`),
  not merely a prompt instruction.

None of this is what makes real execution impossible — the disabled executor is what
does that. These are the controls that make the *paper* simulation behave like a real
risk-managed trading workflow, which is the point of the exercise: this project is a
testbed for the discipline of the pipeline, not a shortcut to real trading.

## What to do if you fork this project and want real execution

This document deliberately does not provide instructions for bypassing the disabled
executor, because none should exist: real-order execution was never a completed,
audited feature of this project, and the strategy this system runs has **no
demonstrated trading edge** (see [`docs/RESEARCH_RESULTS.md`](RESEARCH_RESULTS.md)).
If you fork this project and choose to implement real order execution yourself, you are
taking on that risk entirely on your own, with your own code, your own audit, and your
own money — this project provides no support, guidance, or endorsement for doing so.
