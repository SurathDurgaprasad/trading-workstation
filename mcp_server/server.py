"""Phase 5 — a THIN, read-only MCP adapter around the existing deterministic
core. Every tool below calls existing project code (market/, strategy/,
risk/, agents/signal_explainer) — nothing here recomputes an indicator, a
signal, or a risk decision. No execute_trade/place_order/cancel_order tool
exists, deliberately (spec §10/§11) — this server cannot place, modify, or
cancel anything.

Phase 6 adds paper-trading tools. Exactly ONE of them mutates state
(`paper_trade_signal_tool`), and its name says so unmistakably — it can
never be confused for a real order. It never trusts a caller-supplied
quantity/risk/approved value (spec Phase 6 §20): it always re-derives the
RiskDecision itself, from PaperTradingEngine.submit_signal(), which always
calls the real RiskEngine — a client cannot pass "approved=true" and skip
that gate.

TradingView integration: NOT AVAILABLE in this environment (see the Phase 5
report — no Playwright/Selenium/CDP library, no TradingView SDK, no
browser automation of any kind is installed). No get_chart_context tool is
exposed; fabricating one would violate spec §4/§12's explicit instruction
not to invent what the interface doesn't actually provide.
"""

import logging
import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from pydantic import BaseModel, ConfigDict

from backtesting.trade import Trade

# NOTE ON IMPORT COST (same class of issue as Phase 4.5's main.py fix):
# agents.signal_explainer's import chain (agents.analyst -> llm.provider ->
# core.config) measured at ~4.3s alone. Unlike main.py's `backtest`
# subcommand, this server MUST register all 4 tools at import time for MCP
# discovery to work — deferring agents.signal_explainer's *registration*
# isn't an option. But explain_signal_tool's actual dependency is only
# needed when that specific tool is CALLED, so the import itself is deferred
# into the function body below — the other 3 tools' startup time is
# unaffected by it. See the Phase 5 report's performance section.
from core.config import PROJECT_ROOT
from core.logging import setup_logging
from market.context import MarketContext, get_market_context
from market.data_provider import MarketDataError, OHLCVBar, get_market_data_provider
from market.indicators import compute_indicator_series
from mcp_server.observability import observed_tool
from paper.engine import Bar, PaperTradingEngine
from paper.errors import OutOfOrderBarError
from paper.models import JournalEntry, Position
from paper.reconciliation import reconcile
from paper.store import PaperStore
from risk.account import Account
from risk.config import RiskConfig
from risk.contracts import RiskDecision
from risk.engine import RiskEngine
from schemas.explanation import SignalExplanation
from strategy.registry import UnknownStrategyError, get_strategy
from strategy.signal import Signal

logger = logging.getLogger(__name__)

mcp = FastMCP(
    name="trading-deterministic-core",
    instructions=(
        "Read-only access to a deterministic trading research pipeline: market "
        "data/indicators, a rule-based strategy, and a fail-closed risk engine. "
        "This server places no orders and holds no broker credentials — "
        "evaluate_risk's approved=False is authoritative and final; nothing in "
        "this server, and no LLM consuming it, can override that."
    ),
)

_SUPPORTED_INTERVALS = {"1d"}  # see get_strategy_signal's docstring for why


@mcp.tool()
@observed_tool("get_market_context")
def get_market_context_tool(symbol: str, period: str = "6mo", interval: str = "1d") -> MarketContext:
    """Fetch the latest market snapshot (price + SMA20/50, RSI14, MACD,
    ATR14, volume ratio/trend) for `symbol`, live from Yahoo Finance.

    Calls market.context.get_market_context() directly — the exact function
    Phase 2's LangGraph pipeline uses. No separate data path.
    """
    try:
        return get_market_context(symbol, period=period, interval=interval)
    except MarketDataError as exc:
        raise ToolError(f"Market data error for '{symbol}': {exc}") from exc


