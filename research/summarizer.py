"""Phase 20 -- AI research summaries.

The FIRST roadmap phase needing real LLM involvement outside the
existing `analyze`/AI-explanation paths. Reuses agents.analyst.
invoke_structured exactly as agents/signal_explainer.py already does:
the LLM is handed ALREADY-COLLECTED, already-real evidence (news fetched
by research/news.py, sector fetched by research/sector.py, optionally a
market_intelligence.scanner.CandidateScore's own deterministic
explanation) and asked only to synthesize it -- never to invent a fact,
price, or recommendation. ResearchSummary's field set makes that a type
constraint, not just a prompt instruction (see research/models.py).

Never blocks a caller if Ollama is unavailable -- same posture as
main.py's `_try_ai_explain`: build_research_report always returns real
news/sector evidence even when the AI layer cannot run.
"""

import logging
from datetime import datetime, timezone

from research.errors import ResearchDataError
from research.models import NewsItem, ResearchReport, ResearchSummary, SectorInfo
from research.news import NewsProvider
from research.sector import SectorInfoProvider

logger = logging.getLogger(__name__)


def summarize_research(
    *,
    symbol: str,
    news: list[NewsItem],
    sector: SectorInfo | None,
    candidate_explanation: list[str] | None = None,
) -> ResearchSummary:
    # Deferred: importing agents.analyst pulls in langchain_core -- callers
    # that never reach this function (e.g. `research --no-ai-summary`)
    # must not pay that cost, same discipline main.py already applies to
    # `backtest` vs. `analyze`.
    from agents.analyst import invoke_structured

    if not news and sector is None and not candidate_explanation:
        raise ValueError("summarize_research requires at least some evidence (news, sector, or scanner observations).")

    news_lines = "\n".join(
        f"- [{item.published_at.isoformat()}] ({item.source}) {item.title}: {item.summary}" for item in news
    ) or "(no news items available)"
    sector_line = (
        f"Sector: {sector.sector or 'UNKNOWN'}, Industry: {sector.industry or 'UNKNOWN'}"
        if sector is not None
        else "Sector: not available"
    )
    candidate_lines = "\n".join(candidate_explanation) if candidate_explanation else "(no scanner data available)"

    prompt = f"""
You are a research analyst summarizing ONLY the evidence given below for {symbol}.
Do not introduce any fact, price, event, or opinion that is not present in this evidence.
Do not recommend buying, selling, or holding -- that is not your job and not part of your output.

NEWS EVIDENCE:
{news_lines}

SECTOR CLASSIFICATION:
{sector_line}

SCANNER OBSERVATIONS (deterministic, already computed -- you cannot change these):
{candidate_lines}

Provide:
- summary: a short, plain-language synthesis of what this evidence says, in 3-5 sentences.
- confidence: your confidence (0.0-1.0) that this evidence is substantive and relevant enough to be useful -- NOT confidence in any future price move.
- unknowns: a list of important questions this evidence does not answer.
"""

    return invoke_structured(role="research_summarizer", label="Research Summarizer", prompt=prompt, schema=ResearchSummary)


def build_research_report(
    symbol: str,
    *,
    news_provider: NewsProvider,
    sector_provider: SectorInfoProvider,
    candidate_explanation: list[str] | None = None,
    include_ai_summary: bool = True,
    news_limit: int = 10,
    now: datetime | None = None,
) -> ResearchReport:
    normalized = symbol.strip().upper()
    report_time = now or datetime.now(timezone.utc)

    try:
        news = news_provider.fetch_news(normalized, limit=news_limit)
    except ResearchDataError as exc:
        logger.info("News unavailable for %s, continuing without it: %s", normalized, exc)
        news = []

    try:
        sector = sector_provider.fetch_sector_info(normalized)
    except ResearchDataError as exc:
        logger.info("Sector info unavailable for %s, continuing without it: %s", normalized, exc)
        sector = None

    ai_summary: ResearchSummary | None = None
    ai_summary_unavailable_reason: str | None = None

    if include_ai_summary:
        if not news and sector is None and not candidate_explanation:
            ai_summary_unavailable_reason = "No evidence (news/sector/scanner) was available to summarize."
        else:
            try:
                from llm.provider import check_ollama_availability

                check_ollama_availability()
                ai_summary = summarize_research(
                    symbol=normalized, news=news, sector=sector, candidate_explanation=candidate_explanation
                )
            except Exception as exc:  # noqa: BLE001 -- AI summary must never block a research report
                ai_summary_unavailable_reason = f"AI summary unavailable: {exc}"
                logger.info("AI research summary unavailable for %s, continuing without it: %s", normalized, exc)

    return ResearchReport(
        report_id=ResearchReport.new_id(),
        symbol=normalized,
        as_of=report_time,
        news=news,
        sector=sector,
        ai_summary=ai_summary,
        ai_summary_unavailable_reason=ai_summary_unavailable_reason,
    )
