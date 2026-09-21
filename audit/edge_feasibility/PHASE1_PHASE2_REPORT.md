# Phase 1 — Repository/Research State Audit

**A. Branch/HEAD**: `final-product-hardening`, HEAD `9131389`.
**B. Working tree**: clean.
**C. Relevant commit history**: `e5954ff` (H_XSECT_006 universe widening, REJECTED — sign reversal,
selection-bias warning), `7a29692` (Phase 9: Bonferroni correction — "no promotable finding
survives it", an important prior-session finding), `eed4576` (Scientific research foundation,
final output: NO DEMONSTRATED EDGE — the original H1 verdict), `a4f3740`/`7b9e2c1` (experiment
registry & promotion gate).
**D. Hypothesis registry**: 56 total, 33 REJECTED, 22 INCONCLUSIVE, 1 SUPPORTED — confirmed by
direct `build_hypothesis_registry()` call, matches the prompt's own stated numbers exactly.
**E. Research docs**: 18 preregistration documents in `docs/research/`, one per major hypothesis
(H_MEANREV_003 through 012, H_XSECT_006, H_BREADTH_001, H_EXIT_005, H_EXTREME_001, H_MOMENTUM_001,
plus one ML-track doc `ML_PHASE1_TRIPLE_BARRIER_BASELINE_PREREGISTRATION.md` not yet reconciled
into the registry — flagged for later, not pursued this session unless directly relevant).
**F. Universe files**: `quant_research/universe_expansion.py` (ORIGINAL_32/EXPANDED_ONLY/COMBINED,
current-F&O-eligibility-based), `market_data/universe.py`, `backtesting/universe.py`.
**G. Historical datasets**: 232 symbols with locally cached OHLCV under `data/market/`.
**H/I. Point-in-time / F&O-eligibility reconstruction**: no mechanism exists anywhere in this
project. `underlying_symbols_with_active_derivative()` (`live/dhan/instruments.py`) reads the
cached Dhan scrip-master CSV, which is a CURRENT snapshot only.
**J. Universe/survivorship tests**: `tests/test_universe_expansion.py` and 3 related files test
the CURRENT construction logic; none test point-in-time/dated membership (none exists to test).

# Phase 2 — Point-in-Time Universe Investigation

## What H_MEANREV_010 actually used
`COMBINED` universe (206/208 buildable symbols) — `ORIGINAL_32_NSE_UNIVERSE` (a hand-curated,
historically-plausible list with no documented selection rationale, per `H_XSECT_006`'s own
disclosure) unioned with `EXPANDED_ONLY` (176 symbols derived from `DhanInstrumentMap.
underlying_symbols_with_active_derivative()` — i.e., whichever underlyings have an active FUTSTK
contract in the CURRENTLY-CACHED scrip-master snapshot, dated 2026-09-09/2026-09-01).

## Direct verification: does the cached scrip-master contain historical/expired contracts?

Checked directly: all 1,270 `FUTSTK` rows in `data/dhan/scrip-master.csv` have expiry dates
**2026-09-24 through 2036-11-27** — every single one is forward-looking; zero expired/historical
contract records exist in this file. Confirms `EXPANDED_ONLY`/`COMBINED` reflect only today's
F&O-eligible set, exactly as `H_XSECT_006`'s own preregistration already disclosed (§7 item 5,
resolved earlier this audit) — this is a re-verification, not a new discovery, but confirms there
is no overlooked historical data already sitting in this project's own cache.

## External source investigation (NSE's own public archives, read-only)

Investigated `nseindia.com`'s own official historical-reports tooling:

1. **"Securities available for Trading"** (`/market-data/securities-available-for-trading`):
   current-day-only CSV, updated daily, no historical/dated versions offered through this UI.
2. **"Historical Contract-wise Price Volume Data"** (`/report-detail/fo_eq_security`): requires
   selecting a symbol FIRST (cannot answer "which symbols were eligible on date X" from a blank
   query — the wrong direction for this question), and its own UI states explicitly: **"Only 90
   days data can be access using the time period filter option."** Confirmed insufficient for a
   10-year research window regardless of the symbol-direction problem.
3. **F&O daily bhavcopy archive** (`/all-reports-derivatives`): **a real, authoritative,
   per-contract-per-day archive exists** (e.g. `BhavCopy_NSE_FO_0_0_0_20260918_F_0000.csv.zip`,
   `FNO_BC18092026.DAT`) — this is the CORRECT, genuine data product for reconstructing point-in-
   time membership (every underlying with an active, traded F&O contract on a given date would
   appear in that date's own bhavcopy). This is a real finding, not fabricated.

## POINT_IN_TIME_UNIVERSE_STATUS = PARTIALLY_AVAILABLE

**Evidence for PARTIALLY_AVAILABLE (not AVAILABLE)**: the authoritative source exists and was
directly verified (not assumed), but full reconstruction requires substantial NEW engineering
this session did not implement:
- Bulk retrieval of potentially thousands of individual daily bhavcopy files across a 10-year
  window (this project's browser tooling can navigate and read pages but has no verified bulk
  file-download-and-parse capability suitable for this scale without introducing a new,
  unverified data-acquisition dependency).
- NSE's bhavcopy file FORMAT has changed over the years (the current "UDiFF Common Bhavcopy"
  format is a relatively recent standardization) — a decade-spanning reconstruction would need to
  handle multiple historical schemas correctly, a real parsing-correctness risk if rushed.
- Rate-limit/terms-of-service considerations for bulk historical downloads from a live exchange
  website were not investigated and should be, before any bulk-retrieval attempt.

**Decision, consistent with the mission's own proportionality principle**: building the full
point-in-time universe is a genuine, real, and now-confirmed-feasible-in-principle project, but it
is a substantial, separately-scoped engineering task, not a same-session addendum. Given
`H_MEANREV_011`/`012`/`013` have ALREADY shown the portfolio-level result is unstable/inconclusive
for reasons independent of survivorship (signal-strength selection ruled out, clustering ruled
out), resolving survivorship would not by itself rescue a currently-non-implementable portfolio
result. **Deferred as an explicitly-scoped future task, not abandoned and not silently skipped.**

**Continuing per the mission's own PARTIALLY_AVAILABLE branch**: proceed with research that does
not depend on false historical membership, carrying forward the already-quantified survivorship
exposure (accepted trades: 14.7% of count / 140.8% of net-return-share from the ORIGINAL-32,
point-in-time-plausible subset; EXPANDED-ONLY is a net drag) as an explicit, disclosed limitation
on any MEANREV-family conclusion, per Phase 2's own instructions for this exact status.