@mcp.tool()
@observed_tool("get_strategy_signal")
def get_strategy_signal_tool(
    symbol: str,
    period: str = "1y",
    interval: str = "1d",
    strategy: str = "trend_momentum_baseline",
) -> Signal | None:
    """Run the real deterministic strategy (strategy.registry) against real
    OHLCV history and return the Signal for the MOST RECENT bar, or null if
    the strategy's conditions don't currently hold. Never an LLM — this is
    the exact same strategy.contracts.Strategy.generate_signal() the
    backtester calls.

    Only interval="1d" is validated end-to-end (Phase 4.5's own finding —
    15m/1h/4h/5m are structurally supported but not battle-tested with a
    long history); other intervals are accepted but flagged, not silently
    coerced (spec §28 — never silently transform 4h -> 1h/1d).
    """
    if interval not in _SUPPORTED_INTERVALS:
        logger.warning(
            "get_strategy_signal called with interval=%r, which is structurally "
            "supported but not battle-tested (see the Phase 4.5 report). Proceeding as requested.",
            interval,
        )

    try:
        strategy_impl = get_strategy(strategy)
    except UnknownStrategyError as exc:
        raise ToolError(str(exc)) from exc

    try:
        ohlcv = get_market_data_provider().fetch_ohlcv(symbol, period=period, interval=interval)
        indicator_series = compute_indicator_series(ohlcv)
    except MarketDataError as exc:
        raise ToolError(f"Market data error for '{symbol}': {exc}") from exc
    except ValueError as exc:  # compute_indicator_series on empty data
        raise ToolError(f"Could not compute indicators for '{symbol}': {exc}") from exc

    last_index = len(indicator_series) - 1
    return strategy_impl.generate_signal(indicator_series, last_index, symbol.strip().upper())


@mcp.tool()
@observed_tool("evaluate_risk")
def evaluate_risk_tool(
    signal: Signal,
    account_equity: float,
    account_cash: float,
    account_peak_equity: float,
    account_daily_start_equity: float,
    account_consecutive_losses: int = 0,
    risk_per_trade_pct: float | None = None,
    max_daily_loss_pct: float | None = None,
    max_drawdown_pct: float | None = None,
    max_exposure_pct: float | None = None,
    max_consecutive_losses: int | None = None,
    consecutive_loss_hard_limit: int | None = None,
    min_risk_reward: float | None = None,
) -> RiskDecision:
    """Evaluate a Signal against a caller-supplied account snapshot using the
    real risk.engine.RiskEngine — the exact engine the backtester uses.
    Every risk formula/threshold lives in risk/, never duplicated here.
    approved=False is final; nothing above this tool can turn it into a trade.

    Account state is passed as plain fields (not a full risk.account.Account
    object) so a caller only needs the numbers a broker/paper-trading system
    would actually have on hand — equity, cash, peak equity, the day's
    starting equity, and the current losing streak.
    """
    account = Account(
        initial_capital=account_equity,
        cash=account_cash,
        peak_equity=account_peak_equity,
        daily_start_equity=account_daily_start_equity,
        consecutive_losses=account_consecutive_losses,
    )

    config_kwargs = {
        key: value
        for key, value in {
            "risk_per_trade_pct": risk_per_trade_pct,
            "max_daily_loss_pct": max_daily_loss_pct,
            "max_drawdown_pct": max_drawdown_pct,
            "max_exposure_pct": max_exposure_pct,
            "max_consecutive_losses": max_consecutive_losses,
            "consecutive_loss_hard_limit": consecutive_loss_hard_limit,
            "min_risk_reward": min_risk_reward,
        }.items()
        if value is not None
    }
    try:
        risk_config = RiskConfig(**config_kwargs)
    except Exception as exc:
        raise ToolError(f"Invalid risk configuration: {exc}") from exc

    return RiskEngine(risk_config).evaluate(signal, account)


@mcp.tool()
@observed_tool("explain_signal")
def explain_signal_tool(
    market_context: MarketContext,
    signal: Signal,
    risk_decision: RiskDecision,
) -> SignalExplanation:
    """Ask the existing local LLM (agents.signal_explainer, Ollama) to
    narrate an already-made Signal/RiskDecision. Structurally cannot mutate
    entry/stop/target/quantity/PnL — SignalExplanation has no such field.
    Requires Ollama to be running; fails with a clear ToolError if not.
    """
    from agents.errors import AgentOutputError
    from agents.signal_explainer import explain_signal as _explain_signal
    from llm.errors import ModelNotAvailableError, OllamaUnavailableError
    from llm.provider import check_ollama_availability

    try:
        check_ollama_availability()
    except (OllamaUnavailableError, ModelNotAvailableError) as exc:
        raise ToolError(str(exc)) from exc

    try:
        return _explain_signal(market_context=market_context, signal=signal, risk_decision=risk_decision)
    except AgentOutputError as exc:
        raise ToolError(str(exc)) from exc


# --------------------------------------------------------------------------
# Phase 6: paper trading. One persistent engine per server process, backed
# by a real SQLite file (not :memory: — a server that forgot every position
# on restart would defeat the entire point of Phase 6's persistence work).
# Lazily created on first use so importing this module (e.g. for schema
# inspection in tests) never has the side effect of creating a DB file.
# --------------------------------------------------------------------------

