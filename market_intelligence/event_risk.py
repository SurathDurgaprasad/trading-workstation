"""EXECUTION SAFETY mission, Part 5 -- a deterministic Event Risk layer.

Target flow per the mission's own diagram: Decision Candidate -> Market
Intelligence -> Event Risk Assessment -> Critic -> Risk -> Paper
Execution. This module is the Event Risk Assessment stage: pure,
deterministic, no LLM, no I/O of its own -- it takes evidence the caller
already fetched (this project's own established posture, matching
critic/engine.py and decision_engine/rules.py) and returns one of
ALLOW / CAUTION / BLOCK / UNKNOWN, never silently treating missing
evidence as safe.

Honest scope, set by what Part 4's own architecture/source audit found
real: only CorporateActionsSnapshot (market_intelligence/
corporate_actions.py) exists as a genuine, verified evidence source
today. NSE/BSE bulk & block deals, ASM/GSM surveillance status, and SEBI
regulatory circulars have no real data source anywhere in this codebase
-- this module does NOT fabricate rules for them. A future check for any
of those categories should raise the same "not evaluated" honesty this
module already uses for corporate actions, not invent a verdict from
nothing.

UNKNOWN is a real, distinct verdict (config-dependent whether it BLOCKS,
CAUTIONs, or is treated as ALLOW by a caller's own policy) -- never
silently folded into ALLOW. See EventRiskConfig's own docstring for why
the default does NOT block on UNKNOWN alone ("do not globally halt
trading merely because every optional intelligence source is
unavailable" -- the mission's own explicit instruction).

Deliberately NOT wired into live/critic_gate.py or paper-live's decision
chain yet in this same session: paper-live already gained one new
blocking layer (the deterministic critic) this session, with its own
dedicated regression cycle. Adding event risk as a SECOND new blocking
layer to the live execution chain in the same pass, on top of a still-
narrow rule set (earnings-date proximity is the only real, reliable,
forward-looking signal Part 4 found), is deferred rather than rushed --
this module is complete, real, and tested, ready to wire in as a
follow-up once it has been reviewed on its own.

KNOWN GAP, found via adversarial self-review of this module -- CLOSED
(adversarial hardening pass, 2026-09-18): `assess_event_risk` previously
never checked how old `corporate_actions.as_of` was relative to now, so
a caller could hand it a `CorporateActionsSnapshot` fetched hours or days
ago and this module would evaluate it as if current. Now mirrors
critic.engine.evaluate()'s own DATA_FRESHNESS check for
`market_context.as_of` almost exactly: an explicit `now` parameter,
compared against `corporate_actions.as_of`, against a configurable
threshold (`EventRiskConfig.max_corporate_actions_staleness_seconds`).
Deliberately reuses `treat_missing_corporate_actions_as` for the STALE
case rather than inventing a new severity knob -- stale evidence is
exactly as untrustworthy as missing evidence for this module's purpose,
and `EventRiskCheckName.CORPORATE_ACTIONS_FRESHNESS` keeps it a
separately-named, independently-visible check so an operator can tell
"we never had this evidence" apart from "we had it, but it's stale."
Still NOT wired into live/critic_gate.py or the live decision chain --
this closes the module's own internal gap (making it safe to integrate
later), not the separate decision of whether/when to actually integrate
it, which remains deliberately unmade.
"""

from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum

from market_intelligence.corporate_actions import CorporateActionKind, CorporateActionsSnapshot


class EventRiskVerdict(str, Enum):
    ALLOW = "ALLOW"
    CAUTION = "CAUTION"
    BLOCK = "BLOCK"
    UNKNOWN = "UNKNOWN"
    """Evidence needed to evaluate this check was unavailable -- never
    silently treated as ALLOW; see EventRiskConfig for how a caller
    decides what UNKNOWN means for ITS OWN purpose."""


class EventRiskCheckName(str, Enum):
    CORPORATE_ACTIONS_AVAILABILITY = "CORPORATE_ACTIONS_AVAILABILITY"
    """Was corporate-actions evidence even obtainable for this symbol?"""
    UPCOMING_EARNINGS = "UPCOMING_EARNINGS"
    """Is a forward earnings-date estimate within the caution window?"""
    CORPORATE_ACTIONS_FRESHNESS = "CORPORATE_ACTIONS_FRESHNESS"
    """How old is the corporate-actions snapshot, if one is available at
    all? A separate question from CORPORATE_ACTIONS_AVAILABILITY --
    available-but-stale and never-available are different failure modes,
    kept independently visible rather than conflated."""


