from schemas.critic import CriticAssessment
from schemas.debate import DebateSummary
from schemas.decision import TradingDecision
from schemas.risk import RiskAssessment
from schemas.technical import TechnicalAnalysis


def test_graph_runs_market_context_through_to_supervisor(
    monkeypatch, fake_chat_model, sample_market_context
):
    """market_context -> technical/risk/critic -> debate -> supervisor,
    with every state key holding its declared typed schema at the end."""

    monkeypatch.setattr(
        "agents.market_context_agent.get_market_context",
        lambda symbol: sample_market_context,
    )
    monkeypatch.setattr("agents.analyst.get_analyst_llm", lambda role: fake_chat_model)

    from graph import graph  # imported after monkeypatching so nodes pick up the fakes at call time

    result = graph.invoke(
        {
            "symbol": "AAPL",
            "question": "Analyze AAPL",
            "context": "some retrieved strategy text",
        }
    )

    assert result["market_context"] is sample_market_context
    assert isinstance(result["technical_response"], TechnicalAnalysis)
    assert isinstance(result["risk_response"], RiskAssessment)
    assert isinstance(result["critic_response"], CriticAssessment)
    assert isinstance(result["debate_response"], DebateSummary)
    assert isinstance(result["final_decision"], TradingDecision)


def test_graph_propagates_market_data_error(monkeypatch, fake_chat_model):
    from market.data_provider import MarketDataError

    def _boom(symbol):
        raise MarketDataError(f"No data for {symbol}")

    monkeypatch.setattr("agents.market_context_agent.get_market_context", _boom)
    monkeypatch.setattr("agents.analyst.get_analyst_llm", lambda role: fake_chat_model)

    from graph import graph

    try:
        graph.invoke({"symbol": "NOTREAL", "question": "Analyze NOTREAL", "context": ""})
        assert False, "expected MarketDataError to propagate"
    except MarketDataError:
        pass


def test_graph_fails_safely_on_missing_symbol(monkeypatch, fake_chat_model):
    monkeypatch.setattr("agents.analyst.get_analyst_llm", lambda role: fake_chat_model)

    from graph import graph

    try:
        graph.invoke({"symbol": "", "question": "Analyze", "context": ""})
        assert False, "expected a ValueError for missing symbol"
    except ValueError as exc:
        assert "symbol" in str(exc).lower()
