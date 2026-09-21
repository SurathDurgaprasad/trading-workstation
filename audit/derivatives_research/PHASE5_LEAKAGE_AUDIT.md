# Phase 5 — Data Quality / Information-Leakage Audit

Mandatory audit of `quant_research/derivatives_data.py` (Phase 4's own minimal data layer) against
the mission's own 12-item checklist, before any research experiment is run against it.

## 1. Can an option contract that did not exist at time t appear in the feature set?

**No.** Every `OptionBar`/`FuturesBar`'s own `timestamp` is read directly from the bhavcopy file's
own trade date; a bhavcopy is downloaded per-date (via `fetch_fno_bhavcopy`, Phase A's own module)
and structurally cannot contain a future date's information — NSE publishes one file per trading
day, dated to that day, and never retroactively injects a later day's listings into an earlier
file. Safe by construction of the underlying data source.

## 2. Can future expiry information leak backward?

**No, and this is not a risk in the first place.** An option/future's own expiry date is a fixed,
public fact from the moment the contract is LISTED (not from when it expires) — knowing "this
contract expires 2022-06-30" while parsing the 2022-06-15 bhavcopy is not forward information, it is
a causally-available fact as of 2022-06-15 itself. No code path infers a contract's expiry from a
later file.

## 3. Can future OI be accidentally used?

**Not within Phase 4's own data layer** — each bar's OI is strictly read from its own dated row.
This remains a live discipline requirement for any FUTURE Phase 6/7 research script that joins
multiple dated series (e.g., aligning an option's OI with the underlying's own price on the SAME
date) — flagged as a standing requirement, not a defect found this phase.

## 4. Can end-of-day information enter an intraday feature?

**Not applicable yet, and explicitly disclosed as a scope boundary.** Phase 4 as built is EOD-only
(NSE bhavcopy). Dhan's genuine intraday capability (`/charts/rollingoption`, `/charts/intraday`,
confirmed real and working in Phase 1/2) was NOT implemented in Phase 4's actual code — a deliberate
scope decision (`PHASE3_DATA_FEASIBILITY_GATE.md`'s own conclusion prioritized futures OHLC+OI and
options OI first) to be revisited only if a daily-granularity signal shows promise and intraday
resolution becomes the genuinely limiting factor.

## 5. Can a contract after expiry remain active? — REAL DEFECT FOUND AND FIXED

**Yes, a real gap existed and was fixed this phase.** `select_active_futures_contract`'s original
fallback logic (`pool = eligible if eligible else candidates`) could, if a candidate list ever
contained an ALREADY-EXPIRED contract, fall through to selecting it as "active" — the function only
checked whether a contract was OUTSIDE the roll window, never whether it had already expired
relative to `as_of`. This never manifests with real bhavcopy data in practice (NSE stops listing a
contract in the file the day after its own expiry, so an already-expired contract structurally
cannot appear as a same-day candidate) — but the function must not silently rely on an external data
-source guarantee it does not itself enforce. **Fixed**: candidates are now filtered to
`expiry >= as_of` FIRST, before any roll-window logic runs, in every code path including the
fallback; the function returns `None` if every candidate is already expired, rather than ever
selecting one. Two new regression tests added and passing
(`test_never_selects_an_already_expired_contract`,
`test_excludes_expired_contract_even_when_a_valid_one_exists`).

## 6. Can rolled futures contaminate historical basis?

**Yes — a real, unresolved methodology risk, explicitly disclosed for any future signal work, not
fixed in Phase 4.** `build_continuous_futures_series` correctly selects WHICH contract is "active"
on each date, but does NOT back-adjust prices across a roll. Near-month and far-month futures
typically trade at different absolute prices (cost-of-carry), so a raw price return computed ACROSS
a roll date (yesterday's near-contract close vs. today's far-contract close) would contain an
artificial jump that is not a genuine market return. **Any future signal must either (a) never
compute a raw price return across a roll boundary — only within a single contract's own life, or
using OI/basis-based metrics that are not distorted by this discontinuity — or (b) implement
explicit back-adjustment before use.** This is recorded here as a standing constraint on all future
work built on this series, not solved by Phase 4 itself (which explicitly does not compute a
trading signal).

## 7. Can stale option quotes produce false signals?

**Guarded, not silently possible.** `is_stale_bar(bar, previous_bar)` flags a bar whose own close
exactly repeats the prior bar's close with zero volume (a common "exchange just carries the last
price forward" phenomenon for an untraded contract) — the OI in such a bar remains meaningful; the
PRICE is not a genuine new observation. Any future signal consuming price must check this flag before
treating a repeated close as a real move; three tests confirm the function's own boundary behavior
(first-bar-never-stale, genuine-zero-volume-repeat-is-stale, genuine-price-move-with-zero-volume-is
-not-stale).

## 8. Are option-chain snapshots synchronized with underlying prices?

**Yes, at daily granularity** — NSE bhavcopy is one file per trading day covering all listed
derivatives; every option/future row in a given file shares the same trade date as the equity
pipeline's own same-day bar (both draw from the same NSE trading calendar). No intraday
synchronization question arises yet, per item 4's own scope boundary.

## 9. Are timestamps exchange-local?

**Yes.** Bhavcopy dates are NSE's own trading-calendar dates (IST), the same convention the existing
equity/OHLCV pipeline already uses throughout this project.

## 10. Are bid/ask/last fields distinguishable?

**No — NSE bhavcopy carries no bid/ask at all**, only OHLC and a settlement price. This is a genuine,
disclosed limitation of this specific source (Dhan's real-time `/optionchain` endpoint DOES carry
top bid/ask, per Phase 1/2, but that endpoint is Classification C — current-only, unusable for
historical research). Any future signal relying on bid-ask spread/microstructure information cannot
be built from the bhavcopy route at all.

## 11. Are corporate-action adjustments required?

**Yes, and NOT addressed by Phase 4** — a genuinely open question, not silently ignored. When an
underlying undergoes a split/bonus, NSE typically adjusts outstanding option strikes/lot-sizes to
maintain economic equivalence. A single day's own bhavcopy row already reflects whatever adjustment
was in effect that day, so within one contract's own life this is generally consistent — but
COMPARING or MATCHING option-contract identity across a corporate-action event (e.g., "is this
Strike-500 CE before the split the same economic exposure as Strike-250 CE after a 2:1 split?") is
not solved by anything in `derivatives_data.py`. `quant_research/security_identity_map.py` (built for
the closed OHLCV mean-reversion research) resolves UNDERLYING-EQUITY identity across renames/mergers
and is directly reusable if this becomes relevant, but strike/lot-size-level adjustment tracking is
a separate, unbuilt capability.

## 12. Are illiquid options contaminating the dataset?

**Actively guarded, and precisely quantified.** The parser already excludes any row with all-zero
OHLC (a genuinely untraded strike, not fabricated as "bad data" — Phase 1's own quantified finding:
85.8% of OPTSTK rows, 75.2% of OPTIDX rows in a real sampled bhavcopy have zero volume). Real
-data verification this phase (parsing the actual cached 2022-06-15 bhavcopy): 63,527 raw
OPTSTK+OPTIDX rows → 9,747 bars survive the zero-OHLC filter (15.3%, closely matching the
independently-measured 14.2%/24.8% non-zero-volume fractions from Phase 1). **This filter alone is
NOT sufficient for a real signal** — "traded at all that day" does not mean "liquid enough for a
defensible signal" — any Phase 6/7 work must apply a further, pre-registered liquidity threshold
(e.g., minimum volume/OI, near-ATM/front-month restriction), matching how Dhan's own
`/charts/rollingoption` product design already implicitly restricts to a liquidity-relevant window.

## Summary

One genuine defect was found (item 5) and fixed, tested, and regressed before this document was
finalized — matching the mission's own "if you find a bug, fix it, test it, regress it, commit it,
continue" instruction. Two items (6, 11) are real, disclosed, UNRESOLVED methodology risks that any
future signal-construction phase must explicitly handle, not silently ignore. One item (10) is a
hard source limitation (no bid/ask in this data). The remaining items pass cleanly by construction
or by an already-built, tested guard.
