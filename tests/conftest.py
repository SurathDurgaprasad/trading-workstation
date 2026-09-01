from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest
from pydantic import BaseModel

from market.context import MarketContext
from schemas.critic import CriticAssessment
from schemas.debate import DebateSummary
from schemas.decision import TradingDecision
from schemas.enums import TradingAction
from schemas.risk import RiskAssessment
from schemas.technical import TechnicalAnalysis

AAPL_CACHE_PATH = Path(__file__).resolve().parent.parent / "data" / "market" / "AAPL" / "1d.csv"


def real_aapl_mock_script(symbol: str = "AAPL"):
    """Phase 13: a MockScriptEvent list built from REAL cached AAPL daily
    history, re-tagged for a different symbol name if requested. Used
    wherever a test needs the live pipeline to actually generate a real
    TrendMomentumBaseline signal -- a synthetic flat-price series never
    satisfies SMA20>SMA50 (no trend to detect), so real historical price
    movement is the simplest reliable way to exercise the approval
    workflow's happy path (spec §16G: "real cached market-data tests")."""
    from live.mock_source import MockScriptEvent, make_mock_bar
    from market.data_provider import get_market_data_provider
    from backtesting.cache import CachedMarketDataProvider

    provider = CachedMarketDataProvider(get_market_data_provider())
    ohlcv = provider.fetch_ohlcv("AAPL", interval="1d", period="5y")
    return [
        MockScriptEvent.bar_event(symbol, make_mock_bar(timestamp=b.timestamp, open=b.open, high=b.high, low=b.low, close=b.close, volume=b.volume))
        for b in ohlcv.bars
    ]


class _FakeStructuredRunnable:
    """Stands in for `ChatModel.with_structured_output(schema)`."""

    def __init__(self, instance: BaseModel | None, error: Exception | None = None):
        self._instance = instance
        self._error = error

    def invoke(self, prompt: str) -> BaseModel:
        if self._error is not None:
            raise self._error
        assert self._instance is not None
        return self._instance


class FakeChatModel:
    """Stands in for a role's ChatOllama instance in agents.analyst.get_analyst_llm.

    `responses` maps a schema class to either a pre-built instance of that
    schema (success) or an Exception instance (simulated failure) -- no
    network, no Ollama daemon required.
    """

    def __init__(self, responses: dict[type[BaseModel], BaseModel | Exception]):
        self._responses = responses

    def with_structured_output(self, schema: type[BaseModel]) -> _FakeStructuredRunnable:
        outcome = self._responses[schema]
        if isinstance(outcome, Exception):
            return _FakeStructuredRunnable(None, error=outcome)
        return _FakeStructuredRunnable(outcome)


@pytest.fixture
def sample_market_context() -> MarketContext:
    return MarketContext(
        symbol="AAPL",
        as_of=datetime(2026, 8, 24),
        price=310.34,
        sma_20=313.01,
        sma_50=310.50,
        rsi_14=48.23,
        macd=-1.49,
        macd_signal=-1.25,
        macd_histogram=-0.23,
        atr_14=6.04,
        volume_ratio=0.66,
        volume_trend="decreasing",
    )


@pytest.fixture
def sample_technical_analysis() -> TechnicalAnalysis:
    return TechnicalAnalysis(
        trend="Sideways to slightly down; price below SMA20.",
        support_resistance="Support near 305, resistance near 315.",
        vwap="Trading below session VWAP.",
        entry_quality="Weak — no confirmed breakout.",
        exit_quality="N/A, no open position implied by the question.",
    )


@pytest.fixture
def sample_risk_assessment() -> RiskAssessment:
    return RiskAssessment(
        position_sizing="Cannot be quantified without a stated account size.",
        risk_reward="Approximately 1:2 using ATR14-based stop.",
        stop_loss="ATR14 (6.04) below entry.",
        capital_protection="Reduce size in high ATR regimes.",
    )


@pytest.fixture
def sample_critic_assessment() -> CriticAssessment:
    return CriticAssessment(
        weak_assumptions=["Assumes mean reversion without confirming regime."],
        hidden_risks=["MACD histogram is negative, contradicting SMA20 proximity."],
        failure_scenarios=["Continued volume decline invalidates breakout thesis."],
        missing_rules=["No explicit invalidation level stated."],
    )


@pytest.fixture
def sample_debate_summary() -> DebateSummary:
    return DebateSummary(
        agreements="All three agree momentum is weak.",
        disagreements="Risk sees an acceptable entry; Critic disputes data support.",
        consensus="Wait for confirmation before entry.",
    )


@pytest.fixture
def sample_trading_decision() -> TradingDecision:
    return TradingDecision(
        decision=TradingAction.WAIT,
        confidence=55,
        entry_strategy="Wait for a close back above SMA20 with rising volume.",
        stop_loss="Below recent swing low, ATR14-adjusted.",
        reasoning="Indicators are mixed; no high-conviction setup currently.",
        risks="Volume trend is decreasing, weakening any breakout signal.",
    )


def make_bar(**overrides) -> dict:
    """A qualifying long-setup bar by default (all three
    TrendMomentumBaseline conditions true): sma_20 > sma_50, rsi_14 > 50,
    macd > macd_signal, volume_trend == "increasing". Override individual
    keys to break one condition for a specific test."""
    base = dict(
        open=100.0,
        high=101.0,
        low=99.0,
        close=100.0,
        volume=1_000_000.0,
        sma_20=95.0,
        sma_50=90.0,
        rsi_14=55.0,
        macd=1.0,
        macd_signal=0.5,
        macd_histogram=0.5,
        atr_14=2.0,
        volume_ratio=1.1,
        volume_trend="increasing",
    )
    base.update(overrides)
    return base


def make_indicator_series(bars: list[dict], start: str = "2026-01-01") -> pd.DataFrame:
    index = pd.date_range(start, periods=len(bars), freq="D")
    return pd.DataFrame(bars, index=index)


@pytest.fixture
def fake_chat_model(
    sample_technical_analysis,
    sample_risk_assessment,
    sample_critic_assessment,
    sample_debate_summary,
    sample_trading_decision,
) -> FakeChatModel:
    return FakeChatModel(
        {
            TechnicalAnalysis: sample_technical_analysis,
            RiskAssessment: sample_risk_assessment,
            CriticAssessment: sample_critic_assessment,
            DebateSummary: sample_debate_summary,
            TradingDecision: sample_trading_decision,
        }
    )
