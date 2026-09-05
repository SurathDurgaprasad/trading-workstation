# Live Data Stress Testing

Strategy science mission, Phase 13. Markets are closed at the time this
audit was run (Saturday), so this reviews the live data pipeline's
resilience to adversarial/malformed conditions via its existing and new
test coverage, rather than an actual live session. Source of truth is
always the code and tests, not this document.

## What was already well-covered before this phase

`tests/test_dhan_market_data_source.py`, `tests/test_dhan_wire.py`, and
`tests/test_dhan_candle_builder.py` already covered: WebSocket disconnect
mid-session and bounded reconnect, malformed/truncated wire packets dropped
without crashing, duplicate ticks at the same timestamp, out-of-order ticks
within a bucket, a late tick from an already-closed bucket, a connection
that fails before ever opening, a server-sent Disconnect packet, a
duplicate on_error+on_close pair for the same failure (a real, previously
root-caused Dhan-side 429 scenario), and a flapping connection still
hitting its reconnect bound. This is genuinely thorough coverage for the
transport and reconnection layer.

## Gap found and closed this phase: no tick-level sanity validation

**Before this phase**: a single corrupted-but-well-formed tick (a positive
float, so `OHLCVBar`'s own `Field(gt=0)` schema constraint never caught it)
flowed straight into `CandleBuilder`'s bar aggregation with zero
resistance. A garbage price — a decimal-point error, a units mismatch, any
upstream corruption that still produces a syntactically valid positive
number — would become a bar's high/low/close and flow downstream into
`strategy.generate_signal()` unchallenged. This is the most directly
exploitable path from bad feed data to a bad signal, for a project whose
core promise is never trading on bad data.

**Fixed**: `live/dhan/candle_builder.py`'s `CandleBuilder.on_tick()` now
rejects (logs and drops, never merges into a bucket):
- non-positive price,
- negative volume,
- a price deviating more than `max_tick_deviation_pct` (default 20%,
  configurable, `None` disables the check) from the last genuinely REAL
  price accepted.

The comparison baseline (`_last_known_price`) persists across bucket
rollovers, not just within one bucket — so a garbage tick opening what
would be a fresh bucket is caught too, not only garbage arriving mid-bucket.

**A real design subtlety, caught by an existing test failing first**: an
implausible tick's *timestamp* can still legitimately complete an
already-elapsed prior bucket, even though its *price* is rejected — bucket
completion is a question of elapsed exchange time, which remains
trustworthy independent of whether this specific tick's price is. Rejecting
the price must never also silently delay finalizing an already-complete,
otherwise-legitimate bar until some later, unrelated tick happens to
arrive. `on_tick` separates these two concerns explicitly: a
boundary-crossing tick always finalizes the prior bucket when its timestamp
warrants it, but only a genuinely valid tick ever seeds or merges into
either bucket's OHLC.

8 new tests in `tests/test_dhan_candle_builder.py` cover: non-positive
price dropped without corrupting the bucket, negative volume dropped, a
10x implausible spike dropped, a genuine 5% move still accepted (proving
the check isn't overly strict), the very first tick ever accepted
regardless of magnitude (a known, documented scope limit — no prior real
price exists yet to compare against), the persistence-across-rollover
behavior, the boundary-crossing-still-completes-the-prior-bucket behavior
above, and `max_tick_deviation_pct=None` disabling the check entirely. All
20 pre-existing candle-builder tests, plus the full 68-test Dhan/live
pipeline surface, pass unchanged.

## Gaps found and NOT fixed this phase (documented, flagged)

Both require touching execution/gap-handling semantics in
`PaperTradingEngine` or adding new watchdog infrastructure — larger,
riskier changes than a self-contained validation function, and not
attempted speculatively.

1. **A gap during a disconnect can silently skip a stop/target trigger.**
   `CandleBuilder` correctly never manufactures a synthetic bar for a
   silent period ("do not manufacture a price," by design). But
   `PaperTradingEngine.process_bar`'s own gap-detection
   (`_GAP_WARNING_THRESHOLD`) is explicitly observational only — it logs a
   warning, never rejects or specially handles a large gap. If price moved
   through and back past a stop/target level entirely within a disconnect
   window, the check against the next real bar's own high/low may never
   see the breach. This is a genuine correctness gap for a system whose
   paper-trading results are meant to validate real-money-safe logic
   before it is trusted, and it is not exercised end-to-end by any current
   test (no test asserts on stop/target behavior across a reconnect gap).

2. **No watchdog for total feed silence.** `FreshnessPolicy` only ever
   evaluates when a bar actually arrives — if the feed goes fully silent
   (zero ticks, so `CandleBuilder` never finalizes anything),
   `process_next()` just keeps returning `NO_NEW_DATA` forever, and
   freshness is never checked at all (there is no bar to check it against).
   The dashboard's feed-status table does render a growing "age" column a
   human would eventually notice, but there is no automated
   alert/kill-switch trigger tied to "no data for N minutes during market
   hours." Given this project's fail-closed philosophy elsewhere (the kill
   switch, human-approval gating), a silent-feed watchdog is a natural
   candidate for a future phase, currently missing in both code and tests.
