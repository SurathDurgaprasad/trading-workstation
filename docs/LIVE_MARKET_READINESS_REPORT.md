# TradingAgents Live Market Readiness Report

Adversarial, end-to-end operational readiness audit. Real code
inspection, real regression runs, real fixes with real tests, and a real
dashboard inspected in a real browser — no fabricated live validation.
This audit could NOT test live Dhan connectivity itself: no
`DHAN_CLIENT_ID`/`DHAN_ACCESS_TOKEN` credentials exist in this
environment (`readiness-check` confirms `[FAIL]` on this exact check).
Every claim about live-feed behavior below is either (a) verified
against the real code paths and their existing test coverage, or (b)
explicitly marked as requiring an actual market session to confirm — see
`docs/MONDAY_LIVE_VALIDATION_PLAN.md` for the exact commands.

## 1. Executive Verdict

# **B — CONDITIONALLY READY**

This grade applies **only** to LIVE MARKET OBSERVATION + PAPER
VALIDATION. It does **not** imply real-money trading approval — the
system remains structurally incapable of placing real orders (no
`execute_trade`/`place_order`/broker-credential code path exists
anywhere in this codebase, confirmed by direct inspection and by the
existing `tests/test_dhan_no_real_orders.py` safety suite, which passed
throughout this audit).

**Why CONDITIONALLY, not fully READY**: the platform's paper-trading
core (risk engine, paper engine, kill switch, restart-safety) is
genuinely mature and well-tested. But three real, unresolved conditions
remain: (1) this audit could not test live Dhan connectivity at all —
no credentials exist in this environment, so the single highest-risk,
least-proven area (the live feed) is unverified by this session, only
by its existing mocked test suite; (2) the Dhan live feed and the
decision-engine/critic/scanner chain are two pipelines that have never
been wired together or tested end-to-end — an operator must understand
which command validates which half; (3) two real defects were found and
fixed this session (see Section 4) — their fixes are tested but have,
by definition, zero live-market track record yet.

**Why CONDITIONALLY, not NOT READY**: every defect found was fixed,
tested, and merged to `main` (verified `main == origin/main` after every
change). The safety-critical paths — kill switch, risk gates, restart
recovery, no-real-orders — are deeply tested and were not touched by
this audit except to add coverage. The gaps that remain are about
**observability and integration completeness**, not about the paper
engine being unsafe.

## 2. End-to-End Pipeline Status

**Architecture finding (the single most important fact for an operator
to understand before Monday)**: this codebase contains **two separate,
never-jointly-tested pipelines**:

1. **`shadow-run`** (optionally `--paper-execute`, or via `schedule
   tick`/`loop`): real function calls, no mocks between stages —
   `market_intelligence.scanner.run_scan` (Yahoo) →
   `research.summarizer` → `decision_engine.engine.make_decision` →
   `critic.engine.evaluate` → `risk.sizing.build_signal_for_buy` →
   `paper.engine.submit_signal` → `paper.advance` (re-fetches Yahoo,
   never the live feed) → `predictions.tracker` → `learning.analysis`.
   `--live-source dhan` only overlays a single live Dhan quote onto
   Yahoo-scanned candidates — it does not drive the scan itself.
2. **`live/pipeline.py` `LiveSimPipeline`** (`paper-live`/`live-sim`,
   `--source dhan`): Dhan WebSocket (or mock) feed → a plain
   `strategy.contracts.Strategy` (e.g. `TrendMomentumBaseline`) — **not**
   `decision_engine`/`critic`/the scanner — → `risk` → `paper`.

No test, and no production code path, connects a real Dhan tick to the
scanner/decision/critic chain. This is not a bug — the paper-execution
and risk mechanics are correctly shared underneath both pipelines — but
an operator validating "the live feed" (`paper-live --source dhan`) is
**not** thereby validating "the decision engine sees real prices," and
vice versa. `docs/MONDAY_LIVE_VALIDATION_PLAN.md` now states this
explicitly and separates validation of the two.

