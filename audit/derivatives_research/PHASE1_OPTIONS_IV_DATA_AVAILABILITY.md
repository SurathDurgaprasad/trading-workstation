# Phase 1 — Options Volatility-Surface Data Availability

Final controlled derivatives pass (2026-09-21, continuing from `8f6c9cb`). Question: does the options
implied-volatility surface (level, skew, term structure, call/put asymmetry) provide incremental
predictive information beyond OHLCV+futures? This phase audits data availability before building
anything, extending (not repeating) the prior pass's own Phase 1 findings
(`audit/derivatives_research/PHASE1_DATA_INVENTORY.md`).

## The only route to historical IV: Dhan `/charts/rollingoption`

Already established in the prior pass: NSE bhavcopy carries **no IV field at all** (would require
building an option-pricing/inversion engine — out of scope, not attempted). Dhan's `/optionchain` is
current-only (Classification C, confirmed again this phase via `/optionchain/expirylist`, which
returns only forward-looking expiries from today — no historical capability at all). **Dhan
`/charts/rollingoption` remains the only source with real, ready-made historical IV.** All findings
below are from new, real, live, credentialed verification calls made this phase (not re-citing the
prior pass without re-checking).

## Field-by-field availability (real API responses, this session)

| Field | Available? | Detail |
|---|---|---|
| Underlying | Yes | Via `securityId` (index or stock) — confirmed working for NIFTY (13) and RELIANCE (2885) in the prior pass |
| Timestamp | Yes | Real, IST-aligned epoch timestamps, verified previously (09:15 IST = NSE open) |
| Expiry | **No, not directly** | The request uses a RELATIVE selector (`expiryFlag`+`expiryCode`), not an absolute date; the response contains no expiry-date field. `/optionchain/expirylist` (the only endpoint that returns actual expiry dates) is CURRENT-only — confirmed this phase, returns only forward-looking dates from today, cannot retrospectively confirm what a historical `expiryCode` resolved to on a past date |
| Strike | Yes | Returned per-bar in the response's own `strike` array — confirmed genuinely distinct, consistently-spaced (50-point step for NIFTY) values across `ATM`/`ATM+1`/`ATM-1`/`ATM+2` requests this phase |
| Option type | Yes | Requested explicitly (`CALL`/`PUT`); confirmed this phase that CALL and PUT return the SAME strikes with MATERIALLY DIFFERENT IV (e.g. ~9.2-9.4% call vs. ~11.5-11.8% put at the same strike/date — a real, economically expected put-skew pattern, not a data artifact) |
| Option price (OHLC) | Yes | Real, verified |
| Volume | Yes, with one real defect found this phase | See "Data quality defect" below |
| Open interest | Yes | Real, nonzero, verified |
| Implied volatility | Yes | Real, ready-made (Dhan's own computation, no pricing model needed on our side) |
| Spot | Yes | Real, returned per-bar |
| Futures price | Not from this endpoint | Already separately available and verified in the prior pass (`/charts/historical`, `FUTIDX`) |

## Historical depth, resolution, expiry/strike coverage — re-verified this phase

- **A real, reproducible API bug, re-confirmed**: `expiryCode=0` ("current/near expiry" per the
  documented Annexure) is REJECTED (`HTTP 400, DH-905`) by `/charts/rollingoption` specifically.
  `expiryCode=1` ("next") and `expiryCode=2` ("far") both work (HTTP 200). **This means historical
  term-structure work with this endpoint can only compare "next" vs. "far" expiry — NOT "current/
  near" vs. "next" as a textbook term-structure definition would use.** A real, disclosed limitation
  of the DATA SOURCE, not a limitation this project's own code introduces.
- **Strike coverage for skew**: confirmed real, distinct, correctly-spaced strikes for `ATM`,
  `ATM+1`, `ATM-1`, `ATM+2` (each a separate API call — no single call returns multiple strikes at
  once).
- **Resolution**: 1/5/15/25/60-minute, re-confirmed.
- **Historical depth**: previously confirmed to at least ~4.5 years back (2021-06); not re-tested
  further this phase (no new information beyond the prior pass's own finding).

## Real data-quality defect found this phase: implausible volume near expiry

A full-month (2025-08, hourly, NIFTY ATM CALL) pull found: **zero** zero-volume bars, **zero**
zero-OI bars, **zero** null-IV bars across 133 bars — confirming the ATM-focused endpoint is, by
design, far more liquid than the raw bhavcopy full chain (which had 85.8% zero-volume rows). This is
a genuinely positive Phase 2-relevant finding.

However, inspecting the 2 bars with near-zero IV (both on 2025-08-28, the contract's own final
trading day before expiry) found an **implausible volume field**: 786,238,125 and 330,122,700 —
roughly 1,000x larger than every other bar's own volume in the same series (typical values:
100,000-800,000). This is a genuine data-quality defect in the raw feed near expiry, not a
processing bug in this project's own code (the raw API response itself contains these values) — most
plausibly a units/cumulative-counter artifact specific to final-expiry-day contract behavior. **Any
Phase 3 feature construction must explicitly guard against both symptoms together (near-zero IV AND
implausible volume), which co-occur specifically in the last 1-2 trading sessions before a
contract's own expiry.**

## Answers to the mission's own explicit questions

- **Historical depth**: confirmed to at least ~4.5 years (prior pass), re-confirmed working for
  recent months this phase.
- **Resolution**: intraday, 1-60 minute, confirmed.
- **Missingness**: near-zero within the ATM-focused endpoint (0/133 bars this phase) EXCEPT at the
  final 1-2 sessions before expiry, where both IV and volume become degenerate/implausible — a
  real, narrow, well-understood window requiring explicit exclusion, not a broad missingness
  problem.
- **Zero-volume frequency**: ~0% for ATM-proximate strikes via this endpoint (dramatically better
  than the raw bhavcopy's own 85.8%/75.2%, because Dhan's own rolling-option product design already
  restricts to the liquid, near-the-money region).
- **Timestamp semantics**: real, exchange-local (IST), re-confirmed.
- **Expiry coverage**: relative-selector only (`expiryCode` 1 or 2; 0 is broken), no absolute expiry
  date returned or independently confirmable for a historical date.
- **Strike coverage**: real, correctly-spaced, confirmed for a 4-offset range around ATM.
- **Contract identity**: weaker than the futures side — no absolute expiry date, meaning a
  historical option "contract" from this endpoint is identified only by (underlying, relative
  strike position, relative expiry position, date) — sufficient for the information-content
  questions this phase asks (level/skew/term-structure/asymmetry, all relative-moneyness
  constructs by nature), but NOT sufficient for anything requiring an absolute contract identity
  (e.g., matching against NSE bhavcopy's own absolute-strike rows) — not needed for this phase's own
  scope, disclosed as a boundary.

## Decision

Data is real, historically available, and (for the ATM-proximate region this research needs) far
more liquid than the raw full chain. One real, narrow data-quality defect (near-expiry volume/IV
degeneracy) is disclosed and must be guarded against in Phase 3. Proceeding to Phase 2 (liquidity/
quality gate, formalizing the exclusion rule pre-registered BEFORE any predictive result is seen).
