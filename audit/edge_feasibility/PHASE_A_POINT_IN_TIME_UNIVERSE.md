# Phase A — Point-in-Time NSE F&O Universe: Investigation, Prototype, and Decision Gate

Executed per the user's own detailed A1-A6 mission structure (2026-09-21, continuing from
`58dd8b8`). Result up front: **Classification B — reconstructable with explicit gaps, and the gaps
are material to H_MEANREV_010/013's own result.** Per the mission's own A5 instruction for this
exact outcome, **the H_MEANREV point-in-time replay (Phase A7-A10) is NOT executed this session** —
documented below, not silently skipped.

## A1 — What "eligible universe" actually means in this research (read directly, not assumed)

Read directly: `docs/research/H_MEANREV_010_EXECUTION_STRUCTURE_PREREGISTRATION.md` §5,
`quant_research/universe_expansion.py`, `live/dhan/instruments.py`'s
`underlying_symbols_with_active_derivative`.

- **Eligibility definition actually used**: single-stock-**futures** availability specifically —
  `instrument_name="FUTSTK"` in Dhan's own instrument master, an exchange-vetted liquidity/
  market-cap gate (NSE only permits single-stock derivatives on SEBI-qualifying names). NOT options
  -only names, NOT a broader "F&O segment" definition, NOT NIFTY-index membership (already declined
  elsewhere in this codebase for lack of a verifiable source).
- **Date granularity actually needed**: the current code applies ONE static membership set (today's
  snapshot) uniformly across the full 10-year backtest window — i.e., today's production code does
  not vary membership by date AT ALL. A genuinely point-in-time-correct version needs membership
  as a function of date, since NSE revises F&O eligibility periodically (SEBI's own rolling
  average-market-wide-position-limit criteria), not once.
- **Historical date range required**: 10 years back from "now" (`period="10y"`, a rolling window —
  already flagged in Phase 3 as not exactly reproducible across run dates).
- **Entry/exit dates vs. daily membership**: daily-resolution membership is the theoretically correct
  granularity (eligibility can change more than once across a 10-year span for a given symbol), but
  see A5/A6 below for why this session settles on a coarser, explicitly-approximate schedule instead.
- **Renamed symbols / delisted securities / corporate actions / temporary suspension / zero-volume
  contracts**: NOT redesigned here (per the user's own explicit "do not redesign H_MEANREV_010"
  instruction) — investigated empirically in A2/A4 below, where a renamed/merged/demerged-symbol
  problem turned out to be the SINGLE most material finding of this phase. "Temporary suspension"
  (NSE's F&O ban list, which blocks NEW derivative positions but not the underlying equity's own
  eligibility status) and "zero-volume contracts" are judged **out of scope**: H_MEANREV_010 trades
  the underlying EQUITY only, using F&O eligibility purely as a static liquidity/quality filter — it
  never touches the derivative contracts themselves, so ban-list status and per-contract volume are
  not applicable to this research design.

## A2 — NSE archive structure (investigated directly, not assumed)

Two real, distinct archive generations were found and DIRECTLY VERIFIED this session via live HTTP
requests (both browser-pane navigation, cross-checked with `read_network_requests` for the real
status code, and a direct scripted download for two representative files):

| Generation | URL pattern | Verified date range | Underlying-eligibility column |
|---|---|---|---|
| **Classic** | `archives.nseindia.com/content/historical/DERIVATIVES/{YYYY}/{MON}/fo{DD}{MON}{YYYY}bhav.csv.zip` | HTTP 200 confirmed: 2016-01-04, 2019-01-15, 2022-06-15, 2024-01-15, 2024-06-28. HTTP 404 confirmed: 2024-07-15, 2026-09-18. | `INSTRUMENT` column == `"FUTSTK"`; underlying in `SYMBOL` |
| **UDiFF** (current) | `nsearchives.nseindia.com/content/fo/BhavCopy_NSE_FO_0_0_0_{YYYYMMDD}_F_0000.csv.zip` | HTTP 200 confirmed: 2026-09-18. HTTP 404 confirmed: 2022-06-15. | `FinInstrmTp` column == `"STF"`; underlying in `TckrSymb` |

