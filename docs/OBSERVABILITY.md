# Observability

Strategy science mission, Phase 16. Reviews whether the system has
adequate visibility into its own operation for an operator to trust and
debug it, distinct from the dashboard's user-facing state views.

## What was found already solid

- **No silently-swallowed exceptions in safety-critical paths.**
  `risk/engine.py` and `paper/engine.py` catch nothing themselves — any
  error in risk evaluation or fill/exit logic propagates loudly, never
  hidden. Every `except Exception:` found elsewhere (`paper/store.py`,
  `scheduler/store.py`, `market_intelligence/store.py`, `live/state_store.py`,
  and this session's own `strategy/promotion_store.py`) is the same
  ROLLBACK-then-`raise` transaction pattern — never a silent catch.
  `live/dhan/market_data_source.py`'s few broad catches are explicitly
  documented (`# noqa: BLE001` with a stated reason) and route the failure
  into observable reconnect state (`_last_disconnect_reason`,
  `_reconnect_attempts`) rather than discarding it.
- **Logging is properly configured, not just called.** `core/logging.py`'s
  `setup_logging()` (formatted, timestamped, level-controlled stdout
  output) is called unconditionally at the top of `main()`, before any
  command dispatch — so it applies to every CLI command including this
  session's own new ones (`readiness-check`, `cache-status`). A
  `RotatingFileHandler` (`add_rotating_file_handler`) already exists for
  long-running operations like `schedule loop`, added alongside (not
  replacing) the stdout handler, with idempotency against duplicate
  attachment. This means Phase 13's new `CandleBuilder` rejection warnings
  are genuinely visible to an operator running any command, not silently
  discarded by an unconfigured root logger.

## Gap found and closed this phase: logged-but-not-counted tick rejections

Phase 13 added `CandleBuilder` tick-plausibility rejection (non-positive
price, negative volume, implausible deviation, late/out-of-order) with a
`logger.warning()` call at each rejection site. A log line alone isn't
queryable without grepping — an operator (or the Monday validation plan's
own Step 1 checklist item, "check the log for rejection warnings") had no
programmatic way to ask "how many bad ticks has this session seen."

**Added**: `CandleBuilder.rejected_tick_counts: dict[str, int]` — running
counts by reason (`non_positive_price`, `negative_volume`,
`implausible_deviation`, `late_out_of_order`), incremented alongside each
existing log call, never reset automatically (one instance covers one
symbol/interval for the life of the process). `DhanMarketDataSource.
rejected_tick_counts_by_symbol()` aggregates every subscribed symbol's own
counts into one queryable snapshot across the whole feed.

7 new tests: per-reason increments on `CandleBuilder` directly (including
confirming a valid tick never increments any counter), and one end-to-end
test proving a bad tick arriving over the REAL struct-packed wire format
(not a hand-built dict) still reaches the aggregated counter via
`DhanMarketDataSource`.

## Scope note

This is deliberately a small, targeted addition (counters for one
already-identified risk area), not a new metrics/observability
infrastructure build-out. A full metrics stack, structured JSON logging,
or a log aggregator would be disproportionate new infrastructure for a
single-user, local paper-trading research tool — not attempted here, and
nothing in this project claims that capability exists.
