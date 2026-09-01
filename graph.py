from langgraph.graph import END, START, StateGraph

from agents.critic_agent import critic_agent
from agents.debate_agent import debate_agent
from agents.market_context_agent import market_context_agent
from agents.risk_agent import risk_agent
from agents.supervisor_agent import supervisor_agent
from agents.technical_agent import technical_agent
from state import TradingState


def build_graph():
    builder = StateGraph(TradingState)

    builder.add_node("market_context", market_context_agent)
    builder.add_node("technical", technical_agent)
    builder.add_node("risk", risk_agent)
    builder.add_node("critic", critic_agent)
    builder.add_node("debate", debate_agent)
    builder.add_node("supervisor", supervisor_agent)

    builder.add_edge(START, "market_context")

    builder.add_edge("market_context", "technical")
    builder.add_edge("market_context", "risk")
    builder.add_edge("market_context", "critic")

    builder.add_edge("technical", "debate")
    builder.add_edge("risk", "debate")
    builder.add_edge("critic", "debate")

    builder.add_edge("debate", "supervisor")
    builder.add_edge("supervisor", END)

    return builder.compile()


graph = build_graph()
