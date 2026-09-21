"""Security-identity resolution for point-in-time NSE F&O universe
reconstruction -- Path 1 of the user's own capital-allocation-decision
mission (2026-09-21), continuing Phase A
(audit/edge_feasibility/PHASE_A_POINT_IN_TIME_UNIVERSE.md)'s own material
-gap finding: 14/68 (20.6%) of a sampled "lost F&O eligibility since 2022"
symbol set was unfetchable from this project's data provider under its
historical ticker.

Each of those 14 symbols was investigated individually this session, via
a real web search per event (not from training-data memory alone,
per this project's own "never fabricate" discipline), to determine the
ACTUAL legal structure of whatever corporate action changed its identity
-- specifically, WHICH of two merging entities legally survived (whose
own pre-event price history is a genuine continuation) versus which was
absorbed/extinguished (whose own pre-event price history is NOT safely
continuable under the surviving entity's ticker, since that would splice
two economically distinct companies' returns together).

Result of that investigation (verified this session, sources cited per
entry below):
  - 8/14 are RENAME or MERGER_SURVIVOR events: the historical ticker's
    OWN entity legally continued (just renamed, or absorbed OTHER
    companies into itself), so its OWN pre-event price history is a
    genuine, safe continuation under the current ticker.
  - 3/14 are MERGER_EXTINGUISHED events: the historical ticker's own
    entity was legally absorbed INTO a different, pre-existing company
    (whose own separate history predates the event) -- genuinely NOT
    recoverable; splicing would be a NEW, self-inflicted data-integrity
    error, not a fix.
  - 3/14 remain UNRESOLVED: either a known survivor whose exact current
    ticker was not identified this session (LTI/LTIMindtree), or no
    corporate-action explanation was found for why the historical ticker
    is unfetchable (PEL, GUJGASLTD) -- NOT guessed, left explicit.

This module NEVER fabricates a mapping. `resolve(symbol, as_of)` returns
`None` for any symbol/date this table does not explicitly cover -- the
caller must treat that as "unknown," never as "safe to use `symbol`
as-is" and never as "safe to exclude" without disclosure.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum


class IdentityEventType(str, Enum):
    RENAME = "RENAME"
    """Same legal entity, ticker/name changed only -- no merger."""
    MERGER_SURVIVOR = "MERGER_SURVIVOR"
    """This entity legally survived a merger/amalgamation (absorbed one
    or more other companies into itself, typically also renaming) -- its
    own pre-event price history is a genuine continuation."""
    MERGER_EXTINGUISHED = "MERGER_EXTINGUISHED"
    """This entity was legally absorbed INTO a different, pre-existing
    company. Its own pre-event price history is NOT recoverable under
    the acquirer's ticker -- that ticker's own history predates the
    merger and belongs to a different economic entity."""
    UNRESOLVED = "UNRESOLVED"
    """Investigated this session; no confident classification reached.
    Never guessed -- excluded from any point-in-time universe, disclosed
    as a residual gap, not silently dropped."""


@dataclass(frozen=True)
class IdentityRecord:
    historical_symbol: str  # Yahoo-style ".NS", the ticker as it appeared in a historical bhavcopy
    event_type: IdentityEventType
    event_date: date | None  # None only for UNRESOLVED entries with no confirmed date
    successor_symbol: str | None  # Yahoo-style ".NS"; None for MERGER_EXTINGUISHED/UNRESOLVED
    source: str
    note: str


# Verified this session (2026-09-21) via direct web search per entry -- see each `source`.
# This is NOT an exhaustive enumeration of every identity change across the full 10-year
# window; it resolves exactly the 14-symbol sample Phase A's own 2022-vs-2026 diff surfaced.
IDENTITY_RECORDS: tuple[IdentityRecord, ...] = (
    IdentityRecord(
        historical_symbol="HDFC.NS", event_type=IdentityEventType.MERGER_EXTINGUISHED, event_date=date(2023, 7, 1),
        successor_symbol=None,
        source="CNBC 2023-07-03 'India's HDFC Bank completes $40 billion merger with mortgage lender HDFC'; HDFC Bank's own merger microsite.",
        note="HDFC Ltd (the housing-finance parent) was absorbed into HDFC Bank (the pre-existing, separately-listed subsidiary bank) in a reverse merger; HDFC Ltd shares were extinguished. HDFCBANK.NS is HDFC Bank's OWN pre-existing history, not a continuation of HDFC Ltd's.",
    ),
    IdentityRecord(
        historical_symbol="MINDTREE.NS", event_type=IdentityEventType.MERGER_EXTINGUISHED, event_date=date(2022, 11, 14),
        successor_symbol=None,
        source="Business Standard 2022-11-14 'L&T Infotech, Mindtree merge... comes into effect'; Wikipedia LTIMindtree.",
        note="Mindtree was merged into L&T Infotech (LTI), which survived and was renamed LTIMindtree; Mindtree shares were delisted/extinguished (73 LTI shares per 100 Mindtree shares). Not recoverable under LTI's successor ticker.",
    ),
    IdentityRecord(
        historical_symbol="LTI.NS", event_type=IdentityEventType.UNRESOLVED, event_date=date(2022, 11, 14),
        successor_symbol=None,
        source="Business Standard 2022-11-14; Wikipedia LTIMindtree.",
        note="LTI (L&T Infotech) is a CONFIRMED surviving legal entity (renamed LTIMindtree after absorbing Mindtree) -- the underlying corporate-action type is known, unlike GUJGASLTD/PEL below. Classified UNRESOLVED (not MERGER_SURVIVOR) only because this session did not identify a working current Yahoo ticker for LTIMindtree (LTIM.NS and LTIMINDTREE.NS both failed a direct fetch check) -- a successor MUST NOT be guessed, so this entry has no successor_symbol despite the survivor fact being established.",
    ),
    IdentityRecord(
        historical_symbol="SRTRANSFIN.NS", event_type=IdentityEventType.MERGER_SURVIVOR, event_date=date(2022, 11, 30),
        successor_symbol="SHRIRAMFIN.NS",
        source="MarketScreener 2022-11-30; indianeconomyandmarket.com 2022-12-10.",
        note="Shriram Transport Finance Co Ltd was the continuing legal entity (absorbed Shriram City Union Finance and Shriram Capital into itself, then renamed Shriram Finance Ltd). Verified: SHRIRAMFIN.NS has full 10-year Yahoo depth.",
    ),
    IdentityRecord(
        historical_symbol="MCDOWELL-N.NS", event_type=IdentityEventType.RENAME, event_date=date(2024, 6, 7),
        successor_symbol="UNITDSPR.NS",
        source="MarketScreener; Zerodha Bulletin 'Change in stock name and symbol for United Spirits Limited'.",
        note="Pure ticker/name change (MCDOWELL-N -> UNITDSPR), same legal entity (United Spirits Ltd), no merger. Verified: UNITDSPR.NS has full 10-year Yahoo depth.",
    ),
    IdentityRecord(
        historical_symbol="IDFC.NS", event_type=IdentityEventType.MERGER_EXTINGUISHED, event_date=date(2024, 10, 1),
        successor_symbol=None,
        source="The Legal School 'IDFC IDFC FIRST Bank Merger'; Business Standard 2024-09-27; IDFC FIRST Bank's own merger microsite.",
        note="IDFC Ltd (holding company) was absorbed into IDFC FIRST Bank (the pre-existing, separately-listed bank, itself formed in 2018) -- a reverse merger; IDFC Ltd shares were extinguished (155 IDFC FIRST Bank shares per 100 IDFC Ltd shares). IDFCFIRSTB.NS is the bank's OWN pre-existing history, not a continuation of IDFC Ltd's. (Corrects this session's own earlier, unverified assumption that this pair was safely recoverable.)",
    ),
    IdentityRecord(
        historical_symbol="PVR.NS", event_type=IdentityEventType.MERGER_SURVIVOR, event_date=date(2023, 2, 17),
        successor_symbol="PVRINOX.NS",
        source="BusinessToday 2023-02-07; Wikipedia PVR INOX; NCLT approval 2023-01-12.",
        note="PVR Ltd was the surviving legal entity (absorbed Inox Leisure into itself via all-stock amalgamation, then renamed PVR INOX). Verified: PVRINOX.NS has full 10-year Yahoo depth.",
    ),
    IdentityRecord(
        historical_symbol="TATAMOTORS.NS", event_type=IdentityEventType.RENAME, event_date=date(2025, 10, 1),
        successor_symbol="TMPV.NS",
        source="Autocar Professional 'Tata Motors Demerger Takes Effect'; Business Standard 2025-10-31; Zerodha Console.",
        note="The ORIGINAL, pre-existing 'Tata Motors Ltd' listed entity was renamed 'Tata Motors Passenger Vehicles Ltd' (ticker TMPV), retaining its own full historical listing. The commercial-vehicles business was demerged into a NEW subsidiary (TML Commercial Vehicles Ltd) which was separately listed and later itself renamed 'Tata Motors' -- meaning the CURRENT 'TATAMOTORS.NS' ticker now refers to a DIFFERENT, newly-listed entity than it did before 2025-10-01. Any pre-2025-10-01 observation under 'TATAMOTORS.NS' must resolve to TMPV.NS, never to today's TATAMOTORS.NS. Verified: TMPV.NS has full 10-year Yahoo depth.",
    ),
    IdentityRecord(
        historical_symbol="AMARAJABAT.NS", event_type=IdentityEventType.RENAME, event_date=date(2023, 9, 28),
        successor_symbol="ARE&M.NS",
        source="pv magazine India 2023-09-29; BusinessToday 2023-09-28; Business Standard 2023-09-28.",
        note="Pure rebrand (Amara Raja Batteries -> Amara Raja Energy & Mobility), same legal entity, no merger/demerger disclosed. Verified: ARE&M.NS has full 10-year Yahoo depth.",
    ),
    IdentityRecord(
        historical_symbol="GMRINFRA.NS", event_type=IdentityEventType.RENAME, event_date=date(2022, 9, 15),
        successor_symbol="GMRAIRPORT.NS",
        source="Daily Excelsior 'GMR Infra changes name to GMR Airports Infra'; realtynxt.com.",
        note="GMR Infrastructure Ltd retained its OWN listing/identity (renamed GMR Airports Infrastructure), while the NON-airport business was demerged into a NEW, separately-listed entity (GMR Power and Urban Infra Ltd, GMRP&UI.NS -- verified shorter history, first bar 2022-03-23, consistent with a genuinely new listing, not queried by this map). Verified: GMRAIRPORT.NS has full 10-year Yahoo depth.",
    ),
    IdentityRecord(
        historical_symbol="GUJGASLTD.NS", event_type=IdentityEventType.UNRESOLVED, event_date=None,
        successor_symbol=None,
        source="No corporate-action explanation found this session.",
        note="No rename/merger/demerger identified. GUJGASLTD.NS and a .BO variant both failed a direct fetch check this session; cause not established (could be an unrelated data-provider gap, not necessarily an identity-change problem). Left UNRESOLVED rather than guessed.",
    ),
    IdentityRecord(
        historical_symbol="IBULHSGFIN.NS", event_type=IdentityEventType.RENAME, event_date=date(2023, 9, 25),
        successor_symbol="SAMMAANCAP.NS",
        source="MarketScreener 2023-09-25; Construction Week India; rprealtyplus.com.",
        note="Pure rebrand (Indiabulls Housing Finance -> Sammaan Capital), explicitly confirmed as 'a name change rather than a merger or acquisition,' same legal entity. Verified: SAMMAANCAP.NS has full 10-year Yahoo depth.",
    ),
    IdentityRecord(
        historical_symbol="L&TFH.NS", event_type=IdentityEventType.MERGER_SURVIVOR, event_date=date(2024, 3, 28),
        successor_symbol="LTF.NS",
        source="Free Press Journal; Business Standard 2023-12-04 and 2024-03-29.",
        note="L&T Finance Holdings Ltd (the parent) absorbed its OWN three subsidiaries (L&T Finance Ltd, L&T Infra Credit Ltd, L&T Mutual Fund Trustee Ltd) into itself, then renamed itself L&T Finance Ltd -- the parent entity's own identity continues; this is an internal simplification of the SAME group, not a merger with an external company. Verified: LTF.NS has full 10-year Yahoo depth.",
    ),
    IdentityRecord(
        historical_symbol="PEL.NS", event_type=IdentityEventType.UNRESOLVED, event_date=None,
        successor_symbol=None,
        source="No corporate-action explanation found this session.",
        note="No rename/merger/demerger identified for Piramal Enterprises. PEL.NS and a PIRAMALENT.NS guess both failed a direct fetch check this session; cause not established. Left UNRESOLVED rather than guessed.",
    ),
)

_BY_HISTORICAL_SYMBOL: dict[str, IdentityRecord] = {r.historical_symbol: r for r in IDENTITY_RECORDS}


def resolve(historical_symbol: str) -> IdentityRecord | None:
    """Returns the `IdentityRecord` for `historical_symbol` if this table
    covers it, else `None` -- `None` means "not investigated this
    session," never "confirmed safe to use as-is." Callers MUST treat a
    RENAME/MERGER_SURVIVOR record's `successor_symbol` as the correct
    ticker for fetching that entity's OWN price history (including
    before `event_date`); a MERGER_EXTINGUISHED or UNRESOLVED record (or
    a `None` return) means no safe continuation exists and the symbol
    must be excluded, not substituted."""
    return _BY_HISTORICAL_SYMBOL.get(historical_symbol)


def fetchable_symbol_for(historical_symbol: str) -> str | None:
    """Convenience: the Yahoo symbol to actually fetch OHLCV under for
    `historical_symbol`'s OWN price history, or `None` if none exists.
    For a symbol not in this table at all, returns `historical_symbol`
    unchanged (the caller's own normal fetch will succeed or fail on its
    own merits -- this table only overrides KNOWN identity changes, it
    does not claim to validate every other symbol)."""
    record = resolve(historical_symbol)
    if record is None:
        return historical_symbol
    if record.event_type in (IdentityEventType.RENAME, IdentityEventType.MERGER_SURVIVOR):
        return record.successor_symbol
    return None  # MERGER_EXTINGUISHED or UNRESOLVED -- no safe continuation