| Stage transition | Executes end-to-end? | Persisted? | Restart-recoverable? | Notes |
|---|---|---|---|---|
| Real data → source health → normalization | Yes (`shadow-run` path); Dhan candle-building is a separate leg | Yahoo: via scan/decision stores | Not directly applicable (stateless fetch) | Never tested against a real network call in either path (`tests/test_backtest_lookahead_real_data.py` explicitly asserts a real fetch would fail the test) |
| Candle building → scanner | Only within the Dhan/LiveSimPipeline leg; never feeds the scanner | Ticks are not persisted, only completed bars | N/A | See architecture note above |
| Scanner → decision → critic → risk | Yes, real function calls, `shadow-run` path | `decisions.db`, `scanner.db` | Yes (`test_full_pipeline_survives_a_restart_between_every_stage`, real, genuine cross-process-boundary restart) | No `scan_id` persisted onto the resulting `CandidateScore`/`Decision` — see Section 9 |
| Risk → paper order submission → pending | Yes | `paper.db` | Yes — idempotent by construction (`Signal.stable_id()` deduped inside `store.transaction()`), proven by `test_shadow_run_paper_execute_the_same_symbol_twice_is_idempotent`, which genuinely re-invokes the CLI command (a fresh cold-start, equivalent to a real process restart) | A concurrent-process race on the SAME `paper.db` is theoretically possible (SQLite autocommit mode) but not exercised anywhere in the codebase today |
| Pending → later data → fill logic | Yes | `paper.db` | Yes, dedicated Level-3 restart tests (`tests/test_paper_restart.py`: real file-backed SQLite, real process-boundary simulation, an uninterrupted run compared byte-for-byte against a paused/persisted/resumed one) | `paper/advance.py` re-fetches Yahoo fresh, never the live/streamed feed, even under `--paper-execute` |
| Fill → position monitoring → exit | Yes | `paper.db` | Yes (same restart tests) | Single-position-account invariant enforced; duplicate/out-of-order bars rejected via `OutOfOrderBarError` |
| Exit → prediction/outcome evaluation | Partially independent | `predictions.db` | Yes | **Real gap**: a prediction is recorded BEFORE the critic/risk execution gate runs — a prediction can show `TARGET_HIT` even if the corresponding paper order was rejected or never attempted. Predictions and paper fills are two parallel, not-cross-validated bookkeeping systems. |
| → Learning evidence → dashboard/audit trail | Yes | Reads across all stores directly | Yes (`test_dashboard_renders_exactly_what_a_real_shadow_run_persisted`, a genuine cross-store restart test) | Verified live in a real browser this audit (Section 5) |

**No test exercises the full requested chain in one continuous run
against a real network call.** The closest, `test_shadow_run_end_to_end_with_skip_evaluate_persists_every_stage`,
is fully wired logically but runs on a fake provider. This is expected
and appropriate for a CI-safe test suite — but it means **zero** of this
platform's automated tests constitute live-market proof; only an actual
Monday session can (see the validation plan).

## 3. Live Data Reliability

**This audit fixed two real, previously-unknown defects** in the Dhan
live-data path (both merged to `main`, both regression-tested):

1. **(Severe, now fixed)** `CandleBuilder.on_tick` trusted a tick's own
   timestamp unconditionally with no plausibility check — a single tick
   with a corrupted/wildly-future timestamp (e.g. a decode glitch)
   would seed a bucket dated far in the future, after which every
   subsequent genuine tick would be rejected forever as
   "late_out_of_order" with no self-recovery: **candle production for
   that symbol would permanently stop**. Worse, if the corrupted tick
   arrived mid-bucket, it could silently, prematurely finalize the real,
   still-accumulating bar early. Fixed by comparing each tick's
   timestamp against the builder's own last-known-good timestamp before
   any bucket logic runs — an implausible tick is now fully inert. One
   residual, documented limitation: a corrupted VERY FIRST tick (no
   prior timestamp to compare against) is not covered.