PAPER_DB_PATH = Path(os.environ["TRADING_PAPER_DB_PATH"]) if "TRADING_PAPER_DB_PATH" in os.environ else PROJECT_ROOT / "data" / "paper_trading.db"
_paper_engine: PaperTradingEngine | None = None


def _get_paper_engine() -> PaperTradingEngine:
    global _paper_engine
    if _paper_engine is None:
        PAPER_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        _paper_engine = PaperTradingEngine(PaperStore(PAPER_DB_PATH))
    return _paper_engine


class PaperStatus(BaseModel):
    model_config = ConfigDict(frozen=True)

    account: Account
    open_positions_count: int
    total_journal_entries: int
    total_trades: int


@mcp.tool()
@observed_tool("paper_trade_signal")
def paper_trade_signal_tool(signal: Signal) -> JournalEntry:
    """PAPER-ONLY. Submits `signal` to the real PaperTradingEngine, which
    re-evaluates it through the real RiskEngine itself — any
    quantity/risk/approved fields the caller might imagine are irrelevant;
    only what RiskEngine actually decides matters. Never places a real
    order, never touches a broker (none exists in this server).

    Idempotent: resubmitting a Signal with the same symbol/bar/strategy/
    side/levels (see Signal.stable_id()) returns the ORIGINAL JournalEntry
    unchanged — it does not create a second paper trade.
    """
    return _get_paper_engine().submit_signal(signal)


@mcp.tool()
@observed_tool("submit_paper_market_bar")
def submit_paper_market_bar_tool(symbol: str, bar: OHLCVBar) -> str:
    """PAPER-ONLY, for controlled/manual testing of the bar-driven paper
    engine over a real MCP connection (Phase 7A). NOT a live market-data
    feed path — the caller supplies the bar explicitly, and this tool never
    fetches or trusts any external data itself. Deliberately NOT named
    submit_market_data, to avoid ever being mistaken for a production/live
    ingestion tool (spec Phase 7A §10).

    Reuses market.data_provider.OHLCVBar (the project's one OHLCV model)
    rather than a second bar schema for this tool's parameter.

    Idempotent: resubmitting the identical bar (same symbol + timestamp as
    the last one processed) is a no-op, returned as "DUPLICATE_SKIPPED". A
    bar strictly older than the last one processed raises a ToolError
    (out-of-order — spec §7); this tool never silently reorders history.
    Fills/exits it triggers still go through the same deterministic
    RiskEngine/execution path as every other paper-trading entry point —
    nothing here can change a stop, a quantity, or the account balance
    directly.
    """
    engine = _get_paper_engine()
    paper_bar = Bar(timestamp=bar.timestamp, open=bar.open, high=bar.high, low=bar.low, close=bar.close, volume=bar.volume)
    try:
        outcome = engine.process_bar(symbol, paper_bar)
    except OutOfOrderBarError as exc:
        raise ToolError(str(exc)) from exc
    return outcome.value


@mcp.tool()
@observed_tool("get_account")
def get_account_tool() -> Account:
    """The current paper-trading account state — read-only."""
    return _get_paper_engine().account


@mcp.tool()
@observed_tool("get_open_positions")
def get_open_positions_tool() -> list[Position]:
    """All currently-open paper positions — read-only."""
    return [p for p in _get_paper_engine().store.list_positions() if p.status.value == "OPEN"]


@mcp.tool()
@observed_tool("get_trade_history")
def get_trade_history_tool() -> list[Trade]:
    """All completed paper trades, in the same Trade shape the backtester
    produces — read-only."""
    return _get_paper_engine().store.list_trades()


@mcp.tool()
@observed_tool("get_journal_entry")
def get_journal_entry_tool(signal_id: str) -> JournalEntry | None:
    """The journal entry for a specific signal (approved, rejected, filled,
    or closed) — read-only. Returns null if that signal was never submitted."""
    return _get_paper_engine().store.find_journal_entry_by_signal_id(signal_id)


@mcp.tool()
@observed_tool("get_paper_status")
def get_paper_status_tool() -> PaperStatus:
    """A one-call summary: account state, open position count, total
    journal entries (signals seen), total completed trades — read-only."""
    engine = _get_paper_engine()
    return PaperStatus(
        account=engine.account,
        open_positions_count=sum(1 for p in engine.store.list_positions() if p.status.value == "OPEN"),
        total_journal_entries=len(engine.store.list_journal_entries()),
        total_trades=len(engine.store.list_trades()),
    )


