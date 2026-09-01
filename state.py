from typing import TypedDict

from market.context import MarketContext
from schemas.critic import CriticAssessment
from schemas.debate import DebateSummary
from schemas.decision import TradingDecision
from schemas.risk import RiskAssessment
from schemas.technical import TechnicalAnalysis


class TradingState(TypedDict, total=False):

    symbol: str
    question: str

    context: str
    market_context: MarketContext

    technical_response: TechnicalAnalysis
    risk_response: RiskAssessment
    critic_response: CriticAssessment

    debate_response: DebateSummary

    final_decision: TradingDecision