**Format transition**: bracketed to a ~2.5-week window (last classic 200 = 2024-06-28; first classic
404 = 2024-07-15) — not pinned to the exact day, and not pursued further (see below).

**Two real files were downloaded** (via a plain scripted HTTPS GET, a browser-User-Agent header, and
an NSE-page Referer — no authentication, no bypass of any access control) and their actual schemas
inspected directly:
- `classic_2022-06-15`: 766,268 bytes zipped, 4,911,885-byte inner CSV. `INSTRUMENT` value counts:
  OPTSTK 56,796 / OPTIDX 6,731 / FUTSTK 589 / FUTIDX 19. **198 distinct FUTSTK underlying symbols** —
  a plausible count, in the same range as today's.
- `udiff_2026-09-18`: 1,139,451 bytes zipped, 6,551,129-byte inner CSV. `FinInstrmTp` value counts:
  STO 29,824 / IDO 5,489 / STF 629 / IDF 18. **210 distinct STF underlying symbols** — likewise
  plausible.

**A real rate-limiting/bot-protection signal was directly encountered** partway through this
investigation: after roughly a dozen rapid successive requests to `archives.nseindia.com` /
`nsearchives.nseindia.com` from the browser pane, subsequent same-session navigation attempts to
`nsearchives.nseindia.com` began failing before any HTTP request was even dispatched (verified via
`read_network_requests` showing zero logged requests for those attempts, versus clean 200/404
responses for the earlier ones), and one intervening request resolved to an obfuscated-looking
redirect path characteristic of a bot-challenge page. **This investigation was stopped at that point
rather than retried aggressively** — consistent with the mission's own "do not download years of
files blindly" instruction and this project's own standing discipline against burdening external
infrastructure. NSE's own terms of use for bulk/programmatic archive retrieval remain unread/
unverified — a genuine, disclosed, unresolved policy caveat, not resolved by this session.

## A3 — Prototype (built and tested)

`quant_research/point_in_time_fno_universe.py` (new module, committed): `fetch_fno_bhavcopy(date,
cache_dir)` → tries the expected format first (classic before the confirmed transition window,
UDiFF after), falls back to the other format once, returns `None` — never a fabricated/guessed
result — if neither exists (a real holiday, a genuinely missing date, or a transient failure).
`parse_futstk_underlyings(bhavcopy)` → dispatches by format, extracts FUTSTK/STF underlyings as
Yahoo-style `.NS` symbols, excludes NSE's own connectivity-test instruments. Every returned
snapshot carries explicit provenance (`source_url`, `format_name`, `local_path`, `sha256`).

`tests/test_point_in_time_fno_universe.py` (new, 14 tests, all passing): URL construction against
the directly-verified real patterns; parsing against small, literal, real-row fixtures (excerpted
from the two downloaded files, mirroring `tests/test_dhan_instruments.py`'s own established
real-row-fixture convention — not the full proprietary archive files, which were not committed to
the repository); classic-first vs. UDiFF-first ordering; fallback-on-404 behavior; cache reuse
(no duplicate HTTP request on a second call); `None` on both-formats-missing (a simulated NSE
holiday); checksum computation. Malformed/empty-zip inputs raise `ValueError` rather than returning
a partial result. No test makes a real network call — a `session` object is injected so the URL
-construction/fallback/caching LOGIC is fully tested without adding load to NSE's own
already-observed-to-be-rate-limit-sensitive infrastructure.

