from datetime import datetime, timezone

import pytest

from research.errors import ResearchDataError
from research.models import NewsItem, ResearchSummary, SectorInfo
from research.summarizer import build_research_report, summarize_research


def _news_item(title="Headline") -> NewsItem:
    return NewsItem(
        title=title, summary="Summary text.", source="Yahoo Finance",
        url="https://example.com/a", published_at=datetime(2026, 9, 2, tzinfo=timezone.utc),
    )


def _sector_info() -> SectorInfo:
    return SectorInfo(symbol="AAPL", sector="Technology", industry="Consumer Electronics", as_of=datetime.now(timezone.utc))


class _FakeNewsProvider:
    def __init__(self, items=None, error=None):
        self._items = items or []
        self._error = error

    def fetch_news(self, symbol, *, limit=10):
        if self._error is not None:
            raise self._error
        return self._items


class _FakeSectorProvider:
    def __init__(self, info=None, error=None):
        self._info = info
        self._error = error

    def fetch_sector_info(self, symbol):
        if self._error is not None:
            raise self._error
        return self._info


# --- summarize_research -----------------------------------------------------


def test_summarize_research_returns_only_the_summary_schema(monkeypatch):
    from agents import analyst
    from research import summarizer
    from tests.conftest import FakeChatModel

    fake_summary = ResearchSummary(summary="A neutral synthesis.", confidence=0.6, unknowns=["Whether this continues next week."])
    monkeypatch.setattr(analyst, "get_analyst_llm", lambda role: FakeChatModel({ResearchSummary: fake_summary}))

    result = summarizer.summarize_research(symbol="AAPL", news=[_news_item()], sector=_sector_info(), candidate_explanation=None)

    assert result is fake_summary
    # Structural proof: no field exists that could hold a price/action/recommendation.
    assert set(ResearchSummary.model_fields) == {"summary", "confidence", "unknowns"}


def test_summarize_research_requires_some_evidence():
    with pytest.raises(ValueError):
        summarize_research(symbol="AAPL", news=[], sector=None, candidate_explanation=None)


def test_summarize_research_works_with_only_scanner_evidence(monkeypatch):
    from agents import analyst
    from research import summarizer
    from tests.conftest import FakeChatModel

    fake_summary = ResearchSummary(summary="Trend-only synthesis.", confidence=0.4, unknowns=[])
    monkeypatch.setattr(analyst, "get_analyst_llm", lambda role: FakeChatModel({ResearchSummary: fake_summary}))

    result = summarizer.summarize_research(symbol="AAPL", news=[], sector=None, candidate_explanation=["Trend: uptrend -> score +1.00"])

    assert result is fake_summary


# --- build_research_report --------------------------------------------------


def test_build_research_report_includes_ai_summary_when_available(monkeypatch):
    from agents import analyst
    from llm import provider as llm_provider
    from tests.conftest import FakeChatModel

    fake_summary = ResearchSummary(summary="ok", confidence=0.5, unknowns=[])
    monkeypatch.setattr(analyst, "get_analyst_llm", lambda role: FakeChatModel({ResearchSummary: fake_summary}))
    monkeypatch.setattr(llm_provider, "check_ollama_availability", lambda **kwargs: None)

    report = build_research_report(
        "AAPL", news_provider=_FakeNewsProvider([_news_item()]), sector_provider=_FakeSectorProvider(_sector_info()),
    )

    assert report.symbol == "AAPL"
    assert len(report.news) == 1
    assert report.sector is not None
    assert report.ai_summary is fake_summary
    assert report.ai_summary_unavailable_reason is None


def test_build_research_report_degrades_gracefully_when_ollama_unavailable(monkeypatch):
    from llm import provider as llm_provider

    def _raise_unavailable(**kwargs):
        raise RuntimeError("Ollama is not reachable at http://localhost:11434")

    monkeypatch.setattr(llm_provider, "check_ollama_availability", _raise_unavailable)

    report = build_research_report(
        "AAPL", news_provider=_FakeNewsProvider([_news_item()]), sector_provider=_FakeSectorProvider(_sector_info()),
    )

    assert report.ai_summary is None
    assert report.ai_summary_unavailable_reason is not None
    assert "not reachable" in report.ai_summary_unavailable_reason
    # Real evidence is still present even though the AI layer failed.
    assert len(report.news) == 1
    assert report.sector is not None


def test_build_research_report_skips_ai_summary_when_no_evidence_at_all(monkeypatch):
    from llm import provider as llm_provider

    called = []
    monkeypatch.setattr(llm_provider, "check_ollama_availability", lambda **kwargs: called.append(True))

    report = build_research_report(
        "AAPL", news_provider=_FakeNewsProvider([]), sector_provider=_FakeSectorProvider(None),
    )

    assert report.ai_summary is None
    assert report.ai_summary_unavailable_reason == "No evidence (news/sector/scanner) was available to summarize."
    assert called == []  # never even attempted the LLM call


def test_build_research_report_respects_include_ai_summary_false(monkeypatch):
    from llm import provider as llm_provider

    called = []
    monkeypatch.setattr(llm_provider, "check_ollama_availability", lambda **kwargs: called.append(True))

    report = build_research_report(
        "AAPL", news_provider=_FakeNewsProvider([_news_item()]), sector_provider=_FakeSectorProvider(_sector_info()),
        include_ai_summary=False,
    )

    assert report.ai_summary is None
    assert report.ai_summary_unavailable_reason is None
    assert called == []


def test_build_research_report_continues_when_news_fetch_fails():
    report = build_research_report(
        "AAPL", news_provider=_FakeNewsProvider(error=ResearchDataError("simulated outage")),
        sector_provider=_FakeSectorProvider(_sector_info()), include_ai_summary=False,
    )

    assert report.news == []
    assert report.sector is not None


def test_build_research_report_continues_when_sector_fetch_fails():
    report = build_research_report(
        "AAPL", news_provider=_FakeNewsProvider([_news_item()]),
        sector_provider=_FakeSectorProvider(error=ResearchDataError("simulated outage")), include_ai_summary=False,
    )

    assert report.sector is None
    assert len(report.news) == 1


def test_build_research_report_normalizes_symbol_and_sets_report_metadata():
    report = build_research_report(
        "aapl", news_provider=_FakeNewsProvider([]), sector_provider=_FakeSectorProvider(None), include_ai_summary=False,
    )

    assert report.symbol == "AAPL"
    assert report.report_id
    assert report.as_of is not None