2. **(Moderate, now fixed)** `DhanMarketDataSource.subscribe()` mutated
   internal state per-symbol, inside its own resolution loop, before
   confirming the whole batch of symbols resolved. A multi-symbol
   subscribe where one symbol failed to resolve
   (`InstrumentNotFoundError`) left the resolved symbols partially
   registered internally yet never actually subscribed over the wire —
   an atomicity violation with **zero prior test coverage** (every
   existing `subscribe()` test passed exactly one symbol). Fixed by
   resolving the entire batch first, as a pure computation, and only
   mutating state once every symbol has resolved.

**What is well-built and already tested (mocked, not live)**:
connection lifecycle (initial connect, auth via URL query params per
Dhan's documented format, subscribe, disconnect, bounded exponential
backoff reconnect with flapping-connection storm protection — a
previously-real production incident, now regression-tested — and
server-initiated Disconnect(50) packet handling); the LTT-epoch
mislabeled-as-UTC bug (a real, previously-live incident, now fixed with
regression tests); tick plausibility (duplicate, late/out-of-order,
implausible-price-deviation, and now implausible-timestamp handling);
OHLC correctness under adversarial tick ordering.

**Explicitly acknowledged, not fixed (by design, not oversight)**: Dhan
provides no per-tick message/sequence ID, so exact-duplicate-tick
redelivery cannot be reliably deduplicated — harmless today only because
the project's actual configuration (Ticker-mode subscription) always
passes `volume=0.0`, making a redelivered duplicate a no-op. A price
move that crosses and returns past a stop/target entirely within a
disconnect gap can be missed by the paper engine — a known, documented,
unfixed gap (`docs/LIVE_DATA_STRESS_TESTING.md`).

**Zero of this has ever been tested against a real Dhan connection.**
Every Dhan test in this codebase uses a fake WebSocket transport. This
is the single largest unproven area, and this audit could not close it
— it requires real credentials and a real market session (see the
validation plan's Market Open section).

## 4. Failure & Recovery Results

Per the mandated engineering discipline, both real defects found above
were: reproduced with a failing test first, fixed minimally, regression
tested (full suite, 1500+ tests, run repeatedly throughout this audit),
safety-suite tested, secret-scanned, committed atomically, merged
`--ff-only`, re-tested post-merge, and pushed — `main == origin/main`
verified after every single change.

**Restart/crash recovery — verified, not merely assumed**:
`PaperTradingEngine`'s own state has dedicated "Level 3" tests (real
file-backed SQLite, real process-boundary simulation, comparing an
uninterrupted run byte-for-byte against one paused/persisted/resumed
from a freshly-opened store). `LiveSimPipeline` has its own separate
restart test. The `shadow-run --paper-execute` bridge has genuine
cold-start idempotency coverage (each CLI invocation is a fresh process
in all but name). **A narrower, still-open gap**: no single test
combines all three — a `shadow-run --paper-execute` submitting a
still-PENDING order, a genuine restart, and a later tick correctly
advancing that exact pending order. Assessed as P2 (see Section 10) —
the underlying mechanisms are proven separately at the layer that
matters most.

**Other failure modes checked this audit, via direct code inspection**
(not exhaustively chaos-tested — the mission's own instruction was to
find realistic corruption paths, not achieve 100% synthetic coverage):
kill switch is checked independently in both `live/pipeline.py` and
`paper/advance.py` (the latter added after a prior audit found the
original gap — evidence the project already takes this class of bug
seriously); scheduler lock contention is handled via `try_start_run`'s
own race-safe design with an explicit "lost the race" branch; a stale
`RUNNING` lock is reclaimed after a configurable staleness window.

## 5. Dashboard / UI/UX Status

**Actually run and inspected in a real browser this audit** (not judged
by unit tests alone), against real, previously-persisted historical
data in `data/paper_trading.db`/`data/scanner.db`/`data/decisions.db`/
`data/predictions.db`/`data/scheduler_runs.db`.