**Known scope simplification, disclosed in the module's own docstring**: `underlying_symbols_
with_active_derivative` (the existing, live Dhan-based method) additionally intersects derivative
underlyings against a same-date EQ-series equity list; this bhavcopy-based module does not
independently re-verify that each FUTSTK/STF underlying is EQ-series, relying instead on NSE's own
product design (single-stock derivatives cannot exist on a non-equity-series name). Judged a
reasonable inference, not a fabrication, but explicitly flagged as not independently cross-checked.

## A4 — Historical completeness

| Period | Required dates (10y window) | Directly verified available | Format |
|---|---|---|---|
| 2016 (window start) | ~250 trading days/yr | 1 sampled date (2016-01-04) confirmed present | Classic |
| 2019 | ~250 | 1 sampled date (2019-01-15) confirmed present | Classic |
| 2022 | ~250 | 1 sampled date (2022-06-15) confirmed present | Classic |
| 2024 H1 | ~125 | 2 sampled dates (2024-01-15, 2024-06-28) confirmed present | Classic |
| 2024 H2 – 2026 | ~625 | 1 sampled date (2026-09-18) confirmed present | UDiFF |

**This is a representative sample, not an exhaustive per-day audit** — per the mission's own explicit
instruction not to download years of files blindly, and given the rate-limiting signal encountered
in A2. Every sampled date across every era of the required 10-year window returned a real, parseable
file with a plausible FUTSTK/STF symbol count. No sampled date returned a genuine gap. **Confidence:
MEDIUM-HIGH that day-level coverage is complete across the window** (based on a representative
sample plus NSE's own status as the primary exchange with strong incentive to keep its own official
archive complete), but this is not a certainty claim — a full trading-calendar cross-check (~2,500
dates) was not performed and would itself require the kind of paced, careful, ToS-aware bulk
retrieval this session deliberately did not undertake without further scoping.

**The materially more important completeness finding is NOT about missing dates — it is about
symbol identity stability**, discovered by diffing the verified 2022-06-15 FUTSTK set (198 symbols)
against today's Dhan-derived set (208 symbols):

- 68 symbols appear in the 2022-06-15 FUTSTK set but not in today's set ("lost eligibility since
  2022" candidates).
- 78 symbols appear in today's set but not in the 2022-06-15 set ("gained eligibility since 2022"
  candidates, e.g. recently-listed names like `DMART`, `BSE`, `CDSL`, `DELHIVERY`).

**Tested directly** (via this project's own `market.data_provider`, the SAME provider all research
in this project uses) whether all 68 "lost" symbols are fetchable under their historical ticker:
**54/68 (79.4%) fetch cleanly. 14/68 (20.6%) return `MarketDataError` — Yahoo Finance itself reports
"possibly delisted; no price data found" for the exact historical ticker.** Critically, this 20.6%
is **not** simply "illiquid names that quietly disappeared" — it includes large, currently very
actively-traded companies undergoing a **corporate action** (ticker rename, merger, or demerger)
that changed their listed identity: `HDFC` (merged into `HDFCBANK` in 2023), `MINDTREE` and `LTI`
(merged into `LTIMINDTREE`), `SRTRANSFIN` (renamed `SHRIRAMFIN`), `MCDOWELL-N` (renamed `UNITDSPR`),
`IDFC` (demerged), `PVR` (merged into `PVRINOX`), and — most strikingly — **`TATAMOTORS` itself**
(its 2024 demerger apparently changed its own listed identity enough that Yahoo Finance no longer
serves history under the plain `TATAMOTORS.NS` ticker this project's pipeline has always used).

## A5 — Decision gate

**Classification: B — RECONSTRUCTABLE WITH EXPLICIT GAPS.**

Per the mission's own A5 branching: *"If B: Determine whether the missing dates materially affect
H_MEANREV_010. If the gaps are immaterial, proceed with explicit exclusions. If they are material,
stop the H_MEANREV replay and document why."*

**Determination: the gaps are material, not immaterial.** Reasoning:

1. Phase 4's own already-established finding is that accepted trades from `ORIGINAL_32_NSE_UNIVERSE`
   (a small, always-blue-chip, corporate-action-quiet set) are only 14.7% of trade count but 140.8%
   of summed net return — i.e., the entire reason a point-in-time correction matters is to determine
   how much of H_MEANREV_010's result depends on `EXPANDED_ONLY` (the current-F&O-eligibility,
   survivorship-exposed set). That is EXACTLY the sub-population where corporate-action/rename noise
   concentrates (78 gained + 68 lost candidates observed between just one pair of snapshots 4 years
   apart) — the correction this phase was meant to enable is compromised in precisely the place it
   matters most.
2. A "silently exclude any symbol this project's data provider can't fetch under its historical
   ticker" implementation — the cheap way out — would NOT be a neutral simplification. It would
   systematically bias the point-in-time-corrected universe toward "corporately quiet" stocks
   (companies that never renamed, merged, or demerged), which is a DIFFERENT, NEW, undisclosed
   selection effect, not a genuine fix for the original survivorship concern. Building it and
   presenting the result as "point-in-time corrected" would overstate what was actually achieved.
3. A real fix (a corporate-action-aware historical-ticker-to-current-ticker resolution layer) is a
   separate, substantial sub-project with its own real risks (misattributing a demerged company's
   pre- and post-split economics as one continuous series would be its own data-integrity error) —
   not a small addendum to this phase, and not something to build speculatively without the user's
   own resourcing decision, per Phase 11's own already-recorded determination that this exact
   dependency requires a human resource-allocation call.

**Therefore, per the mission's own explicit instruction for this exact case: Phase A7 (the
point-in-time H_MEANREV replay) is NOT executed this session.** Phases A8-A10 (independent
replication, economic realism, portfolio realism) are consequently not applicable — they are gated
behind A7 producing a result to validate.

## A6 — What was and was not implemented

**Implemented**: `quant_research/point_in_time_fno_universe.py` (dated bhavcopy retrieval + FUTSTK/
STF parsing, with full provenance and a never-fabricate guarantee), `tests/
test_point_in_time_fno_universe.py` (14 tests, all real-schema-derived, all passing). This is
genuine, reusable, tested infrastructure — valuable regardless of whether the full replay proceeds,
and directly reduces the cost of a future, properly-resourced attempt at the corporate-action
-resolution layer A5 identified as the actual remaining blocker.

**Not implemented**: any corporate-action/ticker-rename resolution layer; any bulk multi-year
retrieval; any change to `H_MEANREV` signal logic (none was touched, per the mission's own explicit
prohibition); any registry-verdict rewrite (none of H_MEANREV_009-013's historical verdicts were
altered).

## FACT / INFERENCE / ASSUMPTION / LIMITATION / DECISION

- **FACT**: two real, distinct NSE bhavcopy archive generations exist, jointly verified (via direct
  HTTP status checks and real downloaded-file schema inspection) to cover representative dates
  across the full required 2016-2026 window.
- **FACT**: 14/68 (20.6%) of a sampled "lost FUTSTK eligibility since 2022" symbol set is unfetchable
  from this project's own data provider under its historical ticker, including large corporate
  -action-affected names such as Tata Motors.
- **INFERENCE**: this 20.6% figure is a reasonable, if not exhaustively proven, estimate of the scale
  of the corporate-action/rename problem across the full 10-year window — a single 2022-vs-2026 diff
  is one data point, not a full time-series characterization.
- **ASSUMPTION**: a single-stock-futures underlying is always an EQ-series equity by NSE's own
  product design (not independently re-verified against a same-date equity bhavcopy this session).
- **LIMITATION**: day-level archive completeness was sampled, not exhaustively verified; the exact
  classic/UDiFF format transition date is bracketed to a ~2.5-week window, not pinned exactly; NSE's
  own terms of use for bulk retrieval remain unread.
- **DECISION**: Classification B, gaps material → Phase A7 (point-in-time H_MEANREV replay) NOT
  executed this session. Proceeding to Phase B (F_CONTEXT regime investigation) per the mission's
  own "if blocked, document the blocker, commit the evidence, continue to the next valid phase"
  instruction.
