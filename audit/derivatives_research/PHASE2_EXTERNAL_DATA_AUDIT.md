# Phase 2 — Authoritative External Data Audit

Answers to the mission's own A-J questions. All findings below are from real, live, credentialed
calls made this session (Dhan) or from real archive files already downloaded and inspected in this
and the prior session (NSE) — not from documentation alone, per the mission's own "do not assume"
instruction.

**A. Can historical option-chain data be obtained?** Partially, via two distinct routes with
different strengths. NSE bhavcopy (both formats) gives the full absolute-strike chain, EOD-only, no
ready-made IV. Dhan's `/charts/rollingoption` gives genuine intraday resolution with ready-made
IV/OI/spot, but restricted to a relative-moneyness window (ATM±up to 10 strikes for index options
near expiry, ATM±3 for others, per Dhan's own documented limit) — **not** the full chain at every
historical date. Neither route alone reconstructs "the entire historical option chain at arbitrary
strikes"; each is usable for a narrower, honestly-scoped question.

**B. Can historical futures OI be obtained?** **Yes, confirmed directly** — `/charts/historical`
with `instrument=FUTIDX`, `oi=true` returned real, nonzero open interest (verified this session for
a NIFTY futures contract, values in the 16-18 million range, economically plausible).

**C. Can historical option volume be obtained?** Yes, via both NSE bhavcopy (`CONTRACTS`/
`TtlTradgVol`) and Dhan's `/charts/rollingoption` (`volume`) — both verified to contain real,
nonzero values.

**D. Can historical strike/expiry information be obtained?** Strike: yes, from both routes (NSE
bhavcopy gives the absolute strike directly; Dhan's rolling-option response includes the actual
resolved strike per bar in its own `strike` array, even though the REQUEST only specifies a relative
position). Expiry: yes from NSE bhavcopy (an explicit calendar date per row); **only indirectly**
from Dhan's rolling-option endpoint, which selects a contract via a relative `expiryFlag`/
`expiryCode` and does not return the resolved absolute expiry date in its own response body — a
real, disclosed gap that would need to be independently resolved (e.g., via
`/optionchain/expirylist`, a separate call) if an exact expiry date is required downstream.

**E. Can data be obtained at intraday resolution?** Yes — Dhan's `/charts/rollingoption` and
`/charts/intraday` (with `oi=true`) both provide 1/5/15/25/60-minute bars, verified this session with
real IST-aligned timestamps (e.g., 09:15 IST = NSE market open, confirmed by direct epoch
conversion). NSE bhavcopy is daily/EOD-only — no intraday granularity exists in that archive format
at all.

**F. What is the maximum historical window?** NSE bhavcopy: matches the equity-universe research's
own already-mapped depth (real files verified back to at least 2016-01-04, per the prior session's
Phase A). Dhan `/charts/rollingoption`/`/charts/intraday`: documented as "up to 5 years," empirically
confirmed to at least ~4.5 years back this session (a 2021-06 request returned HTTP 200 with real
data) — the exact 5-year boundary was not pinned further, a minor, low-priority residual unknown.

**G. Are there format changes?** NSE bhavcopy: yes, the already-mapped classic→UDiFF transition
(~2024-06/07, from the prior session's Phase A) applies identically to the option-specific rows in
those same files (not separately re-verified for OPTSTK/OPTIDX rows specifically this session, but
there is no reason to expect the format boundary differs by instrument type within the same file).
Dhan API: a single, current v2 REST contract — no historical format-change concern from the API
consumer's perspective (Dhan's own backend may draw on either NSE format internally, an
implementation detail not exposed to API consumers).

**H. Are there rate limits?** Yes, at multiple layers, all real and already encountered/documented:
NSE archive infrastructure showed genuine rate-limiting/bot-protection behavior after roughly a
dozen rapid requests (directly observed in the prior session's Phase A, root-caused to request
velocity, mitigated there by pacing at 3 seconds/request with zero further incidents). Dhan's own
documented limits: Option Chain API capped at 1 unique request per 3 seconds (explicitly because "OI
data gets updated slow"); general Data APIs capped at 5/second, 100,000/day (from the platform-wide
rate-limit table) — `/charts/rollingoption`'s own specific limit is not separately stated beyond
this general Data API ceiling, a minor disclosed uncertainty, not a blocker (100,000/day is generous
for any realistic per-symbol historical pull).

**I. Can retrieval be automated reliably?** Yes for Dhan — a real, documented, already-credentialed
REST API this project already has working access to (same account already used for live trading
infrastructure, no new subscription or credential needed). Yes for NSE bhavcopy too, subject to the
already-established pacing discipline (paced, sequential requests, never parallel/rapid-fire).

**J. Legal/access restrictions relevant to the project?** Dhan: governed by the same existing
brokerage/API terms this project already operates under for live equity trading and market data —
no new legal exposure identified; the Data API subscription tier is already active (confirmed by
every successful call made this session). NSE: bulk/programmatic archive-retrieval terms of use
remain unread/unverified — an already-disclosed, carried-forward limitation from the prior session's
Phase A, not resolved here, and not blocking for the modest, paced retrieval volumes this research
program is likely to need (a handful to a few dozen historical pulls, not a systematic bulk mirror).

## Small representative sample only — NSE archive not hammered

Per the mission's own "do not hammer external endpoints" instruction, no bulk NSE bhavcopy download
was attempted this phase. The already-downloaded classic-format sample (`classic_2022-06-15.zip`,
from the prior session, still cached locally) was re-inspected for its OPTSTK/OPTIDX rows' own
liquidity profile (see Phase 1's quantified illiquidity finding) — no new NSE archive requests were
made this phase. All new empirical verification this phase used Dhan's own REST API instead
(generous rate limits, already-subscribed, lower operational risk than further NSE archive
requests).
