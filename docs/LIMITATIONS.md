# Limitations

This document is deliberately candid. A public research/engineering portfolio is worth
more when it states plainly what does not work, what was never proven, and what remains
unknown — that is the evidence a reviewer actually needs, not a features list.

## 1. No demonstrated trading edge

**69 hypotheses tested across this project's full research history. 0 promoted.**

| Research program | Hypotheses | Verdict |
|---|---|---|
| OHLCV/technical (entry/exit variants, mean reversion, breakout, momentum, cross-sectional, market/sector/VIX context, calendar/gap/breadth) | 59 | 36 REJECTED, 22 INCONCLUSIVE, 1 SUPPORTED (a confirmed *non*-edge) |
| Derivatives (futures basis/OI, options IV/skew) | 4 | All "no meaningful incremental information" |
| ML (triple-barrier baseline) | 1 | "No evidence of economic edge" |
| Corporate-event and cross-sectional relative (final edge-discovery mission) | 5 | All REJECTED |
| **Total** | **69** | **0 promoted** |

No hypothesis has ever cleared `strategy/promotion_gate.py`'s own promotion criteria
(all three of development/validation/out-of-sample periods confidently positive). The
two strongest raw measurements found anywhere in this history — a cross-sectional
laggard-reversal effect and a point-in-time-corrected single-symbol mean-reversion
result — both independently die at the portfolio/execution stage, not the
signal-detection stage: real price patterns can be *measured*, but none survive
becoming a tradable, cost-aware, portfolio-realistic strategy at this account size and
cost structure. See [`RESEARCH_RESULTS.md`](RESEARCH_RESULTS.md) for the full,
per-hypothesis breakdown and [`EDGE_DISCOVERY_FINAL_REPORT.md`](EDGE_DISCOVERY_FINAL_REPORT.md)
for the terminal conclusion.

**This is not a "not yet profitable" system. It is a system that was rigorously tested
and found, so far, to have no defensible edge.** The research program is closed, not
paused; do not read continued engineering activity on this repository as evidence the
strategy question is still open.

## 2. No validated live trading profitability

Because there is no demonstrated edge, there has never been an attempt at real-money
validation, and none is planned. Live sessions that did run (see
[`LIVE_VALIDATION.md`](LIVE_VALIDATION.md)) validated *operational* correctness —
market-data connectivity, candle construction, fleet supervision, dashboard honesty —
never trading profitability. Historical backtest results, however carefully produced,
are not future results, and this project makes no claim otherwise.

## 3. Data limitations

- **Equity OHLCV**: Yahoo Finance (`yfinance`) only. No independent data-quality audit
  beyond this project's own row-level sanity filters (impossible OHLC relationships,
  NaN rows dropped). Intraday (1m/5m) history is capped at roughly 60 trading days by
  Yahoo's own retention policy — too short for some calendar-effect research (see
  `H_OPENRANGE_001`, `RESEARCH_RESULTS.md`).
- **Point-in-time universe**: only one hypothesis (`H_MEANREV_014`) was tested against a
  survivorship-bias-corrected, point-in-time symbol universe (built from real NSE F&O
  bhavcopy archives). Every other hypothesis in the registry applies *today's* current
  F&O-eligible universe uniformly across a historical window — a known, disclosed,
  unresolved limitation (`docs/MASTER_KNOWN_ISSUES.md`, item R1). Where it *was* tested,
  point-in-time correction only ever made an effect weaker, never stronger — a real,
  if inferred-by-precedent, reason to expect it would not reverse any conclusion here.
- **Market microstructure**: no historical bid/ask, order-book, or trade-direction data
  exists anywhere in this project or via any free source it uses. Family B of the final
  edge-discovery mission (market microstructure) was closed on this data gap alone,
  without ever writing a hypothesis — genuinely untested, not tested-and-failed.
- **Corporate/event data**: only dividend/split history (yfinance) was available with
  real depth; earnings-date coverage for NSE tickers was found unreliable/blocked
  (missing `lxml` dependency, uncertain Yahoo calendar quality for Indian tickers) and
  was deliberately not pursued rather than built on uncertain data.