@dataclass(frozen=True)
class EventRiskCheck:
    name: EventRiskCheckName
    verdict: EventRiskVerdict
    detail: str


@dataclass(frozen=True)
class EventRiskAssessment:
    verdict: EventRiskVerdict
    """The single most severe verdict across all checks (BLOCK > CAUTION
    > UNKNOWN > ALLOW), mirroring critic.models.CriticAssessment's own
    "one overall verdict, full check list preserved" shape."""
    checks: tuple[EventRiskCheck, ...]
    symbol: str
    as_of: date


@dataclass(frozen=True)
class EventRiskConfig:
    earnings_caution_days: int = 3
    """A decision within this many days of an estimated earnings date is
    CAUTION, not BLOCK -- earnings introduce genuine uncertainty (the
    reason many real trading desks avoid fresh entries right before
    them) but this is advisory, not a hard rule backed by this
    project's own evidence (no backtest of an earnings-avoidance rule
    has been run -- see the strategy-science discipline this project
    holds itself to elsewhere)."""
    treat_missing_corporate_actions_as: EventRiskVerdict = EventRiskVerdict.UNKNOWN
    """The mission's own explicit instruction: "do not globally halt
    trading merely because every optional intelligence source is
    unavailable." Default UNKNOWN (visible, not silently ALLOW, but also
    not BLOCK) -- a caller wiring this into a hard gate can override to
    EventRiskVerdict.CAUTION or ALLOW explicitly if that is the policy
    they actually want; this module never decides that policy for them."""
    max_corporate_actions_staleness_seconds: float | None = 24 * 3600.0
    """Adversarial hardening pass (2026-09-18) -- closes this module's own
    documented KNOWN GAP. Mirrors critic/engine.py's DATA_FRESHNESS check
    (same age = now - as_of comparison), but 24h default rather than
    critic's much tighter one: corporate actions (splits, earnings-date
    estimates) genuinely change at most daily, so a same-day-refreshed
    snapshot is a reasonable floor -- deliberately much more generous
    than market_context's own threshold (which refreshes far more often,
    minutes not a day). `None` disables the check entirely, matching
    this project's consistent "None disables" convention."""


_VERDICT_SEVERITY = {
    EventRiskVerdict.ALLOW: 0,
    EventRiskVerdict.UNKNOWN: 1,
    EventRiskVerdict.CAUTION: 2,
    EventRiskVerdict.BLOCK: 3,
}


