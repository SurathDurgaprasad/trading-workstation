"""EXECUTION SAFETY mission, Part 4 -- corporate-actions intelligence.

Real architecture/source audit finding (verified live, not assumed):
`yfinance` -- already a direct dependency of this project (see research/
news.py, research/sector.py, market.data_provider.YahooFinanceProvider)
-- exposes real dividend history, split history, and a forward-looking
earnings-date estimate for NSE-suffixed symbols through its own `Ticker`
object, with NO new credential, NO new external service, and NO scraping
of a site this project hasn't already relied on. Confirmed live against
RELIANCE.NS before being coded, not guessed at: real dividend amounts
(2024/2025/2026), real split history, and a real next-earnings-date
estimate (2026-10-16) all returned correctly.

This does NOT cover NSE/BSE bulk & block deals, ASM/GSM surveillance
status, or SEBI regulatory circulars -- an honest architecture audit
(same session) found no officially-documented, self-service developer
API for any of those three; NSE/BSE publish some of this on their own
public web pages, but scraping them is a different risk category (no
documented rate limits or terms for programmatic access, no dependency
this project already trusts) that this module deliberately does not
attempt. See docs/LIVE_SYSTEM_HARDENING_FINAL_REPORT.md's market-
intelligence audit for the full source-by-source findings.
"""

from datetime import date, datetime, timezone
from enum import Enum
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict

from research.errors import ResearchDataError


class CorporateActionKind(str, Enum):
    DIVIDEND = "DIVIDEND"
    """A real, already-paid dividend -- historical record, not a forecast."""
    SPLIT = "SPLIT"
    """A real, already-executed stock split/bonus-equivalent ratio change."""
    EARNINGS_ESTIMATE = "EARNINGS_ESTIMATE"
    """A forward-looking estimate of the NEXT earnings date -- explicitly
    an ESTIMATE (yfinance's own field name), never treated as confirmed."""


class CorporateAction(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    kind: CorporateActionKind
    event_date: date
    detail: str
    """Plain-language, e.g. "Dividend: 6.00 per share" / "Split ratio 2:1"
    / "Estimated earnings date (unconfirmed)"."""


class CorporateActionsSnapshot(BaseModel):
    """Roadmap's own structural requirement, applied here: never a
    silently-empty result without saying why. `status` distinguishes
    "genuinely no upcoming/recent actions" (AVAILABLE, actions=[]) from
    "could not determine" (UNAVAILABLE) -- an event-risk gate consuming
    this must be able to tell those apart rather than treating both as
    equally safe to proceed on."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    as_of: datetime
    """UTC-aware: when this snapshot was retrieved."""
    actions: tuple[CorporateAction, ...]
    status: str  # "AVAILABLE" | "UNAVAILABLE" -- never fabricated as NEUTRAL/empty-and-silent
    unavailable_reason: str | None = None


@runtime_checkable
class CorporateActionsProvider(Protocol):
    def fetch_corporate_actions(self, symbol: str, *, dividend_history_limit: int = 3, split_history_limit: int = 3) -> CorporateActionsSnapshot:
        """Recent dividend/split history (most-recent-first, bounded by
        the given limits) plus the next known earnings-date estimate, if
        any. Never raises for "no data" -- that is status=UNAVAILABLE,
        not an exception; only raises ResearchDataError for a genuinely
        empty/invalid symbol, matching research/news.py's own posture."""


class YahooCorporateActionsProvider:
    def fetch_corporate_actions(self, symbol: str, *, dividend_history_limit: int = 3, split_history_limit: int = 3) -> CorporateActionsSnapshot:
        import yfinance as yf

        normalized = symbol.strip().upper()
        if not normalized:
            raise ResearchDataError("Symbol must not be empty.")

        now = datetime.now(timezone.utc)
        try:
            ticker = yf.Ticker(normalized)
            dividends = ticker.dividends
            splits = ticker.splits
            calendar = ticker.calendar
        except Exception as exc:  # noqa: BLE001 -- a real fetch failure is UNAVAILABLE, not a crash
            return CorporateActionsSnapshot(
                symbol=normalized, as_of=now, actions=(), status="UNAVAILABLE",
                unavailable_reason=f"{type(exc).__name__}: {exc}",
            )

        actions: list[CorporateAction] = []
        for event_date, amount in dividends.tail(dividend_history_limit).items():
            actions.append(CorporateAction(
                symbol=normalized, kind=CorporateActionKind.DIVIDEND, event_date=event_date.date(),
                detail=f"Dividend: {float(amount):.2f} per share.",
            ))
        for event_date, ratio in splits.tail(split_history_limit).items():
            actions.append(CorporateAction(
                symbol=normalized, kind=CorporateActionKind.SPLIT, event_date=event_date.date(),
                detail=f"Split ratio {float(ratio):g}:1.",
            ))
        earnings_dates = (calendar or {}).get("Earnings Date") or []
        for earnings_date in earnings_dates:
            actions.append(CorporateAction(
                symbol=normalized, kind=CorporateActionKind.EARNINGS_ESTIMATE, event_date=earnings_date,
                detail="Estimated earnings date (unconfirmed -- yfinance's own forward estimate, not a company-confirmed date).",
            ))

        actions.sort(key=lambda a: a.event_date)
        return CorporateActionsSnapshot(symbol=normalized, as_of=now, actions=tuple(actions), status="AVAILABLE")
