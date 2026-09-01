"""MCP contract tests (spec §26). Most run as fast direct Python calls
against the decorated tool functions (FastMCP's @mcp.tool() leaves the
underlying function directly callable — confirmed by inspection); one uses
the real stdio transport for genuine protocol-level discovery proof.

No internal component is mocked here — the tools call the real
market/strategy/risk stack. Only network-touching tools (get_market_context,
get_strategy_signal) are exercised with real symbols; a bad symbol is used
specifically to test the error path with a REAL provider response, not a
simulated one.
"""

import asyncio
import sys

import pytest

from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp import ClientSession
from mcp.server.fastmcp.exceptions import ToolError

from market.context import MarketContext
from mcp_server.server import (
    evaluate_risk_tool,
    explain_signal_tool,
    get_market_context_tool,
    get_strategy_signal_tool,
    mcp,
)
from risk.config import RiskConfig
from risk.contracts import RiskDecision
from risk.engine import RiskEngine
from risk.account import Account
from strategy.signal import ReasonCode, Side, Signal

_FORBIDDEN_VERBS = ("execute", "place", "cancel", "buy", "sell", "order", "modify_position", "withdraw", "deposit")


def _real_signal(**overrides) -> Signal:
    base = dict(
        symbol="AAPL",
        generated_at="2021-11-17T00:00:00",
        side=Side.LONG,
        reference_price=153.49000549316406,
        stop_price=149.61357607160295,
        target_price=161.24286433628626,
        risk_reward=2.0,
        strategy_name="trend_momentum_baseline",
        reason_codes=[ReasonCode.TREND_CONFIRMED, ReasonCode.MOMENTUM_CONFIRMED, ReasonCode.VOLUME_CONFIRMED],
    )
    base.update(overrides)
    return Signal(**base)


# --- Security boundary: no tool can ever place/modify/cancel anything -----


def test_no_tool_exposes_an_execution_capability():
    tool_names = [t.name for t in asyncio.run(mcp.list_tools())]
    # 4 from Phase 5 + 6 from Phase 6's paper-trading tools + 1 from Phase 7A
    # (submit_paper_market_bar_tool) + 1 from Phase 12
    # (run_mock_live_simulation_tool, read-only in effect -- runs against an
    # ephemeral in-memory engine, never the persistent paper DB) + 8 from
    # Phase 13 (6 read-only paper-live workstation tools + 2 unmistakably-
    # named approval-action tools). Several of these mutate PERSISTENT state
    # -- paper_trade_signal_tool, submit_paper_market_bar_tool,
    # approve_pending_signal_tool, reject_pending_signal_tool -- but only
    # simulated state, unmistakably named; see test_mcp_paper.py,
    # test_mcp_paper_bar.py, and test_mcp_live_workstation.py's dedicated checks.
    assert len(tool_names) == 20
    for name in tool_names:
        lowered = name.lower()
        for verb in _FORBIDDEN_VERBS:
            assert verb not in lowered, f"{name} looks like an execution tool ({verb})"


def test_no_tool_exposes_arbitrary_code_execution():
    tool_names = {t.name for t in asyncio.run(mcp.list_tools())}
    assert "execute_python" not in tool_names
    assert "run_shell" not in tool_names
    assert "eval" not in tool_names


# --- Discovery, over the REAL stdio transport ------------------------------


def test_real_stdio_discovery_lists_the_phase_5_tools():
    async def _discover():
        params = StdioServerParameters(command=sys.executable, args=["-m", "mcp_server.server"])
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.list_tools()
                return {t.name for t in result.tools}

    names = asyncio.run(_discover())
    # Phase 5's original 4 must still all be present — this test doesn't
    # assert an exact set anymore since Phase 6 added 6 more (covered by
    # test_mcp_paper.py's own discovery test).
    assert {
        "get_market_context_tool",
        "get_strategy_signal_tool",
        "evaluate_risk_tool",
        "explain_signal_tool",
    } <= names


# --- get_market_context_tool ------------------------------------------------


def test_get_market_context_tool_returns_real_market_context():
    result = get_market_context_tool(symbol="AAPL")
    assert isinstance(result, MarketContext)
    assert result.symbol == "AAPL"
    assert result.price > 0


def test_get_market_context_tool_fails_cleanly_on_an_invalid_symbol():
    with pytest.raises(ToolError):
        get_market_context_tool(symbol="THISISNOTAREALTICKERXYZ")


# --- get_strategy_signal_tool -----------------------------------------------


def test_get_strategy_signal_tool_returns_a_signal_or_none():
    result = get_strategy_signal_tool(symbol="AAPL", period="1y", interval="1d")
    assert result is None or isinstance(result, Signal)