# --------------------------------------------------------------------------
# Phase 12: a READ-ONLY window onto the simulated live pipeline. Runs a
# BOUNDED mock-live replay against an EPHEMERAL, in-memory (":memory:")
# PaperTradingEngine — never the persistent data/paper_trading.db, never a
# real broker or feed (none exists in this codebase). No place_order/
# execute_trade/live_buy/live_sell tool exists, and none is added here.
# --------------------------------------------------------------------------


class MockLiveSimulationSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    interval: str
    source: str = "MOCK"
    status: str = "SIMULATED"
    bars_processed: int
    signals_generated: int
    trades_completed: int
    final_equity: float
    reconciliation_ok: bool


@mcp.tool()
@observed_tool("run_mock_live_simulation")
def run_mock_live_simulation_tool(symbol: str, interval: str = "1d", period: str = "5d", max_bars: int = 50) -> MockLiveSimulationSummary:
    """PAPER-ONLY, READ-ONLY IN EFFECT. Replays up to `max_bars` of CACHED
    historical data for `symbol` through the same MockMarketDataSource ->
    LiveSimPipeline -> PaperTradingEngine path the `live-sim` CLI command
    uses (live/pipeline.py, live/mock_source.py, unchanged) — but against a
    fresh, in-memory engine that is discarded when the call returns. It
    never touches the persistent paper-trading database, never connects to
    a real feed or broker (neither exists in this codebase), and cannot
    place a real order. Source/status are always MOCK/SIMULATED, never
    LIVE — this tool cannot demonstrate anything else.
    """
    from live.freshness import FreshnessPolicy
    from live.mock_source import MockMarketDataSource
    from live.pipeline import LiveSimPipeline

    try:
        source = MockMarketDataSource.from_cached_history(symbol, interval=interval, period=period)
    except MarketDataError as exc:
        raise ToolError(f"Market data error for '{symbol}': {exc}") from exc

    ephemeral_store = PaperStore(":memory:")
    ephemeral_engine = PaperTradingEngine(ephemeral_store)
    strategy = get_strategy("trend_momentum_baseline")
    pipeline = LiveSimPipeline(
        source=source, engine=ephemeral_engine, strategy=strategy, symbols=[symbol], interval=interval,
        freshness_policy=FreshnessPolicy(multiplier=10_000.0),  # this tool replays a bounded historical window, not a live clock -- see live-sim CLI for a realistic freshness demo
    )

    bars_processed = 0
    signals_generated = 0
    while bars_processed < max_bars:
        result = pipeline.process_next()
        if result.kind == "FEED_EXHAUSTED":
            break
        if result.kind in ("BAR_PROCESSED", "STALE_SIGNAL_SUPPRESSED"):
            bars_processed += 1
            if result.signal is not None:
                signals_generated += 1

    report = reconcile(ephemeral_store)
    return MockLiveSimulationSummary(
        symbol=symbol, interval=interval, bars_processed=bars_processed, signals_generated=signals_generated,
        trades_completed=len(ephemeral_store.list_trades()), final_equity=ephemeral_engine.account.equity,
        reconciliation_ok=report.ok,
    )


# --------------------------------------------------------------------------
# Phase 13: read-only observation of the `paper-live` human-approval
# workstation, plus exactly two unmistakably-named approval-action tools.
# Both read AND act against the SAME persistent files main.py's `paper-live`
# CLI writes (data/live_sim_trading.db, data/live_state.db by default,
# env-overridable — same pattern as PAPER_DB_PATH above) so an operator can
# observe or decide from either the CLI or an MCP-connected client and see
# the same state. Still no execute_trade/place_order/live_buy/live_sell —
# approve_pending_signal_tool/reject_pending_signal_tool can only ADVANCE a
# signal that already reached PENDING_HUMAN_APPROVAL through the real
# Strategy -> RiskEngine pipeline; they call the exact same
# LiveSimPipeline.approve_pending()/reject_pending() the CLI's Y/N prompt
# calls, which structurally cannot accept a quantity/stop/target/price
# override (see tests/test_approval_security.py) and always re-runs the
# real RiskEngine before anything executes.
# --------------------------------------------------------------------------

# live/workstation.py is the single source of truth for accessing this
# state (engine/state-store singletons, restore/idempotency logic, the
# approve/reject calls) — dashboard/app.py imports the exact same functions,
# so neither this MCP layer nor the dashboard re-implements any of it.
import live.workstation as _workstation

