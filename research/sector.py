"""Phase 20 -- sector classification.

Reuses yfinance's `Ticker.info` sector/industry fields, confirmed real
against a live call (e.g. AAPL -> sector "Technology", industry
"Consumer Electronics"; see the Phase 20 report). `build_sector_map`
closes a limitation the Phase 19 report stated explicitly: "Sector
strength requires the caller to supply a sector map by hand; no sector
taxonomy is looked up automatically from any source." This is that
lookup -- market_intelligence.scanner.run_scan's sector_map parameter is
unchanged; this only supplies a real value for it.
"""

from collections.abc import Iterable
from datetime import datetime, timezone
from typing import Protocol, runtime_checkable

from research.errors import ResearchDataError
from research.models import SectorInfo


@runtime_checkable
class SectorInfoProvider(Protocol):
    def fetch_sector_info(self, symbol: str) -> SectorInfo: ...


class YahooSectorInfoProvider:
    def fetch_sector_info(self, symbol: str) -> SectorInfo:
        import yfinance as yf

        normalized = symbol.strip().upper()
        if not normalized:
            raise ResearchDataError("Symbol must not be empty.")

        try:
            info = yf.Ticker(normalized).info
        except Exception as exc:
            raise ResearchDataError(f"Failed to fetch sector info for {normalized}.") from exc

        return SectorInfo(
            symbol=normalized,
            sector=info.get("sector") or None,
            industry=info.get("industry") or None,
            as_of=datetime.now(timezone.utc),
        )


def build_sector_map(symbols: Iterable[str], provider: SectorInfoProvider) -> dict[str, str]:
    """symbol -> sector, silently skipping a symbol whose lookup fails or
    has no sector classification -- never a fabricated entry. Directly
    usable as market_intelligence.scanner.run_scan(sector_map=...)."""
    result: dict[str, str] = {}
    for symbol in symbols:
        try:
            info = provider.fetch_sector_info(symbol)
        except ResearchDataError:
            continue
        if info.sector:
            result[info.symbol] = info.sector
    return result