**Before this audit**: the dashboard (both `/` and `/intelligence`)
never stated the actual, completed strategy research conclusion
anywhere. The closest existing element — `/intelligence`'s own
"Profitability evidence" section — reports a verdict over a much
smaller, live `decision_engine` prediction sample (observed live this
audit: `INSUFFICIENT_DATA`, 3 unresolved predictions), a genuinely
different finding from the real research result and one an operator
could easily mistake for "not enough data yet, might turn positive."

**After this audit's fix**: a prominent, visually distinct (amber, not
the red danger banner) verdict banner — "SCIENTIFIC STRATEGY VERDICT:
NO DEMONSTRATED EDGE" with the real evidence summary — now appears on
every page, verified visually in a real browser on both `/` and
`/intelligence`, and covered by a new regression test.

**What was already good, confirmed by direct inspection**: the safety
banner ("SIMULATED PAPER TRADING — NOT connected to a live broker or
feed. No real order can ever be placed here.") is unconditional and
correct; the market-status banner already honestly disclosed its
holiday-blindness before this audit's fix and now correctly reflects a
configured calendar when one exists; empty states show clear, specific
guidance text ("No market data processed yet in this session — run
python main.py paper-live ... to start a feed") rather than blank
tables; kill switch and risk status are on the landing page, not buried;
a real historical paper account (101,331.83 equity, 32 total trades, 2
consecutive losses, 1.62% drawdown) rendered correctly with no crashes
or malformed output.

**Not independently verified this audit**: narrow-viewport/mobile
responsiveness, very large table rendering (the real data available had
at most ~20 rows per table), and long-symbol-name wrapping — the
dashboard's own CSS uses fixed-width grid columns
(`grid-template-columns: 220px 1fr`) that would likely handle these
reasonably but were not visually stress-tested.

## 6. LLM Contribution Verdict

**Optional / narrative, never decision-critical.** Verified by direct
inspection of every LLM call site reachable from the real trading
pipeline: `decision_engine.engine.narrate_decision`,
`agents.decision_reviewer`, `agents.signal_explainer`,
`research.summarizer` all produce Pydantic-typed output with **no field
capable of holding a price, quantity, label, or approval flag** —
enforced at the type level, not by convention. `risk/engine.py` and
`decision_engine/rules.py` are both confirmed, by their own module
docstrings and by dedicated LLM-independence tests
(`tests/test_backtest_llm_independence.py`,
`tests/test_decision_engine_llm_independence.py`, both AST-based import
scans, not just documentation claims), to contain zero LLM/I/O/
randomness. The kill switch is a direct SQLite read with no LLM code
path anywhere near it. The one schema shaped like a real trading
decision (`schemas.decision.TradingDecision`, via
`agents.supervisor_agent`) lives entirely inside the standalone,
print-only `analyze` CLI command — never persisted to any store, never
wired to execution. **LLM usage could be removed entirely with zero
loss to trading logic.** It adds human-readable explanation value only.

## 7. Market Intelligence Coverage

| Data Category | Available | Source | Real-time | Reliable | Used in decisions |
|---|---|---|---|---|---|
| Company news | Yes | Yahoo (`yfinance`) | No (polled) | Real, not fabricated | **No** — reaches `research/` narrative only, never `decision_engine.rules.classify()` |
| Sector classification | Yes | Yahoo | No | Real | No — narrative only |
| Benchmark/regime (e.g. `^NSEI` trend) | Yes | Yahoo | No | Real | **Partial** — the one real-world-context input that DOES feed the scanner's composite score |
| Market news, NSE/BSE/SEBI announcements, corporate actions, earnings, dividends, splits, bonus issues, bulk/block deals, global market context, India VIX, macro events | **No** | — | — | — | No — none of these exist in the codebase at all |

**Direct answer: the system does NOT make decisions with awareness of
important real-world events.** `market_intelligence/scanner.py`'s own
docstring states it is purely price/indicator-based. An earnings
surprise, a stock split, or a regulatory action against a company would
not be seen by this system at all — it would trade (in paper) purely on
price/volume technicals, oblivious to it. This is a real, honestly
disclosed gap, not a claim of coverage that doesn't exist.

**Architecture recommendation for future work** (not implemented this
audit, per the mission's own "design, don't rush-build" instruction):
separate deterministic event filters (a detected trading halt, a
scheduled earnings date, a flagged high-impact announcement — yes/no
facts) from LLM event interpretation (summarizing an unstructured
announcement's likely relevance) — never let the LLM invent an event
fact into persisted state, mirroring the same type-level discipline
already used for `TradingDecision`/`SignalExplanation` elsewhere in this
codebase.

## 8. Scientific Strategy Status

# **NO DEMONSTRATED EDGE.**

`TrendMomentumBaseline` (the active default strategy) was backtested
against a real 41-symbol universe over 5 years: 368+ trades,
statistically negative mean return, underperforms buy-and-hold decisively,
underperformed by 96% of random-entry Monte Carlo iterations. A
follow-up "Strategy Edge Discovery" research program tested the most
promising exit-logic variant (H_EXIT_002, partial profit-taking) to a
full 12-step protocol — INCONCLUSIVE, not promoted, and its own
units-corrected total-return comparison showed it performing marginally
*worse* than the frozen baseline despite an improved per-trade metric.
The first entry-side hypothesis tested (Pullback Continuation) produced
too few trades (29 total) to evaluate at all. No exit or entry variant
tested demonstrates a real edge. See
`docs/STRATEGY_EDGE_DISCOVERY_FINAL_OUTPUT.md` for the complete evidence
table and closing analysis. **This finding is now stated prominently on
every dashboard page** (Section 5) — it was not, before this audit.

## 9. Monday Operational Readiness

**Exact blockers, in priority order**:

1. **No live Dhan credential test possible in this environment.** This
   audit verified every Dhan code path by direct inspection and its
   existing (mocked) test suite, but the single highest-risk area — an
   actual live WebSocket connection — is genuinely unproven until a real
   market session runs. Not fixable from this session; the Monday
   validation plan's Market Open section is the actual test.
2. **Understand the two-pipeline architecture before choosing a
   command** (Section 2) — running `paper-live --source dhan` alone
   does not validate the decision-engine chain, and vice versa.
3. **Populate `config/schedule.yaml`** with the real current-year NSE
   holiday list before Monday (Step B3 of the validation plan) — without
   it, every session runs holiday-blind by default (the underlying code
   now supports cross-checking; it needs real data supplied).
4. **No structural blocker beyond the above.** `readiness-check` passes
   every check it can check outside a live session (credentials aside);
   the safety suite passes; `main == origin/main`.

## 10. Remaining Risks

**P0 (must not be worked around, not found this audit)**: none — no
defect found this audit compromises the paper-only guarantee or a risk
control.

**P1 (should be addressed before extended unattended live use)**:
- No persisted correlation between `predictions.db` and `paper.db` — a
  decision's own ID is never carried into the `Signal`/paper-journal
  chain, so reconstructing "what actually happened for this one
  decision" requires manually re-deriving a content hash rather than a
  stored join. Scoped fix identified (add an optional `decision_id`
  field to `Signal`, thread it through the paper bridge) but not
  implemented this audit — a genuine architecture change deserving its
  own reviewed change, not a rushed addition at the end of an already
  large session.
- Predictions are recorded before the critic/risk execution gate runs —
  a prediction can show a resolved outcome even when no corresponding
  paper order was ever attempted. Two parallel bookkeeping systems, not
  cross-validated.
- Logging has no structured output or correlation IDs — reconstructing
  a decision's lifecycle from logs alone is not possible; the SQLite
  stores are the only queryable source of truth.

**P2 (real but lower-impact)**:
- No single test combines shadow-run's paper-execute bridge with a
  genuine process restart mid-pending-order (Section 4) — the
  underlying mechanisms are separately proven, but the specific
  combination is untested.
- A stop/target crossed entirely within a Dhan disconnect gap may not
  trigger correctly — known, documented, unfixed (pre-existing finding,
  reconfirmed this audit).
- A `paper.db` write race under genuinely concurrent processes is
  theoretically possible (SQLite autocommit mode) but not exercised
  anywhere in the actual codebase today.
- Dashboard responsiveness at narrow viewport widths and with very
  large tables was not independently stress-tested this audit.

**P3 (documented, low urgency)**:
- `market/data_provider.py`'s Yahoo timestamp normalization strips
  tzinfo without converting to UTC first — flagged by this audit's own
  security/timezone research as a latent ~5.5h computation error IF this
  path is ever driven with an intraday interval against a tz-aware
  index; currently benign in actual usage (daily bars, and Yahoo bars
  are never routed through the freshness policy in the live wiring
  today).
- Market intelligence coverage gaps (Section 7) — a real, disclosed
  limitation, not a defect.

## 11. What Was Fixed

Only real, reproduced-then-fixed defects (all merged to `main`, all
regression-tested):

1. **Exchange holiday-calendar gap**: `current_market_session()` had no
   holiday awareness at all; a real NSE/BSE holiday on a weekday would
   be reported OPEN. Fixed with an opt-in-but-defaulted `holidays`
   parameter reusing the scheduler's own existing `ScheduleConfig`
   format, wired into `readiness-check`, `paper-live`, `shadow-run`, and
   the dashboard, with a conventional default config path so an operator
   who forgets a flag still benefits once the file is populated once.
   Caught and fixed a real ambiguity bug in this fix's own first draft
   (an empty-but-loaded holiday calendar was indistinguishable from
   "never checked") via its own test suite before it shipped.
2. **CandleBuilder timestamp plausibility** (Section 3, item 1) — severe,
   could permanently stop candle production or silently corrupt a bar.
3. **DhanMarketDataSource partial-subscription atomicity** (Section 3,
   item 2) — moderate, zero prior test coverage.
4. **Dashboard scientific-verdict visibility** (Section 5) — the
   platform never stated its own real research conclusion anywhere an
   operator would see it.

## 12. What Was Deliberately NOT Fixed

- **The two-pipeline architecture gap** (Dhan feed never wired to the
  decision-engine/scanner/critic chain) — a genuine, large integration
  project, not a bug with a minimal fix. Documented, not attempted.
- **The `predictions.db`/`paper.db` correlation-ID gap** (P1 above) — a
  real architecture change with a clear, scoped design identified, but
  deliberately not rushed into an already-large session without its own
  focused review.
- **The stop/target-across-disconnect-gap concern** — pre-existing,
  already documented, requires a design decision (e.g. re-checking
  open positions against the first bar after a reconnect) beyond this
  audit's scope.
- **Market intelligence expansion** (real news/events/corporate
  actions/VIX) — the mission's own explicit instruction was to design
  the correct architecture, not rush-build a scraper; a
  deterministic-filter/LLM-interpretation split is recommended
  (Section 7) but not implemented.
- **A live Dhan connectivity test** — genuinely impossible without real
  credentials in this environment; deferred to the Monday validation
  plan by necessity, not choice.

## 13. What Must Be Observed Monday

Live behaviors this audit could not validate during the weekend, listed
exactly (see `docs/MONDAY_LIVE_VALIDATION_PLAN.md` for commands):

- A genuine Dhan WebSocket connection reaching `CONNECTED`/`LIVE` state
  against the real service (not the fake transport every test uses).
- Real tick-to-candle production during actual market hours, including
  whether the new `implausible_timestamp` rejection ever fires on
  genuine data (it should not, on a healthy feed).
- A real reconnect after a genuine network interruption (only ever
  tested against a fake transport that always "succeeds" on retry).
- Whether the holiday-calendar cross-check correctly reports CLOSED on
  the next actual configured holiday (requires waiting for one, or a
  deliberately-configured test date near a real session).
- End-to-end human-approval-gate behavior against a real, live-generated
  signal (tested extensively against mock/replayed data, never a live
  one).
- Whether `paper/advance.py`'s Yahoo re-fetch (used even under
  `--paper-execute`) has any real-world latency/staleness interaction
  with a concurrently-running live Dhan session that this audit's
  code-only inspection could not surface.