def test_get_strategy_signal_tool_rejects_an_unknown_strategy():
    with pytest.raises(ToolError):
        get_strategy_signal_tool(symbol="AAPL", strategy="does_not_exist")


# --- evaluate_risk_tool: MCP output must equal a direct RiskEngine call ----


def test_evaluate_risk_tool_matches_a_direct_risk_engine_call_exactly():
    """Spec §17: "MCP RiskDecision == direct RiskEngine decision" — no
    transformation may change the authoritative values."""
    signal = _real_signal()

    via_mcp = evaluate_risk_tool(
        signal=signal,
        account_equity=100_000.0,
        account_cash=100_000.0,
        account_peak_equity=100_000.0,
        account_daily_start_equity=100_000.0,
    )

    account = Account(initial_capital=100_000.0, cash=100_000.0, peak_equity=100_000.0, daily_start_equity=100_000.0)
    direct = RiskEngine(RiskConfig()).evaluate(signal, account)

    assert isinstance(via_mcp, RiskDecision)
    assert via_mcp.model_dump() == direct.model_dump()


def test_evaluate_risk_tool_honors_custom_risk_config_overrides():
    signal = _real_signal()
    decision = evaluate_risk_tool(
        signal=signal,
        account_equity=100_000.0,
        account_cash=100_000.0,
        account_peak_equity=100_000.0,
        account_daily_start_equity=100_000.0,
        max_exposure_pct=0.001,  # unattainable -> must reject
    )
    assert not decision.approved
    from risk.veto import VetoReason
    assert VetoReason.MAX_EXPOSURE in decision.veto_reasons


def test_evaluate_risk_tool_rejects_invalid_risk_configuration_cleanly():
    signal = _real_signal()
    with pytest.raises(ToolError):
        evaluate_risk_tool(
            signal=signal,
            account_equity=100_000.0,
            account_cash=100_000.0,
            account_peak_equity=100_000.0,
            account_daily_start_equity=100_000.0,
            risk_per_trade_pct=-1.0,  # RiskConfig requires gt=0
        )


# --- Non-mutation: the tool cannot be coaxed into changing entry/stop/etc. -


def test_evaluate_risk_tool_cannot_alter_the_signals_entry_stop_target():
    """Spec §18: feed a signal through the tool and confirm the RiskDecision
    it returns never contains a different entry/stop/target than the input
    Signal — because RiskDecision has no such field to hold a mutated value
    in (it holds position_size.quantity and risk_per_unit, both DERIVED, and
    the original `signal` is never echoed back with different numbers)."""
    signal = _real_signal(reference_price=200.0, stop_price=190.0, target_price=220.0)

    decision = evaluate_risk_tool(
        signal=signal,
        account_equity=1_000_000.0,
        account_cash=1_000_000.0,
        account_peak_equity=1_000_000.0,
        account_daily_start_equity=1_000_000.0,
    )

    # RiskDecision's only price-shaped field is risk_per_unit, which must
    # equal exactly reference_price - stop_price -- not some other number.
    assert decision.position_size.risk_per_unit == signal.reference_price - signal.stop_price
    # There is no field on RiskDecision that could hold an "entry" or
    # "target" at all -- structurally verified, not just by this one value.
    assert not hasattr(decision, "entry")
    assert not hasattr(decision, "target")
    assert not hasattr(decision, "stop")


# --- explain_signal_tool: schema-enforced non-mutation (mocked LLM here — --
# --- the REAL-Ollama version is test_signal_explainer.py + this session's --
# --- manual MCP transcript, both already proven) ---------------------------


def test_explain_signal_tool_returns_only_the_explanation_schema(monkeypatch):
    from agents import analyst
    from schemas.explanation import SignalExplanation
    from tests.conftest import FakeChatModel

    fake = SignalExplanation(supporting_evidence=["x"], contradicting_evidence=["y"], narrative="z")
    monkeypatch.setattr(analyst, "get_analyst_llm", lambda role: FakeChatModel({SignalExplanation: fake}))

    mc = MarketContext(symbol="AAPL", as_of="2026-08-24T00:00:00", price=310.34)
    signal = _real_signal()
    decision = evaluate_risk_tool(
        signal=signal, account_equity=100_000.0, account_cash=100_000.0,
        account_peak_equity=100_000.0, account_daily_start_equity=100_000.0,
    )

    result = explain_signal_tool(market_context=mc, signal=signal, risk_decision=decision)
    assert result is fake
    assert set(type(result).model_fields) == {"supporting_evidence", "contradicting_evidence", "narrative"}