def assess_event_risk(
    *,
    symbol: str,
    as_of: date,
    corporate_actions: CorporateActionsSnapshot | None,
    config: EventRiskConfig | None = None,
    now: datetime | None = None,
) -> EventRiskAssessment:
    """`corporate_actions` is the caller's own already-fetched snapshot
    (this module never fetches anything itself -- same posture as
    critic.engine.evaluate() taking an already-computed benchmark_context
    rather than fetching one). None means "the caller never attempted
    to fetch it" -- treated identically to a fetch that returned
    status=UNAVAILABLE; both mean "no real evidence", never "assume
    fine".

    `now` (adversarial hardening pass, 2026-09-18): optional, defaults to
    None for exact backward compatibility with the one existing call
    pattern this module had before today (no real caller existed at all
    -- see this module's own top-of-file docstring). When supplied (and
    corporate-actions evidence is available, and the staleness threshold
    is enabled), drives the new CORPORATE_ACTIONS_FRESHNESS check against
    `corporate_actions.as_of`. When omitted, that check is simply not
    appended at all -- "the caller didn't ask for a freshness opinion" is
    not the same thing as "evidence is missing," and only the latter
    should ever be able to raise the overall verdict (see the inline
    comment above the check itself for why an UNKNOWN-when-omitted
    design was tried and rejected)."""
    config = config or EventRiskConfig()
    checks: list[EventRiskCheck] = []

    availability_evaluated = corporate_actions is not None
    is_available = availability_evaluated and corporate_actions.status == "AVAILABLE"
    if not availability_evaluated:
        avail_verdict = config.treat_missing_corporate_actions_as
        avail_detail = "No corporate-actions evidence was supplied to this assessment at all."
    elif not is_available:
        avail_verdict = config.treat_missing_corporate_actions_as
        avail_detail = f"Corporate-actions fetch failed: {corporate_actions.unavailable_reason or 'unknown reason'}."
    else:
        avail_verdict = EventRiskVerdict.ALLOW
        avail_detail = "Corporate-actions evidence is available."
    checks.append(EventRiskCheck(name=EventRiskCheckName.CORPORATE_ACTIONS_AVAILABILITY, verdict=avail_verdict, detail=avail_detail))

    # The FRESHNESS check is only ever APPENDED when the caller actually
    # opted into it (is_available, a threshold configured, AND `now`
    # supplied) -- deliberately NOT appended-as-UNKNOWN otherwise. An
    # earlier draft of this fix appended it as UNKNOWN whenever `now` was
    # omitted, which silently downgraded the OVERALL verdict from ALLOW to
    # UNKNOWN for every pre-existing call pattern (UNKNOWN outranks ALLOW
    # in _VERDICT_SEVERITY) -- caught by this module's own pre-existing
    # test suite. `now=None` means "the caller didn't ask for a freshness
    # opinion," not "evidence is missing" -- those are different things,
    # and only the latter should ever raise the overall verdict. Mirrors
    # every other "None disables" check in this project: a disabled check
    # is simply absent, not present-and-UNKNOWN.
    if is_available and config.max_corporate_actions_staleness_seconds is not None and now is not None:
        from paper.engine import _naive  # same tz-normalization critic/engine.py's own DATA_FRESHNESS check uses, for the identical reason

        age_seconds = (_naive(now) - _naive(corporate_actions.as_of)).total_seconds()
        if age_seconds > config.max_corporate_actions_staleness_seconds:
            checks.append(EventRiskCheck(
                name=EventRiskCheckName.CORPORATE_ACTIONS_FRESHNESS, verdict=config.treat_missing_corporate_actions_as,
                detail=(
                    f"Corporate-actions snapshot is {age_seconds:,.0f}s old, exceeding the "
                    f"{config.max_corporate_actions_staleness_seconds:,.0f}s limit -- treated the same as missing evidence."
                ),
            ))
        else:
            checks.append(EventRiskCheck(
                name=EventRiskCheckName.CORPORATE_ACTIONS_FRESHNESS, verdict=EventRiskVerdict.ALLOW,
                detail=f"Corporate-actions snapshot is {age_seconds:,.0f}s old, within the {config.max_corporate_actions_staleness_seconds:,.0f}s limit.",
            ))

    if is_available:
        earnings_dates = [a.event_date for a in corporate_actions.actions if a.kind == CorporateActionKind.EARNINGS_ESTIMATE]
        upcoming = [d for d in earnings_dates if 0 <= (d - as_of).days <= config.earnings_caution_days]
        if upcoming:
            nearest = min(upcoming)
            checks.append(EventRiskCheck(
                name=EventRiskCheckName.UPCOMING_EARNINGS, verdict=EventRiskVerdict.CAUTION,
                detail=f"Estimated earnings date {nearest.isoformat()} is within {config.earnings_caution_days} day(s) of {as_of.isoformat()}.",
            ))
        else:
            checks.append(EventRiskCheck(
                name=EventRiskCheckName.UPCOMING_EARNINGS, verdict=EventRiskVerdict.ALLOW,
                detail="No estimated earnings date falls within the caution window.",
            ))
    else:
        checks.append(EventRiskCheck(
            name=EventRiskCheckName.UPCOMING_EARNINGS, verdict=config.treat_missing_corporate_actions_as,
            detail="Cannot evaluate -- no available corporate-actions evidence.",
        ))

    overall = max((c.verdict for c in checks), key=lambda v: _VERDICT_SEVERITY[v])
    return EventRiskAssessment(verdict=overall, checks=tuple(checks), symbol=symbol.strip().upper(), as_of=as_of)
