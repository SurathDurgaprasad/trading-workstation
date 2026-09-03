"""Phase 20 -- news collection.

Reuses yfinance, already a direct dependency of this project (see
market.data_provider.YahooFinanceProvider) -- no new credential, no new
external service, no scraping of a site whose terms this project hasn't
already relied on. `Ticker.news` is Yahoo Finance's own public news feed
for a symbol; field shapes below were confirmed against a real, live
call (see the Phase 20 report's evidence section) before being coded,
not guessed at.
"""

from datetime import datetime
from typing import Protocol, runtime_checkable

from research.errors import ResearchDataError
from research.models import NewsItem


@runtime_checkable
class NewsProvider(Protocol):
    def fetch_news(self, symbol: str, *, limit: int = 10) -> list[NewsItem]:
        """Most-recent-first. Malformed/incomplete entries (missing title
        or publish timestamp) are skipped, never fabricated into a
        placeholder -- a shorter-than-`limit` result is expected, not a bug."""


class YahooNewsProvider:
    def fetch_news(self, symbol: str, *, limit: int = 10) -> list[NewsItem]:
        import yfinance as yf

        normalized = symbol.strip().upper()
        if not normalized:
            raise ResearchDataError("Symbol must not be empty.")

        try:
            raw = yf.Ticker(normalized).news
        except Exception as exc:
            raise ResearchDataError(f"Failed to fetch news for {normalized}.") from exc

        items: list[NewsItem] = []
        for entry in raw or []:
            item = _parse_entry(entry)
            if item is not None:
                items.append(item)
            if len(items) >= limit:
                break
        return items


def _parse_entry(entry: dict) -> NewsItem | None:
    content = entry.get("content") or {}
    title = content.get("title")
    pub_date = content.get("pubDate")
    if not title or not pub_date:
        return None

    published_at = _parse_timestamp(pub_date)
    if published_at is None:
        return None

    provider = ((content.get("provider") or {}).get("displayName")) or "Unknown"
    url = (content.get("canonicalUrl") or {}).get("url")
    summary = content.get("summary") or ""

    return NewsItem(title=title, summary=summary, source=provider, url=url, published_at=published_at)


def _parse_timestamp(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
