import pytest

from research.errors import ResearchDataError
from research.models import NewsItem
from research.news import YahooNewsProvider


def _entry(
    *, title="Some headline", summary="Some summary", pub_date="2026-09-02T10:00:00Z",
    provider_name="Yahoo Finance", url="https://example.com/a",
):
    content = {"title": title, "summary": summary, "pubDate": pub_date}
    if provider_name is not None:
        content["provider"] = {"displayName": provider_name}
    if url is not None:
        content["canonicalUrl"] = {"url": url}
    return {"id": "abc123", "content": content}


def _install_fake_ticker(monkeypatch, *, news_by_symbol=None, raise_by_symbol=None):
    import yfinance

    news_by_symbol = news_by_symbol or {}
    raise_by_symbol = raise_by_symbol or {}

    class _FakeTicker:
        def __init__(self, symbol):
            if symbol in raise_by_symbol:
                raise raise_by_symbol[symbol]
            self.news = news_by_symbol.get(symbol, [])

    monkeypatch.setattr(yfinance, "Ticker", _FakeTicker)


def test_fetch_news_parses_a_real_shaped_entry(monkeypatch):
    _install_fake_ticker(monkeypatch, news_by_symbol={"AAPL": [_entry()]})

    items = YahooNewsProvider().fetch_news("AAPL")

    assert len(items) == 1
    item = items[0]
    assert isinstance(item, NewsItem)
    assert item.title == "Some headline"
    assert item.summary == "Some summary"
    assert item.source == "Yahoo Finance"
    assert item.url == "https://example.com/a"
    assert item.published_at.isoformat() == "2026-09-02T10:00:00+00:00"


def test_fetch_news_skips_entries_missing_a_title(monkeypatch):
    _install_fake_ticker(monkeypatch, news_by_symbol={"AAPL": [_entry(title=None), _entry()]})

    items = YahooNewsProvider().fetch_news("AAPL")

    assert len(items) == 1


def test_fetch_news_skips_entries_missing_a_publish_date(monkeypatch):
    _install_fake_ticker(monkeypatch, news_by_symbol={"AAPL": [_entry(pub_date=None), _entry()]})

    items = YahooNewsProvider().fetch_news("AAPL")

    assert len(items) == 1


def test_fetch_news_skips_entries_with_an_unparseable_timestamp(monkeypatch):
    _install_fake_ticker(monkeypatch, news_by_symbol={"AAPL": [_entry(pub_date="not-a-date"), _entry()]})

    items = YahooNewsProvider().fetch_news("AAPL")

    assert len(items) == 1


def test_fetch_news_defaults_a_missing_provider_name_to_unknown(monkeypatch):
    _install_fake_ticker(monkeypatch, news_by_symbol={"AAPL": [_entry(provider_name=None)]})

    items = YahooNewsProvider().fetch_news("AAPL")

    assert items[0].source == "Unknown"


def test_fetch_news_tolerates_a_missing_url(monkeypatch):
    _install_fake_ticker(monkeypatch, news_by_symbol={"AAPL": [_entry(url=None)]})

    items = YahooNewsProvider().fetch_news("AAPL")

    assert items[0].url is None


def test_fetch_news_respects_the_limit(monkeypatch):
    _install_fake_ticker(monkeypatch, news_by_symbol={"AAPL": [_entry() for _ in range(5)]})

    items = YahooNewsProvider().fetch_news("AAPL", limit=2)

    assert len(items) == 2


def test_fetch_news_raises_research_data_error_on_ticker_failure(monkeypatch):
    _install_fake_ticker(monkeypatch, raise_by_symbol={"AAPL": RuntimeError("simulated outage")})

    with pytest.raises(ResearchDataError):
        YahooNewsProvider().fetch_news("AAPL")


def test_fetch_news_rejects_an_empty_symbol():
    with pytest.raises(ResearchDataError):
        YahooNewsProvider().fetch_news("   ")


def test_fetch_news_returns_empty_list_when_no_news_available(monkeypatch):
    _install_fake_ticker(monkeypatch, news_by_symbol={"AAPL": []})

    items = YahooNewsProvider().fetch_news("AAPL")

    assert items == []
