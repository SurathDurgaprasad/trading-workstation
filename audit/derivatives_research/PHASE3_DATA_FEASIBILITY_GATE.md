# Phase 3 — Data Feasibility Gate

Classification per the mission's own four-way scale, checked against its own nine minimum
requirements: timestamped observations; known contract identity; known expiry; known strike where
applicable; no future contract leakage; sufficient historical coverage; reproducible retrieval;
deterministic parsing; auditable missing-data behavior.

## Classification table

| Candidate information source | Classification | Why |
|---|---|---|
| **Futures OI (level)** | **A — Historically usable** | Directly verified real, nonzero data via Dhan `/charts/historical`(`oi=true`); NSE bhavcopy carries the same field. All nine minimum requirements met, with ONE flagged engineering complexity (contract rollover — see below), not a data-availability gap. |
| **Futures OI change** | **A** | Directly derivable from the same OI-level series (or read directly from NSE bhavcopy's own `CHG_IN_OI` column). Same requirements met. |
| **Futures basis (futures price − spot price)** | **A** | Both legs (futures OHLC, spot OHLC) independently verified with real, matching-granularity historical data. The strongest, cleanest candidate — direct reuse of already-mature spot-price infrastructure from the closed OHLCV research. |
| **Futures premium/discount** | **A** | Same as basis — a normalized variant of the same two data legs. |
| **Futures volume** | **A** | Directly present in both NSE bhavcopy and Dhan futures OHLC responses, verified real. |
| **Spot/futures divergence** | **A** | Same two data legs as basis; a different framing of the same well-supported pair. |
| **Open interest (options)** | **A** | Directly verified in both NSE bhavcopy (`OPEN_INT`/`OpnIntrst`) and Dhan `/charts/rollingoption` (`oi`). Contract identity is explicit (strike+expiry+type from bhavcopy; strike returned per-bar from Dhan). |
| **Options OI change** | **A** | Derivable from the level series (bhavcopy has a direct `CHG_IN_OI` column; Dhan requires a simple bar-to-bar difference). |
| **Option volume** | **B — Partially usable** | Real data exists in both routes, but the quantified illiquidity finding (85.8% zero-volume OPTSTK rows, 75.2% zero-volume OPTIDX rows in a real sampled bhavcopy) means naive use is dominated by economically meaningless noise. Usable ONLY with a disclosed, pre-registered liquidity filter (e.g., near-ATM, front-month) — not usable as a raw, unfiltered feature. |
| **OI/volume interaction** | **B** | Same liquidity-filtering requirement as option volume above; otherwise the underlying data is real and available. |
| **Options positioning (OI-pattern-inferred)** | **B** | The raw data (OI, OI change, volume) is real and available, but "positioning" as a concept requires additional interpretive construction not yet scoped or built — genuinely constructible, but with more researcher-degrees-of-freedom risk than a direct basis/OI-level measure; any signal built here needs a tightly pre-registered, narrow operational definition to avoid becoming a disguised data-mining exercise. |
| **ATM/OTM implied volatility (level)** | **B** | Dhan `/charts/rollingoption` gives real, ready-made IV directly — no pricing model needed — but ONLY for the specific relative-strike position requested per call (ATM, ATM+1, etc.); NSE bhavcopy has NO ready IV field at all (would require building an option-pricing/inversion engine from scratch, a substantial new capability this project does not have). Usable via the Dhan route, single-moneyness-slice at a time. |
| **IV skew (put IV vs. call IV, or across strikes)** | **B** | Constructible from real data, but requires MULTIPLE separate `/charts/rollingoption` calls (one per relative strike offset and/or option side) rather than one call returning a full skew — a real, disclosed multi-call aggregation requirement, not a blocker, but genuinely more engineering-intensive than a single-leg signal. |
| **IV term structure (across expiries)** | **B** | Same multi-call aggregation requirement as skew, but across `expiryCode`/`expiryFlag` combinations instead of strikes — the most call-intensive of the IV-based families. |
| **Option-chain structure (full chain, historical)** | **B** | Neither route alone gives a complete, absolute-strike, IV-annotated historical chain: NSE bhavcopy gives the full chain but no IV and EOD-only; Dhan gives real IV but only a relative-moneyness window. A genuinely complete historical chain would require combining both routes — real, but substantial, engineering, deferred unless a narrower single-route signal (basis, OI, or single-moneyness IV) already shows promise (per the mission's own Phase 6 "smallest set" instruction). |
| **Put/call structure (e.g. PCR)** | **B** | Real data exists on both legs (call OI/volume, put OI/volume), but — like skew — requires separate calls/rows for each side, and (per the option-volume finding) needs the same liquidity-filtering discipline before any ratio is meaningful. |
| **Index/constituent derivatives divergence** (index futures/options positioning vs. aggregate constituent positioning) | **B, least mature** | Every underlying data piece exists (index futures/options data, all confirmed available; the SAME data for every individual stock, also confirmed available) — but this is a genuinely more complex, multi-symbol AGGREGATION signal with no existing scoping, no prior research pattern to reuse, and the most researcher-degrees-of-freedom risk of any candidate on this list. Explicitly the lowest-priority candidate — not pursued unless a simpler family (futures basis or OI-level) is validated first and a specific, narrow, economically-motivated reason to extend to this family emerges. |
| **Current-snapshot option chain (Greeks, IV, OI, bid/ask, "as of right now")** | **C — Current-only** | `/optionchain` (real-time) has NO historical/date parameter at all — directly confirmed from the documented request structure (only `Expiry`, no `fromDate`/`toDate`). Usable only for a future live/paper-trading signal, never for backtesting. |
| **Dhan WebSocket OI/Full packets** | **C — Current-only** (and not even currently reachable) | Real-time-only by nature; additionally, the live pipeline doesn't subscribe to the packet types that carry OI today (Quote mode, equity segment only) — would require new live-infrastructure work to reach even for a future promoted signal, entirely separate from this backtesting-research phase. |
| **yfinance-derived options data (any field)** | **D — Unavailable** | Directly tested this session: `yf.Ticker("RELIANCE.NS").options` returns an empty tuple. No options capability exists for NSE symbols via this already-relied-upon provider. |
| **Historical option-chain reconstruction at ARBITRARY absolute strikes, intraday, with ready IV, for the full 10-year OHLCV research window** | **D — Unavailable as a single, complete capability** | No single route provides all of: intraday resolution + absolute (not relative) strikes + ready-made IV + the full 10-year window, simultaneously. This specific, maximal combination is not achievable with currently accessible sources — a real, disclosed ceiling, not something to work around by quietly combining partial sources without disclosure. |

## Primary conclusion for Phase 4 scoping

**Futures basis, futures OI/OI-change, and options OI/OI-change are the strongest (Classification A)
candidates** — they meet all nine minimum requirements cleanly, draw on already-verified real data
from BOTH NSE bhavcopy and Dhan's live API, and (for futures basis specifically) directly reuse
already-mature spot-price infrastructure from the closed OHLCV research. The one flagged engineering
complexity for the futures side is **contract rollover** — a genuinely new problem (each month's
futures contract has its own distinct Dhan `securityId`; a continuous basis series requires
stitching consecutive contracts together under an explicit, pre-declared rollover rule) — not a
data-availability gap, and explicitly listed as a required test case in the mission's own Phase 4
engineering rules.

IV-based signals (level, skew, term structure) are real and available (Classification B) but carry
meaningfully more engineering overhead (multi-call aggregation, no direct expiry-date field from
Dhan's rolling endpoint, no IV at all from the NSE bhavcopy route) and are therefore **not** the
first candidate for the Phase 6 information-content test, per the mission's own "choose the smallest
economically motivated set" instruction — held in reserve as a natural second family if the futures
-basis/OI family is validated and a further, separately-scoped experiment is warranted.

**Decision: Phase 4's minimal data layer will be built around futures OHLC+OI (with explicit
rollover handling) and options OI/OI-change (from the already-partially-built NSE bhavcopy parser,
extended to surface the fields it already reads but currently discards) — not around IV/skew/term
-structure, which remain a disclosed, real, but lower-priority capability for a possible future
phase.**