LIVE_SIM_DB_PATH = _workstation.LIVE_SIM_DB_PATH
LIVE_STATE_DB_PATH = _workstation.LIVE_STATE_DB_PATH


class LiveSimStatus(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: str = "SIMULATED"
    source: str = "MOCK"
    kill_switch_active: bool
    kill_switch_reason: str | None
    pending_approvals_count: int
    account: Account
    open_positions_count: int
    reconciliation_ok: bool


class PendingApprovalSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    signal_id: str
    symbol: str
    signal: Signal
    strategy_version: str
    risk_config_version: str
    requested_quantity: int
    state: str
    created_at: str
    expires_at: str


@mcp.tool()
@observed_tool("get_live_sim_status")
def get_live_sim_status_tool() -> LiveSimStatus:
    """One-call snapshot of the paper-live workstation: kill switch state,
    pending-approval count, account state, open positions, and
    reconciliation — read-only, reused directly from the same persistent
    PaperTradingEngine/LiveStateStore the `paper-live` CLI writes to.
    Always SIMULATED/MOCK — no real broker or feed exists in this server.
    """
    return LiveSimStatus(**_workstation.get_live_sim_status())


@mcp.tool()
@observed_tool("get_pending_approvals")
def get_pending_approvals_tool() -> list[PendingApprovalSummary]:
    """Every signal CURRENTLY sitting at PENDING_HUMAN_APPROVAL — read-only,
    read directly from the persistent LiveStateStore (live/state_store.py),
    the same durable record approve_pending_signal_tool/
    reject_pending_signal_tool act on."""
    return [
        PendingApprovalSummary(
            signal_id=r.signal_id, symbol=r.symbol, signal=r.signal, strategy_version=r.strategy_version,
            risk_config_version=r.risk_config_version, requested_quantity=r.requested_quantity,
            state=r.state, created_at=r.created_at, expires_at=r.expires_at,
        )
        for r in _workstation.get_pending_approvals()
    ]


@mcp.tool()
@observed_tool("get_positions")
def get_positions_tool() -> list[Position]:
    """Currently-open positions in the paper-live workstation's persistent
    account — read-only. This is a SEPARATE account/database from the
    plain `paper` CLI's (see get_open_positions_tool above)."""
    return _workstation.get_positions()


@mcp.tool()
@observed_tool("get_account_state")
def get_account_state_tool() -> Account:
    """The paper-live workstation's current account state — read-only."""
    return _workstation.get_account_state()


@mcp.tool()
@observed_tool("get_risk_state")
def get_risk_state_tool() -> dict:
    """A read-only readout of the Account/RiskConfig fields RiskEngine's own
    vetoes are computed from (consecutive losses, drawdown, daily P&L, open
    positions) — not a new risk calculation, just surfacing the same
    numbers RiskEngine.evaluate() already reads for the paper-live account."""
    return _workstation.get_risk_state()


@mcp.tool()
@observed_tool("get_trade_journal")
def get_trade_journal_tool() -> list[JournalEntry]:
    """Every journal entry (approved/rejected/filled/closed) ever recorded
    against the paper-live workstation's persistent account — read-only."""
    return _workstation.get_trade_journal()


@mcp.tool()
@observed_tool("approve_pending_signal")
def approve_pending_signal_tool(signal_id: str, reason: str | None = None) -> dict:
    """THE ONLY MCP tool that can turn a PENDING_HUMAN_APPROVAL signal into a
    paper order — and even then only via the exact same
    LiveSimPipeline.approve_pending() the `paper-live` CLI's interactive
    Y/N prompt calls, which re-runs the FULL RiskEngine check again against
    CURRENT account state before anything executes. This tool has NO
    quantity/stop/target/price parameter — approve_pending()'s own
    signature makes overriding those structurally impossible (see
    tests/test_approval_security.py). Deliberately NOT named
    execute_trade/place_order/live_buy — it can only advance a signal that
    already passed the real Strategy -> RiskEngine pipeline; it creates no
    new capability.
    """
    return _workstation.approve_pending_signal(signal_id, reason=reason)


@mcp.tool()
@observed_tool("reject_pending_signal")
def reject_pending_signal_tool(signal_id: str, reason: str | None = None) -> dict:
    """Rejects a PENDING_HUMAN_APPROVAL signal via the same
    LiveSimPipeline.reject_pending() domain method the CLI's REJECT path
    calls. No order is ever created by this tool."""
    return _workstation.reject_pending_signal(signal_id, reason=reason)


def main() -> None:
    setup_logging()
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