- **Cross-sectional/sector data**: a small, hand-built, incomplete (21–32 of 208 symbols)
  sector map, not sourced from an official index-constituent list.

## 4. Dependency on a single retail-grade data/broker provider

Real-time market data comes from a single broker integration (Dhan, `live/dhan/`).
There is no fallback data provider for live operation — a Dhan outage or API change is
a single point of failure for the live path. Historical/offline research depends
entirely on Yahoo Finance, an unofficial, best-effort data source with no SLA.

## 5. Market-data interruptions are real and were observed live

Live sessions recorded multiple real feed interruptions of varying causes: idle-timeout
reconnects, Dhan-side connection caps (`code=805`, a 5-connections-per-client-ID limit),
and at least three occurrences of an unexplained ~15-minute, fleet-wide interruption
around the same time of day, whose root cause remains genuinely unproven despite
investigation (see `docs/DHAN_FEED_INTERRUPTION_1514_INVESTIGATION_2026-09-22.md`). The
system's resilience mechanisms (gap detection, reconnect, staleness suppression) were
proven to work correctly under these conditions — but the underlying cause of the
recurring pattern is still unknown.

## 6. Latency and execution realism are unverified for real trading

This is a paper-trading system; there is no real-order path (see
[`SAFETY.md`](SAFETY.md)), and so there has never been a real fill, real slippage
measurement, or real latency profile to validate against. The cost model
(`backtesting/costs.py`) uses realistic-but-assumed NSE brokerage/fee/slippage figures
(~0.21% round-trip), not measured real-execution data. Any future live-execution attempt
would need its own, separate validation of these assumptions — this project does not
provide it.

## 7. Retail account constraints modeled, not fully explored

Position sizing and portfolio realism (fixed capital, max exposure, position caps) were
tested for the mean-reversion and cross-sectional families and were themselves a
primary cause of those hypotheses' rejection (fixed brokerage fees dominate small
position sizes; capacity/clustering limits reduce concurrent-position strategies'
realized returns below their raw signal-level returns). No general-purpose
multi-symbol portfolio/correlation-risk engine exists — the two portfolio-realism
implementations that do exist (`quant_research/mean_reversion_portfolio.py`,
`quant_research/cross_sectional_portfolio.py`) are narrowly scoped to their own
hypothesis families, not reusable infrastructure.

## 8. Risk-model limitations

- `RiskEngine` is fail-closed and deterministic, but its position-sizing and exposure
  logic have not been independently stress-tested against extreme, correlated
  multi-symbol drawdown scenarios beyond what the fleet's own per-symbol isolation
  provides.
- The consecutive-loss circuit breaker, max-exposure limit, and per-trade risk
  percentage are fixed defaults (`risk/config.py`), not tuned or validated against any
  edge — because there is no edge to tune them against.

## 9. No real-money execution, by design — not a roadmap item

See [`SAFETY.md`](SAFETY.md) for the full detail. This is listed here for completeness:
there is no partially-built real-order path, no "almost there" execution adapter, and no
plan to add one. `DisabledDhanOrderExecutor` raises unconditionally from every
order-mutating method; a real Dhan credential only ever enables read-only account calls
and the market-data feed.

## 10. Advisory LLM layer is exactly that — advisory

The optional LLM layer (Ollama by default, or OpenAI opt-in — `agents/`, `llm/`,
`graph.py`) can explain, narrate, or critique a decision, but no LLM-output schema in
this codebase has a field that could carry a quantity, price, stop, target, or approval
— enforced at the type level, not merely by prompt instruction (verified by
`tests/test_ai_output_cannot_carry_trading_authority.py`). Prompts in this layer are
unversioned (no `PROMPT_VERSION` field recorded alongside AI output), a disclosed,
accepted gap for a single-user research tool, not a production LLM-ops posture.

## 11. Single-user, local-first design — not built for scale or multi-tenancy

The dashboard binds to loopback by default and has no CSRF protection on its
state-changing routes (accepted for the local-only threat model — see
[`SECURITY.md`](../SECURITY.md)). There is no authentication layer anywhere. Do not
expose the dashboard to an untrusted network.
