import argparse
import logging
import sys
import time
from datetime import datetime

from pydantic import BaseModel

# NOTE ON IMPORT COST (Phase 4.5 performance investigation): `graph` (and
# transitively `agents.*`, `rag.retriever`) pull in langgraph, langchain_ollama,
# and langchain_chroma — measured at ~15-20s of import time alone on this
# machine, dwarfing an actual backtest run (~1s per period). The `backtest`
# subcommand is required to work with Ollama/LangGraph completely absent
# (spec §18) and never needs any of that, so those imports are deferred into
# run() below instead of sitting at module top-level — `python main.py
# backtest ...` no longer pays for them at all. `agents.errors`/`llm.errors`/
# `rag.errors` stay at top level: they're plain exception classes, not the
# heavy libraries, and `main()`'s except clause needs them regardless of command.
from agents.errors import AgentOutputError
from backtesting.report import format_backtest_report
from backtesting.runner import FullBacktestRun, run_full_backtest
from core.config import PROJECT_ROOT
from core.logging import setup_logging
from live.dhan.config import DhanCredentialsMissingError
from live.dhan.instruments import InstrumentNotFoundError
from live.dhan.rest_client import DhanRestError
from llm.errors import ModelNotAvailableError, OllamaUnavailableError
from market.data_provider import MarketDataError
from predictions.errors import PredictionUnavailableError
from rag.errors import RagStoreNotFoundError
from risk.config import RiskConfig
from risk.sizing import SizingUnavailableError
from state import TradingState
from strategy.registry import UnknownStrategyError, get_strategy

logger = logging.getLogger(__name__)

DEFAULT_QUESTION = """
Analyze this trading strategy.
Find flaws.
Estimate risk.
Suggest improvements.
"""

DEFAULT_PAPER_DB_PATH = PROJECT_ROOT / "data" / "paper_trading.db"

_KNOWN_COMMANDS = ("analyze", "backtest", "paper", "live-sim", "paper-live", "dashboard", "scan", "research", "decide", "size", "predict", "evaluate", "learn", "review", "shadow-run", "schedule", "universe", "regime", "experiment")

# Known, controlled failure modes. Anything else is an unexpected bug and is
# allowed to raise with its real traceback rather than being masked here.
_CONTROLLED_ERRORS = (
    OllamaUnavailableError,
    ModelNotAvailableError,
    RagStoreNotFoundError,
    MarketDataError,
    AgentOutputError,
    UnknownStrategyError,
    ValueError,
    DhanCredentialsMissingError,
    DhanRestError,
    InstrumentNotFoundError,
    SizingUnavailableError,
    PredictionUnavailableError,
)


# --------------------------------------------------------------------------
# `analyze` — the Phase 1/2 AI multi-agent pipeline (unchanged behavior).
# --------------------------------------------------------------------------


def run(symbol: str, question: str | None = None) -> TradingState:
    # Deferred: see the import-cost note at the top of this file.
    from graph import graph
    from llm.provider import check_ollama_availability
    from rag.retriever import get_context

    resolved_question = question if question is not None else DEFAULT_QUESTION

    logger.info("Checking Ollama availability")
    check_ollama_availability()

    logger.info("Retrieving document context")
    context = get_context(resolved_question)

    logger.info("Invoking trading analysis graph for %s", symbol)
    result = graph.invoke(
        {
            "symbol": symbol,
            "question": resolved_question,
            "context": context,
        }
    )

    return result


def _format_model(model: BaseModel) -> str:
    lines = []
    for field_name, value in model.model_dump(mode="json").items():
        label = field_name.replace("_", " ").title()
        if isinstance(value, list):
            value = "\n  - " + "\n  - ".join(str(item) for item in value) if value else "(none)"
        lines.append(f"{label}: {value}")
    return "\n".join(lines)


def print_analysis_report(result: TradingState) -> None:
    market_context = result.get("market_context")

    print("=" * 50)
    print("AI TRADING ANALYSIS")
    print("=" * 50)

    print(f"\nSymbol: {result.get('symbol')}")
    if market_context is not None:
        print(f"Timestamp: {market_context.as_of.isoformat()}")

        print("\nMARKET DATA")
        for line in market_context.to_prompt_lines()[2:]:  # skip Symbol/As-of, already shown
            print(line)

    print("\nTECHNICAL ANALYSIS")
    print(_format_model(result["technical_response"]))

    print("\nRISK ANALYSIS")
    print(_format_model(result["risk_response"]))

    print("\nCRITIC")
    print(_format_model(result["critic_response"]))

    print("\nDEBATE")
    print(_format_model(result["debate_response"]))

    decision = result["final_decision"]
    print("\nFINAL AI ASSESSMENT")
    print("(AI market analysis only — not a validated trading signal)")
    print(_format_model(decision))


def run_analyze_command(args: argparse.Namespace) -> None:
    result = run(symbol=args.symbol, question=args.question)
    print_analysis_report(result)


# --------------------------------------------------------------------------
# `backtest` — Phase 3 deterministic strategy engine. No LLM, no network
# beyond the (cached) historical data fetch.
# --------------------------------------------------------------------------


def run_backtest_command(args: argparse.Namespace) -> None:
    strategy = get_strategy(args.strategy)

    logger.info(
        "Running backtest for %s (%s, period=%s, interval=%s)",
        args.symbol,
        strategy.name,
        args.period,
        args.interval,
    )

    risk_config = RiskConfig(
        risk_per_trade_pct=args.risk_per_trade,
        max_daily_loss_pct=args.max_daily_loss,
        max_drawdown_pct=args.max_drawdown,
        max_exposure_pct=args.max_exposure,
        max_consecutive_losses=args.max_consecutive_losses,
        consecutive_loss_risk_multiplier=args.consecutive_loss_risk_multiplier,
        consecutive_loss_hard_limit=args.consecutive_loss_hard_limit,
        min_risk_reward=args.min_risk_reward,
    )

    run_result: FullBacktestRun = run_full_backtest(
        symbol=args.symbol,
        strategy=strategy,
        period=args.period,
        interval=args.interval,
        initial_capital=args.initial_capital,
        risk_config=risk_config,
    )

    print(
        format_backtest_report(
            run_result.full,
            development=run_result.development,
            validation=run_result.validation,
            out_of_sample=run_result.out_of_sample,
        )
    )


# --------------------------------------------------------------------------
# `paper` — Phase 6 deterministic paper trading + journal. No LLM, no
# broker, no live orders — same import-deferral discipline as `backtest`.
# --------------------------------------------------------------------------


def run_paper_command(args: argparse.Namespace) -> None:
    from backtesting.cache import CachedMarketDataProvider
    from market.data_provider import get_market_data_provider
    from market.indicators import compute_indicator_series
    from paper.engine import PaperTradingEngine
    from paper.reconciliation import reconcile
    from paper.replay import replay_historical
    from paper.store import PaperStore

    db_path = args.db or DEFAULT_PAPER_DB_PATH
    store = PaperStore(db_path)
    engine = PaperTradingEngine(store, initial_capital=args.initial_capital)

    if args.paper_command == "status":
        account = engine.account
        open_positions = [p for p in store.list_positions() if p.status.value == "OPEN"]
        journal = store.list_journal_entries()
        trades = store.list_trades()
        print("=" * 50)
        print("PAPER TRADING STATUS")
        print("=" * 50)
        print(f"\nDatabase: {db_path}")
        print(f"\nInitial Capital:     {account.initial_capital:,.2f}")
        print(f"Equity:              {account.equity:,.2f}")
        print(f"Cash:                {account.cash:,.2f}")
        print(f"Realized PnL:        {account.realized_pnl:,.2f}")
        print(f"Peak Equity:         {account.peak_equity:,.2f}")
        print(f"Current Drawdown:    {account.current_drawdown_pct:.2f}%")
        print(f"Consecutive Losses:  {account.consecutive_losses}")
        print(f"\nOpen Positions:      {len(open_positions)}")
        print(f"Total Trades:        {len(trades)}")
        print(f"Total Signals Seen:  {len(journal)}")

        report = reconcile(store)
        print(f"\nReconciliation:      {'OK' if report.ok else 'FAILED'}")
        for issue in report.issues:
            print(f"  - {issue.check}: {issue.detail}")

    elif args.paper_command == "run":
        strategy = get_strategy(args.strategy)
        provider = CachedMarketDataProvider(get_market_data_provider())
        ohlcv = provider.fetch_ohlcv(args.symbol, period=args.period, interval=args.interval)
        indicator_series = compute_indicator_series(ohlcv)

        logger.info("Running paper trading replay for %s over %d bars", args.symbol, len(indicator_series))
        summary = replay_historical(engine, symbol=args.symbol, indicator_series=indicator_series, strategy=strategy)

        print(f"Processed {summary.bars_processed} bars for {summary.symbol}.")
        print(f"Submitted {summary.signals_submitted} signals.")
        print(f"Account equity: {engine.account.equity:,.2f}")

        report = reconcile(store)
        if not report.ok:
            print("\nRECONCILIATION FAILED:", file=sys.stderr)
            for issue in report.issues:
                print(f"  - {issue.check}: {issue.detail}", file=sys.stderr)
            sys.exit(1)

    elif args.paper_command == "trades":
        trades = store.list_trades()
        if not trades:
            print("No completed paper trades yet.")
        for trade in trades:
            print(
                f"{trade.symbol:10s} {trade.entry_time} -> {trade.exit_time}  "
                f"entry={trade.entry_price:.2f} exit={trade.exit_price:.2f} qty={trade.quantity}  "
                f"net_pnl={trade.net_pnl:,.2f}  R={trade.r_multiple:.2f}  ({trade.exit_reason.value})"
            )

    elif args.paper_command == "journal":
        entries = store.list_journal_entries()
        if not entries:
            print("No journal entries yet.")
        for entry in entries:
            print(
                f"{entry.created_at}  {entry.symbol:10s} {entry.outcome.value:24s} "
                f"signal={entry.signal_id[:12]}  strategy={entry.strategy_name}@{entry.strategy_version}"
            )

    store.close()


# --------------------------------------------------------------------------
# `live-sim` — Phase 12 mock-live pipeline. NOT connected to any real broker
# or live feed; replays cached history bar-by-bar through the same
# import-deferral discipline as `backtest`/`paper`.
# --------------------------------------------------------------------------

DEFAULT_LIVE_SIM_DB_PATH = PROJECT_ROOT / "data" / "live_sim_trading.db"


def run_live_sim_command(args: argparse.Namespace) -> None:
    from live.freshness import FreshnessPolicy
    from live.mock_source import MockMarketDataSource
    from live.pipeline import LiveSimPipeline
    from paper.engine import PaperTradingEngine
    from paper.reconciliation import reconcile
    from paper.store import PaperStore

    db_path = args.db or DEFAULT_LIVE_SIM_DB_PATH
    store = PaperStore(db_path)
    engine = PaperTradingEngine(store, initial_capital=args.initial_capital)
    strategy = get_strategy(args.strategy)

    source = MockMarketDataSource.from_cached_history(args.symbol, interval=args.interval, period=args.period)
    freshness_policy = FreshnessPolicy(multiplier=args.freshness_multiplier)
    pipeline = LiveSimPipeline(
        source=source, engine=engine, strategy=strategy, symbols=[args.symbol], interval=args.interval,
        freshness_policy=freshness_policy, require_human_approval=args.require_human_approval,
    )

    print("=" * 60)
    print("SIMULATED INTRADAY PIPELINE -- NOT LIVE TRADING")
    print("=" * 60)
    print(f"SOURCE:   MOCK (replaying cached history)")
    print(f"STATUS:   SIMULATED")
    print(f"SYMBOL:   {args.symbol}")
    print(f"INTERVAL: {args.interval}")
    print(f"DATABASE: {db_path}")
    print(f"HUMAN APPROVAL REQUIRED: {args.require_human_approval}")
    print("This process places NO real orders and holds NO broker connection.")
    print("=" * 60)

    processed = 0
    while args.max_bars is None or processed < args.max_bars:
        result = pipeline.process_next()
        if result.kind == "FEED_EXHAUSTED":
            print("\n[SIMULATED] Feed exhausted -- cached history replay complete.")
            break
        if result.kind == "FEED_DISCONNECTED":
            print(f"[SIMULATED] FEED DISCONNECTED: {result.detail}")
            continue

        processed += 1
        line = f"[SIMULATED] bar#{processed:4d} {result.bar.timestamp}  {result.symbol}  close={result.bar.close:.2f}  outcome={result.kind}"
        if result.freshness is not None:
            line += f"  fresh={result.freshness.is_fresh}"
        print(line)

        if result.signal is not None:
            print(f"             signal: {result.signal.side.value} ref={result.signal.reference_price:.2f} stop={result.signal.stop_price:.2f} target={result.signal.target_price:.2f}")
        if result.journal_entry is not None:
            print(f"             risk/paper outcome: {result.journal_entry.outcome.value}")
        if result.kind == "PENDING_HUMAN_APPROVAL":
            print(f"             PENDING HUMAN APPROVAL -- signal_id={result.signal.stable_id()[:12]} (no order placed; use pipeline.approve_pending()/reject_pending())")

    print(f"\n[SIMULATED] Bars processed: {processed}")
    print(f"[SIMULATED] Account equity: {engine.account.equity:,.2f}")
    report = reconcile(store)
    print(f"[SIMULATED] Reconciliation: {'OK' if report.ok else 'FAILED'}")
    if not report.ok:
        for issue in report.issues:
            print(f"  - {issue.check}: {issue.detail}", file=sys.stderr)
        sys.exit(1)

    store.close()


# --------------------------------------------------------------------------
# `paper-live` — Phase 13 human-operated intraday workstation. Extends
# `live-sim`'s pipeline with a persistent kill switch and an interactive
# human approval prompt for every PENDING_HUMAN_APPROVAL signal. Same
# import-deferral discipline as `backtest`/`paper`/`live-sim`. Still NOT
# connected to any real broker or live feed; places no real orders.
# --------------------------------------------------------------------------

DEFAULT_LIVE_STATE_DB_PATH = PROJECT_ROOT / "data" / "live_state.db"


def _print_account_block(account) -> None:
    print("\nACCOUNT")
    print(f"  Cash:              {account.cash:,.2f}")
    print(f"  Equity:            {account.equity:,.2f}")
    print(f"  Open P&L:          {account.unrealized_pnl:,.2f}")
    print(f"  Daily P&L:         {account.daily_pnl:,.2f}")
    print(f"  Drawdown:          {account.current_drawdown_pct:.2f}%")
    print(f"  Consecutive Losses:{account.consecutive_losses:3d}")


def _print_signal_block(pipeline, result) -> None:
    signal = result.signal
    pending = pipeline.pending_approvals.get(signal.stable_id())
    quantity = pending.requested_quantity if pending else 0
    print("\nSIGNAL DETECTED")
    print(f"  Signal ID: {signal.stable_id()[:12]}")
    print(f"  Symbol:    {result.symbol}")
    print(f"  Direction: {signal.side.value}")
    print(f"  Entry:     {signal.reference_price:.2f}")
    print(f"  Stop:      {signal.stop_price:.2f}")
    print(f"  Target:    {signal.target_price:.2f}")
    print(f"  Quantity:  {quantity}")
    print("  RISK:      APPROVED (risk check #1 passed -- a second, independent")
    print("             check runs again at the moment of your decision)")


def _try_ai_explain(pipeline, result) -> str | None:
    """Optional, best-effort only. Explanation-only per spec — it cannot
    change the entry/stop/target/quantity/approval status, and it must
    never block the workflow if Ollama is unavailable."""
    try:
        from agents.signal_explainer import explain_signal
        from llm.provider import check_ollama_availability
        from market.context import MarketContext

        check_ollama_availability()
        indicators = pipeline.latest_indicators(result.symbol)
        if indicators is None:
            return None
        market_context = MarketContext.from_indicators(indicators)
        pending = pipeline.pending_approvals.get(result.signal.stable_id())
        risk_decision = pipeline.engine.risk_engine.evaluate(result.signal, pipeline.engine.account) if pending else None
        if risk_decision is None:
            return None
        explanation = explain_signal(market_context=market_context, signal=result.signal, risk_decision=risk_decision)
        pipeline.mark_ai_explained(result.signal.stable_id())
        return explanation.narrative
    except Exception as exc:  # noqa: BLE001 — AI explanation must never block approval
        logger.info("AI explanation unavailable, continuing without it: %s", exc)
        return None


def _prompt_approval(auto_approve: bool, auto_reject: bool) -> str:
    if auto_approve:
        print("\nAPPROVE [Y] / REJECT [N]: Y (--auto-approve)")
        return "APPROVE"
    if auto_reject:
        print("\nAPPROVE [Y] / REJECT [N]: N (--auto-reject)")
        return "REJECT"
    while True:
        choice = input("\nAPPROVE [Y] / REJECT [N]: ").strip().upper()
        if choice in ("Y", "YES"):
            return "APPROVE"
        if choice in ("N", "NO"):
            return "REJECT"
        print("Please answer Y or N.")


def _build_market_data_source(args: argparse.Namespace):
    """Returns (source, source_label, status_label). MOCK/SIMULATED for the
    existing scripted replay (unchanged); DHAN/LIVE for a real Dhan
    WebSocket feed (Phase 15) -- the only two labels this project's own
    DataSource/DataStatus model allows a live-sim CLI run to display,
    matching whatever the resulting bars are actually tagged with."""
    if args.source == "dhan":
        from live.dhan.config import load_dhan_credentials
        from live.dhan.instruments import DhanInstrumentMap
        from live.dhan.market_data_source import DhanMarketDataSource

        credentials = load_dhan_credentials()  # raises DhanCredentialsMissingError with a clear message if unset
        instrument_map = DhanInstrumentMap.download(force=args.refresh_instrument_map)
        source = DhanMarketDataSource(credentials=credentials, instrument_map=instrument_map, interval=args.interval)
        return source, "DHAN (real WebSocket feed)", "LIVE"

    from live.mock_source import MockMarketDataSource

    source = MockMarketDataSource.from_cached_history(args.symbol, interval=args.interval, period=args.period)
    return source, "MOCK (replaying cached history)", "SIMULATED"


def run_paper_live_command(args: argparse.Namespace) -> None:
    from live.freshness import FreshnessPolicy
    from live.pipeline import DEFAULT_APPROVAL_TIMEOUT_SECONDS, LiveSimPipeline
    from live.state_store import LiveStateStore
    from paper.engine import PaperTradingEngine
    from paper.reconciliation import reconcile
    from paper.store import PaperStore

    state_db_path = args.state_db or DEFAULT_LIVE_STATE_DB_PATH
    state_store = LiveStateStore(state_db_path)

    if args.kill_switch:
        state_store.activate_kill_switch(reason=args.kill_switch_reason or "manual CLI activation")
        print(f"[KILL SWITCH ACTIVATED] {state_db_path}")
        print("No new positions or pending approvals will be created until --reset-kill-switch is run.")
        print("Existing open positions and pending approvals are untouched.")
        state_store.close()
        return
    if args.reset_kill_switch:
        state_store.reset_kill_switch()
        print(f"[KILL SWITCH RESET] {state_db_path}")
        state_store.close()
        return

    db_path = args.db or DEFAULT_LIVE_SIM_DB_PATH
    store = PaperStore(db_path)
    engine = PaperTradingEngine(store, initial_capital=args.initial_capital)
    strategy = get_strategy(args.strategy)

    source, source_label, status_label = _build_market_data_source(args)
    freshness_policy = FreshnessPolicy(multiplier=args.freshness_multiplier)
    approval_timeout_seconds = args.approval_timeout_seconds if args.approval_timeout_seconds is not None else DEFAULT_APPROVAL_TIMEOUT_SECONDS
    pipeline = LiveSimPipeline(
        source=source, engine=engine, strategy=strategy, symbols=[args.symbol], interval=args.interval,
        freshness_policy=freshness_policy, require_human_approval=not args.no_human_approval,
        approval_timeout_seconds=approval_timeout_seconds, state_store=state_store,
    )

    print("=" * 60)
    print("HUMAN-OPERATED PAPER TRADING WORKSTATION -- NOT LIVE TRADING")
    print("=" * 60)
    print(f"SOURCE:   {source_label}")
    print(f"STATUS:   {status_label}")
    print("EXECUTION: PAPER (this is always true, regardless of data source)")
    print(f"SYMBOL:   {args.symbol}")
    print(f"INTERVAL: {args.interval}")
    print(f"DATABASE: {db_path}")
    print(f"STATE DB: {state_db_path}")
    print(f"HUMAN APPROVAL REQUIRED: {not args.no_human_approval}")
    if args.source == "dhan":
        from live.dhan.market_session import current_market_session

        session = current_market_session()
        print(f"MARKET SESSION: {session.state.value} (as of {session.as_of_ist.strftime('%H:%M:%S IST')}, does NOT account for exchange holidays)")
    print("This process places NO real orders and holds NO broker connection for execution.")
    if pipeline.is_kill_switch_active():
        print("\n*** KILL SWITCH ACTIVE *** -- no new signal will be approved or executed.")
        print("Run `python main.py paper-live --reset-kill-switch --state-db "
              f"{state_db_path}` to clear it.")
    print("=" * 60)

    processed = 0
    try:
        processed = _run_paper_live_loop(args, pipeline, engine, store, status_label, processed)
    except KeyboardInterrupt:
        print(f"\n[{status_label}] Interrupted by user (Ctrl+C) -- shutting down cleanly.")
    finally:
        # Lifecycle fix (Phase 17, found via code review — no live network involved): source.close()
        # was never called on ANY exit path, including normal completion. For --source dhan this left
        # the real WebSocket connection open, relying entirely on daemon-thread/process teardown rather
        # than a deliberate close(). Must run regardless of how the loop above exits.
        source.close()

    print(f"\n[{status_label}] Bars processed: {processed}")
    _print_account_block(engine.account)
    report = reconcile(store)
    print(f"\n[{status_label}] Reconciliation: {'OK' if report.ok else 'FAILED'}")
    # store.close()/state_store.close() moved before the reconciliation-failure exit below (Phase 17
    # fix, same finding) -- previously a failed reconciliation triggered sys.exit(1) before either was
    # ever closed.
    store.close()
    state_store.close()
    if not report.ok:
        for issue in report.issues:
            print(f"  - {issue.check}: {issue.detail}", file=sys.stderr)
        sys.exit(1)

    print("\nThis is still simulated trading. No real broker is connected. No real order can be placed.")


def _run_paper_live_loop(args: argparse.Namespace, pipeline, engine, store, status_label: str, processed: int) -> int:
    while args.max_bars is None or processed < args.max_bars:
        result = pipeline.process_next()
        for expired_id in result.expired_signal_ids:
            print(f"\n[EXPIRED] signal {expired_id[:12]} -- approval window elapsed without a decision.")

        if result.kind == "FEED_EXHAUSTED":
            print(f"\n[{status_label}] Feed exhausted -- replay complete.")
            break
        if result.kind == "FEED_DISCONNECTED":
            print(f"\n[{status_label}] FEED DISCONNECTED: {result.detail}")
            print(f"[{status_label}] No new signal will be generated while disconnected. Existing positions are still monitored on reconnect.")
            time.sleep(1.0)  # avoid a tight busy-loop if the source is permanently down (e.g. Dhan reconnect attempts exhausted)
            continue
        if result.kind == "NO_NEW_DATA":
            continue  # feed alive, nothing new this poll -- not an error, don't spam output or count as a processed bar

        processed += 1

        if result.kind == "KILL_SWITCH_ACTIVE":
            print(f"\n[{args.symbol}] bar#{processed:4d} {result.bar.timestamp}  KILL SWITCH ACTIVE -- signal suppressed, no order created.")
            continue

        if result.kind == "PENDING_HUMAN_APPROVAL":
            _print_account_block(engine.account)
            _print_signal_block(pipeline, result)
            if not args.no_ai_explanation:
                explanation = _try_ai_explain(pipeline, result)
                if explanation:
                    print("\nAI EXPLANATION (informational only -- cannot change risk/quantity/price):")
                    print(f"  {explanation}")
            decision = _prompt_approval(args.auto_approve, args.auto_reject)
            signal_id = result.signal.stable_id()
            action = pipeline.approve_pending(signal_id) if decision == "APPROVE" else pipeline.reject_pending(signal_id)
            detail = f" ({action.journal_entry.outcome.value})" if action.journal_entry else ""
            print(f"  -> {action.outcome.value}{detail}")
            continue

        line = f"[{args.symbol}] bar#{processed:4d} {result.bar.timestamp}  close={result.bar.close:.2f}  {result.kind}"
        if result.freshness is not None:
            line += f"  fresh={result.freshness.is_fresh}"
        position = store.get_open_position(args.symbol)
        if position is not None:
            # Continuous position monitoring, reusing the same Position/
            # Account fields the ACCOUNT/reconciliation blocks already use —
            # nothing here recomputes P&L, exposure, or risk.
            line += (
                f"  | POSITION qty={position.quantity} entry={position.entry_price:.2f} "
                f"stop={position.stop_price:.2f} target={position.target_price:.2f} "
                f"open_pnl={engine.account.unrealized_pnl:,.2f} equity={engine.account.equity:,.2f}"
            )
        print(line)

    return processed


# --------------------------------------------------------------------------
# `dashboard` — Phase 13 §19 minimal local web view of the SAME persistent
# paper-live state (live/workstation.py) the CLI and MCP tools use. Local-
# only by default (127.0.0.1); no new dependency (Starlette/uvicorn are
# already installed as transitive deps of the `mcp` package).
# --------------------------------------------------------------------------


def run_dashboard_command(args: argparse.Namespace) -> None:
    import uvicorn

    from dashboard.app import app

    print(f"Starting the paper-live dashboard at http://{args.host}:{args.port} (SIMULATED, local-only).")
    print("This page reads/acts on the SAME state main.py's paper-live CLI writes to.")
    print("It does not advance the market itself -- run `python main.py paper-live ...` to process bars.")
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


# --------------------------------------------------------------------------
# `scan` -- Phase 19 market scanner: MarketUniverse -> ranked, explainable
# candidates. No AI, no recommendation, no buy/sell/quantity/price level --
# see market_intelligence/models.py's module docstring. Same
# import-deferral discipline as `backtest`/`paper`.
# --------------------------------------------------------------------------

DEFAULT_SCANNER_DB_PATH = PROJECT_ROOT / "data" / "scanner.db"


def _build_provider(args: argparse.Namespace):
    """Phase 30 -- returns (provider_for_use, resilient_provider_or_None).

    If `args.resilient` (opt-in, default off on every command that
    offers it), wraps the real network-calling provider with
    market_data.resilience.ResilientMarketDataProvider (timeout/retry
    with backoff+jitter/circuit-breaker/metrics) INSIDE the existing
    cache layer -- a cache hit still skips resilience entirely, since
    no network call happens on a hit. Deliberately opt-in rather than
    the new default everywhere: it changes call latency/threading
    behavior on failure, and every existing test's fixture-patching of
    get_market_data_provider/CachedMarketDataProvider must keep working
    completely unchanged for a caller that never passes --resilient."""
    from backtesting.cache import CachedMarketDataProvider
    from market.data_provider import get_market_data_provider

    if getattr(args, "resilient", False):
        from market_data.resilience import build_resilient_provider

        resilient = build_resilient_provider(get_market_data_provider())
        return CachedMarketDataProvider(resilient), resilient
    return CachedMarketDataProvider(get_market_data_provider()), None


def _print_provider_metrics(resilient) -> None:
    if resilient is not None:
        print(f"\nProvider metrics (--resilient): {resilient.metrics.summary_line()}")


def _build_live_snapshot_provider(args: argparse.Namespace):
    """Phase 31 -- returns a market_data.contracts.SnapshotAdapter, or
    None if `--live-source` was not passed. Dhan is currently the only
    real, credential-backed live source this project has; this reuses
    the EXACT same credential-loading (`load_dhan_credentials`) and
    instrument-map download (`DhanInstrumentMap.download` -- public,
    unauthenticated) `paper-live --source dhan` already established in
    Phase 15/16, and the EXACT same, unmodified Phase 18
    `market_data.adapters.dhan.build_dhan_adapter` -- no new connection
    mechanism is introduced anywhere in this phase."""
    if getattr(args, "live_source", None) != "dhan":
        return None

    from live.dhan.config import load_dhan_credentials
    from live.dhan.instruments import DhanInstrumentMap
    from market_data.adapters.dhan import build_dhan_adapter

    logger.info("Connecting a live Dhan snapshot source (--live-source dhan)")
    credentials = load_dhan_credentials()
    instrument_map = DhanInstrumentMap.download()
    return build_dhan_adapter(credentials=credentials, instrument_map=instrument_map, interval="1m")


def run_scan_command(args: argparse.Namespace) -> None:
    from market_data.universe import MarketUniverse
    from market_intelligence.scanner import run_scan
    from market_intelligence.store import ScanHistoryStore

    if args.watchlist_file:
        universe = MarketUniverse.from_yaml_file(args.watchlist_file)
    elif args.symbols:
        symbols = [s for s in args.symbols.split(",") if s.strip()]
        universe = MarketUniverse.from_watchlist(symbols)
    else:
        print("scan: one of --symbols or --watchlist-file is required.", file=sys.stderr)
        sys.exit(2)

    provider, resilient = _build_provider(args)
    benchmark_symbol = args.benchmark or None

    logger.info("Running market scan over %d symbols (universe=%s)", len(universe), universe.mode)
    report = run_scan(
        universe, provider=provider, benchmark_symbol=benchmark_symbol,
        period=args.period, interval=args.interval,
    )

    db_path = args.db or DEFAULT_SCANNER_DB_PATH
    store = ScanHistoryStore(db_path)
    store.save_report(report)
    store.close()

    print("=" * 70)
    print("MARKET SCANNER -- CANDIDATE DISCOVERY (no recommendation, no buy/sell)")
    print("=" * 70)
    print(f"Scan ID:        {report.scan_id}")
    print(f"As of:          {report.as_of.isoformat()}")
    print(f"Universe:       {report.universe_mode} ({report.universe_size} symbols)")
    benchmark_line = report.benchmark_symbol or "none"
    if report.benchmark_unavailable_reason:
        benchmark_line += f"  (unavailable: {report.benchmark_unavailable_reason})"
    print(f"Benchmark:      {benchmark_line}")
    print(f"Config version: {report.config_version}")
    print(f"Database:       {db_path}")
    print(f"\nCandidates: {len(report.candidates)}   Excluded: {len(report.excluded)}\n")

    for candidate in report.candidates[: args.top]:
        print(f"{candidate.symbol:12s} score={candidate.composite_score:+.3f}  close={candidate.last_close:.2f}  as_of={candidate.as_of}")
        for line in candidate.explanation:
            print(f"    - {line}")

    if report.excluded:
        print(f"\nExcluded ({len(report.excluded)}):")
        for item in report.excluded:
            print(f"  {item.symbol:12s} {item.reason}")

    from market_intelligence.regime import compute_breadth

    breadth = compute_breadth(report)
    ratio_text = f"{breadth.advance_decline_ratio:.2f}" if breadth.advance_decline_ratio is not None else "n/a"
    print(f"\nMarket breadth (this scan): {breadth.advancing} advancing, {breadth.declining} declining, {breadth.flat} flat (advance/decline ratio: {ratio_text})")

    _print_provider_metrics(resilient)


# --------------------------------------------------------------------------
# `regime` -- Phase 33 market regime & breadth intelligence: reads the
# latest persisted scan (breadth + sector strength are pure aggregations
# over it, zero extra network calls) and fetches ONE fresh benchmark
# series for trend/volatility classification. Every number here is a
# direct reuse of an existing indicator or classifier -- no AI, no
# opaque scoring. No recommendation, no buy/sell, no order.
# --------------------------------------------------------------------------


def run_regime_command(args: argparse.Namespace) -> None:
    from market_intelligence.regime import build_market_regime_report
    from market_intelligence.store import ScanHistoryStore

    scanner_db = args.scanner_db or DEFAULT_SCANNER_DB_PATH
    store = ScanHistoryStore(scanner_db)
    scan_report = store.latest_report()
    store.close()

    if scan_report is None:
        print(f"regime: no scan found in {scanner_db} -- run `scan` first.", file=sys.stderr)
        sys.exit(1)

    # --benchmark not passed at all (None) -> inherit whatever the scan itself
    # used. Passed as "" -> explicitly disable. Passed as a symbol -> override.
    # (matches `scan --benchmark ""`'s own existing disable convention.)
    from market_intelligence.regime import USE_SCAN_REPORTS_OWN_BENCHMARK

    benchmark_symbol = USE_SCAN_REPORTS_OWN_BENCHMARK if args.benchmark is None else (args.benchmark or None)

    sector_map = None
    if args.with_sectors:
        from research.sector import YahooSectorInfoProvider, build_sector_map

        logger.info("Building a sector map for %d scanned symbols (--with-sectors)", len(scan_report.candidates))
        sector_map = build_sector_map((c.symbol for c in scan_report.candidates), YahooSectorInfoProvider())

    provider, resilient = _build_provider(args)
    report = build_market_regime_report(
        scan_report, provider=provider, benchmark_symbol=benchmark_symbol, sector_map=sector_map,
        period=args.period, interval=args.interval,
    )

    print("=" * 70)
    print("MARKET REGIME & BREADTH -- EXPLAINABLE AGGREGATES (no recommendation, no buy/sell)")
    print("=" * 70)
    print(f"Based on scan:  {report.scan_id} (as of {scan_report.as_of.isoformat()})")
    print(f"Generated at:   {report.as_of.isoformat()}")

    print("\nBREADTH (this scan's universe):")
    ratio_text = f"{report.breadth.advance_decline_ratio:.2f}" if report.breadth.advance_decline_ratio is not None else "n/a"
    pct_text = f"{report.breadth.advancing_pct:.1%}" if report.breadth.advancing_pct is not None else "n/a"
    print(f"  Advancing:  {report.breadth.advancing}")
    print(f"  Declining:  {report.breadth.declining}")
    print(f"  Flat:       {report.breadth.flat}")
    print(f"  A/D ratio:  {ratio_text}")
    print(f"  Advancing%: {pct_text}")

    print(f"\nBENCHMARK ({report.benchmark.symbol or 'none configured'}):")
    if report.benchmark.symbol is not None:
        print(f"  Trend regime:      {report.benchmark.trend_regime}")
        print(f"  Volatility regime: {report.benchmark.volatility_regime}")
        if report.benchmark.atr_pct_vs_trailing_average is not None:
            print(f"  ATR% vs trailing avg: {report.benchmark.atr_pct_vs_trailing_average:.2f}x")
        if report.benchmark.last_close is not None:
            print(f"  Last close:        {report.benchmark.last_close:.2f}")

    if sector_map is not None:
        print(f"\nSECTOR STRENGTH ({len(report.sector_strength)} sector(s), strongest first):")
        if not report.sector_strength:
            print("  (no symbol in this scan had a recognized sector)")
        for sector in report.sector_strength:
            print(f"  {sector.sector:24s} n={sector.symbol_count:3d}  avg composite={sector.average_composite_score:+.2f}")
    else:
        print("\nSECTOR STRENGTH: not computed (pass --with-sectors to build one -- costs one extra fetch per symbol).")

    _print_provider_metrics(resilient)


# --------------------------------------------------------------------------
# `research` -- Phase 20 research intelligence: real Yahoo Finance news +
# sector classification, plus an OPTIONAL, never-blocking AI summary
# (narration only -- same posture as the AI explanation step in
# `paper-live`). No recommendation, no buy/sell/quantity/price level.
# --------------------------------------------------------------------------

DEFAULT_RESEARCH_DB_PATH = PROJECT_ROOT / "data" / "research.db"


def run_research_command(args: argparse.Namespace) -> None:
    from research.news import YahooNewsProvider
    from research.sector import YahooSectorInfoProvider
    from research.store import ResearchStore
    from research.summarizer import build_research_report

    logger.info("Running research for %s", args.symbol)
    report = build_research_report(
        args.symbol,
        news_provider=YahooNewsProvider(),
        sector_provider=YahooSectorInfoProvider(),
        include_ai_summary=not args.no_ai_summary,
        news_limit=args.news_limit,
    )

    db_path = args.db or DEFAULT_RESEARCH_DB_PATH
    store = ResearchStore(db_path)
    store.save_report(report)
    store.close()

    print("=" * 70)
    print("RESEARCH REPORT -- EVIDENCE ONLY (no recommendation, no buy/sell)")
    print("=" * 70)
    print(f"Report ID:  {report.report_id}")
    print(f"Symbol:     {report.symbol}")
    print(f"As of:      {report.as_of.isoformat()}")
    print(f"Database:   {db_path}")

    if report.sector is not None:
        print(f"\nSector:     {report.sector.sector or 'UNKNOWN'}")
        print(f"Industry:   {report.sector.industry or 'UNKNOWN'}")
    else:
        print("\nSector:     not available")

    print(f"\nNews ({len(report.news)}):")
    if not report.news:
        print("  (none available)")
    for item in report.news:
        print(f"  [{item.published_at.isoformat()}] ({item.source}) {item.title}")
        if item.url:
            print(f"      {item.url}")

    if report.ai_summary is not None:
        print("\nAI SUMMARY (narration only -- not a recommendation):")
        print(f"  {report.ai_summary.summary}")
        print(f"  Confidence: {report.ai_summary.confidence:.2f}")
        if report.ai_summary.unknowns:
            print("  Unknowns:")
            for unknown in report.ai_summary.unknowns:
                print(f"    - {unknown}")
    else:
        reason = report.ai_summary_unavailable_reason or "AI summary skipped (--no-ai-summary)."
        print(f"\nAI SUMMARY: not available ({reason})")


# --------------------------------------------------------------------------
# `decide` -- Phase 21 decision intelligence engine: combines the latest
# persisted scanner + research evidence into a BUY/WATCH/AVOID/EXIT/
# NO_ACTION LABEL, with a never-blocking, optional AI narrative. This is
# NOT an order and places NO trade -- decision_engine/ never imports
# paper/ or any broker adapter. Converting a label into an actual paper
# trade remains a separate, unchanged, entirely manual step.
# --------------------------------------------------------------------------

DEFAULT_DECISION_DB_PATH = PROJECT_ROOT / "data" / "decisions.db"


def run_decide_command(args: argparse.Namespace) -> None:
    from pathlib import Path

    from decision_engine.engine import make_decision
    from decision_engine.models import RiskContext
    from decision_engine.store import DecisionStore
    from market_intelligence.store import ScanHistoryStore
    from research.store import ResearchStore

    normalized = args.symbol.strip().upper()

    scanner_db = args.scanner_db or DEFAULT_SCANNER_DB_PATH
    candidate = None
    if Path(scanner_db).exists():
        scan_store = ScanHistoryStore(scanner_db)
        latest_scan = scan_store.latest_report()
        if latest_scan is not None:
            candidate = latest_scan.get(normalized)
        scan_store.close()

    research_db = args.research_db or DEFAULT_RESEARCH_DB_PATH
    research_report = None
    if Path(research_db).exists():
        research_store = ResearchStore(research_db)
        research_report = research_store.latest_report_for_symbol(normalized)
        research_store.close()

    risk_context = RiskContext.unknown()
    if args.paper_db:
        from paper.store import PaperStore

        paper_store = PaperStore(args.paper_db)
        open_position = paper_store.get_open_position(normalized)
        account = paper_store.get_account()
        risk_context = RiskContext(
            has_open_position=open_position is not None,
            consecutive_losses=account.consecutive_losses if account is not None else 0,
            note=f"Derived from paper account state at {args.paper_db}.",
        )
        paper_store.close()

    logger.info("Running decision engine for %s", normalized)
    decision = make_decision(
        normalized, candidate=candidate, research=research_report, risk_context=risk_context,
        include_narrative=not args.no_narrative,
    )

    db_path = args.db or DEFAULT_DECISION_DB_PATH
    store = DecisionStore(db_path)
    store.save_decision(decision)
    store.close()

    print("=" * 70)
    print("DECISION -- LABEL ONLY, NOT AN ORDER (no trade is placed by this command)")
    print("=" * 70)
    print(f"Decision ID:    {decision.decision_id}")
    print(f"Symbol:         {decision.symbol}")
    print(f"As of:          {decision.as_of.isoformat()}")
    print(f"LABEL:          {decision.label.value}")
    if decision.confidence is not None:
        print(f"Confidence:     {decision.confidence:.0%} ({decision.confidence_explanation})")
    print(f"Config version: {decision.config_version}")
    print(f"Database:       {db_path}")

    print("\nRationale:")
    for line in decision.rationale:
        print(f"  - {line}")

    if candidate is None:
        print(f"\nScanner evidence: none found for {normalized} (run `scan` first, or check --scanner-db).")
    if research_report is None:
        print(f"Research evidence: none found for {normalized} (run `research` first, or check --research-db).")
    if decision.risk_context.note:
        print(f"Risk context: {decision.risk_context.note}")

    if decision.narrative is not None:
        print("\nAI NARRATIVE (explanation only -- cannot change the label above):")
        print(f"  {decision.narrative}")
    else:
        reason = decision.narrative_unavailable_reason or "AI narrative skipped (--no-narrative)."
        print(f"\nAI NARRATIVE: not available ({reason})")


# --------------------------------------------------------------------------
# `size` -- Phase 22: bridges decision_engine's BUY label to the EXISTING,
# UNCHANGED RiskEngine/Account/RiskConfig dynamic position-sizing math.
# A PREVIEW ONLY -- no order, real or paper, is placed by this command;
# it only reports what the existing paper-trading risk engine would size
# this decision at, given the specified capital.
# --------------------------------------------------------------------------


def run_size_command(args: argparse.Namespace) -> None:
    from pathlib import Path

    from decision_engine.store import DecisionStore
    from market.context import get_market_context
    from risk.account import new_account
    from risk.sizing import size_decision

    normalized = args.symbol.strip().upper()

    decision_db = args.decision_db or DEFAULT_DECISION_DB_PATH
    decision = None
    if Path(decision_db).exists():
        decision_store = DecisionStore(decision_db)
        decision = decision_store.latest_decision_for_symbol(normalized)
        decision_store.close()

    if decision is None:
        print(f"size: no decision found for {normalized} in {decision_db} -- run `decide --symbol {normalized}` first.", file=sys.stderr)
        sys.exit(1)

    risk_config = RiskConfig(
        risk_per_trade_pct=args.risk_per_trade,
        max_daily_loss_pct=args.max_daily_loss,
        max_drawdown_pct=args.max_drawdown,
        max_exposure_pct=args.max_exposure,
        max_consecutive_losses=args.max_consecutive_losses,
        consecutive_loss_risk_multiplier=args.consecutive_loss_risk_multiplier,
        consecutive_loss_hard_limit=args.consecutive_loss_hard_limit,
        min_risk_reward=args.min_risk_reward,
    )
    account = new_account(args.initial_capital)

    logger.info("Sizing %s decision for %s against %.2f capital", decision.label.value, normalized, args.initial_capital)
    live_snapshot_provider = _build_live_snapshot_provider(args)
    market_context = get_market_context(normalized, period=args.period, interval=args.interval, live_snapshot_provider=live_snapshot_provider)
    risk_decision = size_decision(decision, market_context=market_context, account=account, risk_config=risk_config)

    print("=" * 70)
    print("POSITION SIZING PREVIEW -- NOT AN ORDER (no real or paper trade is placed)")
    print("=" * 70)
    print(f"Symbol:         {normalized}")
    print(f"Decision:       {decision.label.value} (as of {decision.as_of.isoformat()}, decision_id={decision.decision_id})")
    print(f"Capital:        {args.initial_capital:,.2f}")
    print(f"Data source:    {market_context.data_source or 'UNKNOWN'} ({market_context.data_status or 'UNKNOWN'})")
    print(f"\n{risk_decision.explanation}")
    print(f"Approved:       {risk_decision.approved}")
    if risk_decision.position_size is not None:
        print(f"Quantity:       {risk_decision.position_size.quantity}")
        print(f"Risk amount:    {risk_decision.risk_amount:,.2f} ({risk_decision.risk_percent:.2f}% of equity)")
        print(f"Notional:       {risk_decision.position_size.notional_value:,.2f}")
    if risk_decision.exposure is not None:
        print(f"Exposure:       {risk_decision.exposure.exposure_pct:.2f}% of equity")
    if risk_decision.veto_reasons:
        print("Veto reasons:")
        for reason in risk_decision.veto_reasons:
            print(f"  - {reason.value}")


# --------------------------------------------------------------------------
# `predict` / `evaluate` -- Phase 23 shadow prediction & continuous
# evaluation. The system keeps a record of what it would have done and
# monitors real subsequent market data against it, whether or not the
# user actually traded it. NOT an order, real or paper -- predictions/
# never imports paper/ or any broker adapter.
# --------------------------------------------------------------------------

DEFAULT_PREDICTIONS_DB_PATH = PROJECT_ROOT / "data" / "predictions.db"


def _risk_config_from_args(args: argparse.Namespace) -> RiskConfig:
    return RiskConfig(
        risk_per_trade_pct=args.risk_per_trade, max_daily_loss_pct=args.max_daily_loss,
        max_drawdown_pct=args.max_drawdown, max_exposure_pct=args.max_exposure,
        max_consecutive_losses=args.max_consecutive_losses, consecutive_loss_risk_multiplier=args.consecutive_loss_risk_multiplier,
        consecutive_loss_hard_limit=args.consecutive_loss_hard_limit, min_risk_reward=args.min_risk_reward,
    )


def _size_if_requested(decision, *, market_context, args: argparse.Namespace):
    """Shared by `predict`/`shadow-run`: computes and returns a real
    risk.contracts.RiskDecision to persist alongside a prediction, ONLY
    when the caller passed --initial-capital (see _add_optional_sizing_args's
    own docstring on why None is the sentinel for "don't size at all,
    preserve prior behavior exactly"). A fresh risk.account.Account is
    built each call -- this is a per-decision "what if I took this trade
    against my configured capital" preview, the same posture `size`
    itself already has, not a portfolio-aware sequential simulation."""
    if args.initial_capital is None:
        return None
    from risk.account import new_account
    from risk.sizing import size_decision

    account = new_account(args.initial_capital)
    return size_decision(decision, market_context=market_context, account=account, risk_config=_risk_config_from_args(args))


def _bridge_to_paper_execution(signal, risk_decision, *, engine, state_store) -> str | None:
    """Explicit, opt-in bridge from a decision_engine BUY into a REAL
    paper.engine.PaperTradingEngine order -- the SAME idempotent,
    risk-gated `submit_signal` mechanism `paper`/`paper-live` already
    use, never a second, competing execution path. Returns a short
    outcome string to print, or None if paper execution was not even
    attempted (no risk_decision was computed, or the kill switch is
    active) -- the shadow prediction itself is recorded regardless,
    completely independent of this.

    Deliberately does NOT re-check risk_decision.approved before calling
    submit_signal: `_size_if_requested`'s preview evaluates against a
    FRESH, hypothetical account every time (the same posture `size`
    itself has), while `engine`'s real account reflects whatever THIS
    SAME run's earlier symbols already submitted -- for a
    single-position account, a later symbol in the same run can
    genuinely and correctly differ from its own preview (e.g.
    SKIPPED_ALREADY_ACTIVE after an earlier symbol's order was
    submitted). submit_signal's own real-account evaluation is the only
    authoritative answer for what actually happens; the persisted
    risk_decision is a preview, not a promise."""
    if risk_decision is None:
        return None
    if state_store.is_kill_switch_active():
        return "SKIPPED (kill switch active)"
    journal = engine.submit_signal(signal, strategy_version="decision_engine_buy_bridge/1.0")
    return journal.outcome.value


def _print_risk_decision_if_present(risk_decision) -> None:
    if risk_decision is None:
        return
    print("\nTrade plan (persisted with this prediction -- NOT an order):")
    print(f"  Capital:        {risk_decision.account_equity:,.2f}")
    print(f"  Approved:       {risk_decision.approved}")
    if risk_decision.position_size is not None:
        print(f"  Quantity:       {risk_decision.position_size.quantity}")
        print(f"  Risk amount:    {risk_decision.risk_amount:,.2f} ({risk_decision.risk_percent:.2f}% of equity)")
        print(f"  Notional:       {risk_decision.position_size.notional_value:,.2f}")
    if risk_decision.veto_reasons:
        print(f"  Veto reasons:   {', '.join(r.value for r in risk_decision.veto_reasons)}")


def run_predict_command(args: argparse.Namespace) -> None:
    from pathlib import Path

    from decision_engine.store import DecisionStore
    from market.context import get_market_context
    from predictions.store import PredictionStore
    from predictions.tracker import create_prediction
    from risk.sizing import build_signal_for_buy

    normalized = args.symbol.strip().upper()

    decision_db = args.decision_db or DEFAULT_DECISION_DB_PATH
    decision = None
    if Path(decision_db).exists():
        decision_store = DecisionStore(decision_db)
        decision = decision_store.latest_decision_for_symbol(normalized)
        decision_store.close()

    if decision is None:
        print(f"predict: no decision found for {normalized} in {decision_db} -- run `decide --symbol {normalized}` first.", file=sys.stderr)
        sys.exit(1)

    logger.info("Recording a shadow prediction for %s from decision %s", normalized, decision.decision_id)
    live_snapshot_provider = _build_live_snapshot_provider(args)
    market_context = get_market_context(normalized, period=args.period, interval=args.interval, live_snapshot_provider=live_snapshot_provider)

    db_path = args.db or DEFAULT_PREDICTIONS_DB_PATH
    store = PredictionStore(db_path)
    # Phase 36: duplicate prevention -- a prediction already recorded for
    # this exact entry bar (e.g. `predict` run twice against an unchanged
    # daily close) must not silently inflate prediction counts / skew
    # win-rate statistics with a second, redundant row.
    if store.has_prediction_for_entry(normalized, market_context.as_of):
        store.close()
        print(f"predict: a prediction for {normalized} at entry bar {market_context.as_of.isoformat()} is already recorded -- skipping duplicate.", file=sys.stderr)
        sys.exit(1)

    signal = build_signal_for_buy(decision, market_context)
    risk_decision = _size_if_requested(decision, market_context=market_context, args=args)
    prediction = create_prediction(decision, signal, horizon_bars=args.horizon_bars, interval=args.interval, risk_decision=risk_decision)
    store.save_prediction(prediction)
    store.close()

    print("=" * 70)
    print("SHADOW PREDICTION RECORDED -- NOT AN ORDER (tracked for later evaluation only)")
    print("=" * 70)
    print(f"Prediction ID:  {prediction.prediction_id}")
    print(f"Decision ID:    {prediction.decision_id}")
    print(f"Symbol:         {prediction.symbol}")
    print(f"Entry:          {prediction.entry_price:.2f} (at {prediction.entry_time.isoformat()})")
    print(f"Stop:           {prediction.stop_price:.2f}")
    print(f"Target:         {prediction.target_price:.2f}")
    print(f"Horizon:        {prediction.horizon_bars} bars ({prediction.interval})")
    print(f"Database:       {db_path}")
    print(f"Data source:    {market_context.data_source or 'UNKNOWN'} ({market_context.data_status or 'UNKNOWN'})")
    _print_risk_decision_if_present(prediction.risk_decision)
    print("\nThis is a hypothetical shadow prediction, tracked whether or not you trade it.")
    print("Run `python main.py evaluate` later to check its outcome against real subsequent market data.")


def run_evaluate_command(args: argparse.Namespace) -> None:
    from predictions.store import PredictionStore
    from predictions.tracker import evaluate_prediction, summarize_predictions

    db_path = args.db or DEFAULT_PREDICTIONS_DB_PATH
    store = PredictionStore(db_path)
    pending = store.list_predictions_needing_evaluation()
    provider, resilient = _build_provider(args)

    print("=" * 70)
    print("SHADOW PREDICTION EVALUATION -- NOT AN ORDER (outcome monitoring only)")
    print("=" * 70)
    print(f"Database:                       {db_path}")
    print(f"Predictions needing evaluation: {len(pending)}\n")

    for prediction in pending:
        logger.info("Evaluating prediction %s (%s)", prediction.prediction_id, prediction.symbol)
        try:
            evaluation = evaluate_prediction(prediction, provider=provider, period=args.period)
            store.save_evaluation(evaluation)
            print(f"{prediction.symbol:10s} {prediction.prediction_id[:12]}  {evaluation.outcome.value:18s} {evaluation.detail}")
        except Exception as exc:  # noqa: BLE001 -- one prediction's failure (an unexpected error beyond the MarketDataError evaluate_prediction already handles internally) must never abort evaluation of the rest of the batch, same posture as shadow-run's per-symbol isolation.
            logger.warning("evaluate: %s (%s) failed, continuing with the rest of the batch: %s", prediction.symbol, prediction.prediction_id, exc)
            print(f"{prediction.symbol:10s} {prediction.prediction_id[:12]}  FAILED               {exc}")

    summary = summarize_predictions(store.list_all_evaluations())
    store.close()

    print("\nSummary (latest evaluation per prediction):")
    print(f"  Total:             {summary.total_predictions}")
    print(f"  Active:            {summary.active}")
    print(f"  Target hit:        {summary.target_hit}")
    print(f"  Stop hit:          {summary.stop_hit}")
    print(f"  Expired:           {summary.expired}")
    print(f"  Insufficient data: {summary.insufficient_data}")
    print(f"  Win rate:          {f'{summary.win_rate:.1%}' if summary.win_rate is not None else 'n/a (nothing resolved yet)'}")
    print(f"  Average return:    {f'{summary.average_return:+.2%}' if summary.average_return is not None else 'n/a'}")
    print(f"  Profit factor:     {f'{summary.profit_factor:.2f}' if summary.profit_factor is not None else 'n/a'}")
    _print_provider_metrics(resilient)


# --------------------------------------------------------------------------
# `learn` -- Phase 24 performance learning: READ-ONLY analysis over Phase
# 23's prediction history (strategy comparison, market regime performance,
# confidence calibration, signal quality). Per the roadmap's own Phase 24
# rule ("No automatic strategy modification without Versioning/Evaluation/
# Rollback/Audit Trail"), this command changes no configuration and places
# no order -- learning/ never writes to DecisionConfig, RiskConfig, or
# anything else.
# --------------------------------------------------------------------------


def _fmt_pct(value: float | None) -> str:
    return f"{value:+.2%}" if value is not None else "n/a"


def _fmt_ratio(value: float | None) -> str:
    return f"{value:.2f}" if value is not None else "n/a"


def run_learn_command(args: argparse.Namespace) -> None:
    from pathlib import Path

    from decision_engine.store import DecisionStore
    from learning.analysis import EvaluatedPrediction, build_learning_report
    from predictions.store import PredictionStore

    predictions_db = args.predictions_db or DEFAULT_PREDICTIONS_DB_PATH
    decision_db = args.decision_db or DEFAULT_DECISION_DB_PATH

    items: list[EvaluatedPrediction] = []
    if Path(predictions_db).exists():
        prediction_store = PredictionStore(predictions_db)
        decision_store = DecisionStore(decision_db) if Path(decision_db).exists() else None

        for prediction in prediction_store.list_predictions():
            evaluation = prediction_store.latest_evaluation_for_prediction(prediction.prediction_id)
            if evaluation is None:
                continue
            decision = decision_store.get_decision(prediction.decision_id) if decision_store is not None else None
            items.append(EvaluatedPrediction(prediction=prediction, evaluation=evaluation, decision=decision))

        prediction_store.close()
        if decision_store is not None:
            decision_store.close()

    logger.info("Building performance learning report over %d evaluated predictions", len(items))
    provider, resilient = _build_provider(args)
    report = build_learning_report(items, provider=provider)

    print("=" * 70)
    print("PERFORMANCE LEARNING REPORT -- READ-ONLY (no configuration changed, no order placed)")
    print("=" * 70)
    print(f"Generated at:           {report.generated_at.isoformat()}")
    print(f"Predictions considered: {report.total_predictions_considered}")

    print("\nStrategy comparison (by decision config version):")
    if not report.strategy_comparison:
        print("  (none)")
    for s in report.strategy_comparison:
        print(
            f"  {s.config_version:18s} total={s.total:4d} resolved={s.resolved:4d} "
            f"win_rate={_fmt_pct(s.win_rate)} avg_return={_fmt_pct(s.average_return)} profit_factor={_fmt_ratio(s.profit_factor)}"
        )

    print("\nMarket regime performance (at entry):")
    if not report.regime_performance:
        print("  (none)")
    for r in report.regime_performance:
        print(f"  {r.regime.value:10s} total={r.total:4d} resolved={r.resolved:4d} win_rate={_fmt_pct(r.win_rate)} avg_return={_fmt_pct(r.average_return)}")

    print("\nConfidence calibration (composite score median split -- legacy proxy):")
    if not report.confidence_calibration:
        print("  (none -- no predictions with recorded scanner evidence)")
    for c in report.confidence_calibration:
        print(f"  {c.bucket_label:34s} total={c.total:4d} resolved={c.resolved:4d} win_rate={_fmt_pct(c.win_rate)} avg_return={_fmt_pct(c.average_return)}")

    print("\nConfidence calibration (Phase 34: real decision_engine.confidence score, fixed LOW/MEDIUM/HIGH bands):")
    if not report.real_confidence_calibration:
        print("  (none -- no decisions with a recorded confidence score)")
    for c in report.real_confidence_calibration:
        print(f"  {c.bucket_label:34s} total={c.total:4d} resolved={c.resolved:4d} win_rate={_fmt_pct(c.win_rate)} avg_return={_fmt_pct(c.average_return)}")

    print("\nSignal quality (resolved predictions only):")
    print(f"  Resolved:                {report.signal_quality.resolved}")
    print(f"  Avg favorable excursion: {_fmt_pct(report.signal_quality.average_favorable_excursion)}")
    print(f"  Avg adverse excursion:   {_fmt_pct(report.signal_quality.average_adverse_excursion)}")

    print("\nSector performance (at decision time):")
    if not report.sector_performance:
        print("  (none -- no decisions with recorded research/sector evidence)")
    for s in report.sector_performance:
        print(f"  {s.sector:24s} total={s.total:4d} resolved={s.resolved:4d} win_rate={_fmt_pct(s.win_rate)} avg_return={_fmt_pct(s.average_return)}")

    p = report.profitability
    print("\nProfitability evidence (Phase 41 -- this project makes NO profitability claim beyond this verdict):")
    print(f"  Verdict:                {p.verdict.value}")
    print(f"  Sample size (resolved): {p.sample_size}")
    print(f"  Win rate:               {_fmt_pct(p.win_rate)}  (95% CI [{_fmt_pct(p.win_rate_ci_low)}, {_fmt_pct(p.win_rate_ci_high)}])" if p.win_rate is not None else "  Win rate:               n/a")
    print(f"  Average win:            {_fmt_pct(p.average_win)}")
    print(f"  Average loss:           {_fmt_pct(p.average_loss)}")
    print(f"  Expectancy (per trade): {_fmt_pct(p.expectancy)}")
    print(f"  Profit factor:          {_fmt_ratio(p.profit_factor)}")
    print(f"  Max drawdown:           {_fmt_pct(p.max_drawdown)}")
    print(f"  Return volatility:      {_fmt_pct(p.return_volatility)} (per-trade stdev -- NOT a time-normalized Sharpe ratio)")
    if p.mean_return_ci_low is not None:
        print(f"  Mean return 95% CI:     [{_fmt_pct(p.mean_return_ci_low)}, {_fmt_pct(p.mean_return_ci_high)}]")
    print("  Reasoning:")
    for line in p.reasoning:
        print(f"    - {line}")

    print("\nNotes:")
    for note in report.notes:
        print(f"  - {note}")
    _print_provider_metrics(resilient)


# --------------------------------------------------------------------------
# `experiment` -- Phase 37 experiment tracking: a NAMED, REGISTERED record
# of "I am deliberately running this configuration, starting now, for
# this reason" -- distinct from decision_engine.config.DecisionConfig/
# market_intelligence.config.ScannerConfig/risk.config.RiskConfig's own
# existing, unmodified deterministic version_id() hashing, which this
# reuses rather than re-deriving. Append-only: `start` and `end` never
# rewrite a registered experiment, only add a new event -- current
# status is always DERIVED from the latest event.
# --------------------------------------------------------------------------

DEFAULT_EXPERIMENTS_DB_PATH = PROJECT_ROOT / "data" / "experiments.db"


def _resolve_current_config_version(config_type) -> str:
    from experiments.models import ConfigType

    if config_type == ConfigType.DECISION_ENGINE:
        from decision_engine.config import DecisionConfig

        return DecisionConfig().version_id()
    if config_type == ConfigType.SCANNER:
        from market_intelligence.config import ScannerConfig

        return ScannerConfig().version_id()
    from risk.config import RiskConfig

    return RiskConfig().version_id()


def run_experiment_command(args: argparse.Namespace) -> None:
    from datetime import timezone

    from experiments.models import ConfigType, Experiment, ExperimentEvent, ExperimentEventType
    from experiments.store import ExperimentStore

    db_path = args.db or DEFAULT_EXPERIMENTS_DB_PATH
    store = ExperimentStore(db_path)

    if args.experiment_command == "start":
        config_type = ConfigType(args.config_type)
        config_version = _resolve_current_config_version(config_type)
        now = datetime.now(timezone.utc)
        experiment = Experiment(
            experiment_id=Experiment.new_id(), name=args.name, description=args.description or "",
            config_type=config_type, config_version=config_version, started_at=now,
        )
        store.save_experiment(experiment)
        store.save_event(ExperimentEvent(
            event_id=ExperimentEvent.new_id(), experiment_id=experiment.experiment_id,
            event_type=ExperimentEventType.STARTED, occurred_at=now, detail="registered via `experiment start`",
        ))
        store.close()

        print("=" * 70)
        print("EXPERIMENT REGISTERED -- dataset/time boundary starts now")
        print("=" * 70)
        print(f"Experiment ID:  {experiment.experiment_id}")
        print(f"Name:           {experiment.name}")
        print(f"Config type:    {experiment.config_type.value}")
        print(f"Config version: {experiment.config_version}")
        print(f"Started at:     {experiment.started_at.isoformat()}")
        print(f"Database:       {db_path}")
        print("\nThis records WHICH config is in effect and WHEN this experiment's comparison window starts.")
        print("It does not change any configuration -- decide/scan/size continue to use their own current settings unchanged.")
        return

    if args.experiment_command == "end":
        experiment = store.get_experiment(args.experiment_id)
        if experiment is None:
            store.close()
            print(f"experiment: no experiment found with id {args.experiment_id} in {db_path}.", file=sys.stderr)
            sys.exit(1)
        if store.is_ended(args.experiment_id):
            store.close()
            print(f"experiment: {args.experiment_id} is already ended.", file=sys.stderr)
            sys.exit(1)

        store.save_event(ExperimentEvent(
            event_id=ExperimentEvent.new_id(), experiment_id=args.experiment_id,
            event_type=ExperimentEventType.ENDED, occurred_at=datetime.now(timezone.utc), detail=args.note or "",
        ))
        store.close()
        print(f"Experiment {args.experiment_id} ({experiment.name!r}) ended.")
        return

    if args.experiment_command == "list":
        experiments = store.list_experiments(limit=args.limit)
        rows = [(e, store.is_ended(e.experiment_id)) for e in experiments]
        store.close()

        print("=" * 70)
        print("EXPERIMENTS -- READ-ONLY REGISTRY")
        print("=" * 70)
        print(f"Database: {db_path}\n")
        if not rows:
            print("No experiments registered yet -- run `experiment start` first.")
        for experiment, ended in rows:
            status = "ENDED" if ended else "ONGOING"
            print(f"{experiment.experiment_id[:12]}  {status:8s} {experiment.config_type.value:16s} {experiment.name}")
            print(f"             config_version={experiment.config_version}  started={experiment.started_at.isoformat()}")
        return

    if args.experiment_command == "compare":
        from pathlib import Path

        from decision_engine.store import DecisionStore
        from experiments.comparison import compare_experiments
        from learning.analysis import EvaluatedPrediction
        from predictions.store import PredictionStore

        experiments = store.list_experiments(limit=args.limit)

        predictions_db = args.predictions_db or DEFAULT_PREDICTIONS_DB_PATH
        decision_db = args.decision_db or DEFAULT_DECISION_DB_PATH
        items: list[EvaluatedPrediction] = []
        if Path(predictions_db).exists():
            prediction_store = PredictionStore(predictions_db)
            decision_store = DecisionStore(decision_db) if Path(decision_db).exists() else None
            for prediction in prediction_store.list_predictions():
                evaluation = prediction_store.latest_evaluation_for_prediction(prediction.prediction_id)
                if evaluation is None:
                    continue
                decision = decision_store.get_decision(prediction.decision_id) if decision_store is not None else None
                items.append(EvaluatedPrediction(prediction=prediction, evaluation=evaluation, decision=decision))
            prediction_store.close()
            if decision_store is not None:
                decision_store.close()

        comparisons = compare_experiments(experiments, items, store)
        store.close()

        print("=" * 70)
        print("EXPERIMENT COMPARISON -- each experiment's OWN dataset/time boundary, not lifetime aggregates")
        print("=" * 70)
        if not comparisons:
            print("No experiments registered yet -- run `experiment start` first.")
        for c in comparisons:
            window_end = c.ended_at.isoformat() if c.ended_at is not None else "ongoing"
            print(f"\n{c.experiment.name} ({c.experiment.experiment_id[:12]})")
            print(f"  Config version: {c.experiment.config_version}")
            print(f"  Window:         {c.experiment.started_at.isoformat()} -> {window_end}")
            print(f"  Total:          {c.total}   Resolved: {c.resolved}")
            print(f"  Win rate:       {_fmt_pct(c.win_rate) if c.win_rate is not None else 'n/a'}")
            print(f"  Avg return:     {_fmt_pct(c.average_return) if c.average_return is not None else 'n/a'}")
            print(f"  Profit factor:  {_fmt_ratio(c.profit_factor) if c.profit_factor is not None else 'n/a'}")
        return

    if args.experiment_command == "recommend":
        from pathlib import Path

        from decision_engine.store import DecisionStore
        from experiments.comparison import compare_experiments
        from learning.adaptation import compare_and_recommend
        from learning.analysis import EvaluatedPrediction
        from predictions.store import PredictionStore

        baseline_experiment = store.get_experiment(args.baseline_id)
        candidate_experiment = store.get_experiment(args.candidate_id)
        if baseline_experiment is None:
            store.close()
            print(f"experiment recommend: no experiment found with id {args.baseline_id} in {db_path}.", file=sys.stderr)
            sys.exit(1)
        if candidate_experiment is None:
            store.close()
            print(f"experiment recommend: no experiment found with id {args.candidate_id} in {db_path}.", file=sys.stderr)
            sys.exit(1)

        predictions_db = args.predictions_db or DEFAULT_PREDICTIONS_DB_PATH
        decision_db = args.decision_db or DEFAULT_DECISION_DB_PATH
        items: list[EvaluatedPrediction] = []
        if Path(predictions_db).exists():
            prediction_store = PredictionStore(predictions_db)
            decision_store = DecisionStore(decision_db) if Path(decision_db).exists() else None
            for prediction in prediction_store.list_predictions():
                evaluation = prediction_store.latest_evaluation_for_prediction(prediction.prediction_id)
                if evaluation is None:
                    continue
                decision = decision_store.get_decision(prediction.decision_id) if decision_store is not None else None
                items.append(EvaluatedPrediction(prediction=prediction, evaluation=evaluation, decision=decision))
            prediction_store.close()
            if decision_store is not None:
                decision_store.close()

        comparisons = compare_experiments([baseline_experiment, candidate_experiment], items, store)
        store.close()
        by_id = {c.experiment.experiment_id: c for c in comparisons}
        recommendation = compare_and_recommend(baseline=by_id[args.baseline_id], candidate=by_id[args.candidate_id])

        print("=" * 70)
        print("PROMOTION RECOMMENDATION -- ADVISORY ONLY, NO CONFIGURATION IS CHANGED")
        print("=" * 70)
        print(f"Baseline:  {baseline_experiment.name} ({baseline_experiment.experiment_id[:12]})")
        print(f"Candidate: {candidate_experiment.name} ({candidate_experiment.experiment_id[:12]})")
        print(f"\nVerdict: {recommendation.verdict.value}\n")
        for line in recommendation.reasoning:
            print(f"  - {line}")
        print("\nThis command never edits any configuration file. Promotion, if desired, remains a manual step:")
        print("edit the relevant config's own source, then run `experiment start` again to track the promoted version.")
        return


# --------------------------------------------------------------------------
# `shadow-run` -- Phase 27 end-to-end shadow trading validation: ONE pass
# through the full pipeline (scan -> research -> decide -> predict ->
# evaluate -> learn) for a configured watchlist. This is orchestration
# only -- every step calls the exact same library function its own
# standalone CLI command already uses (market_intelligence.scanner.
# run_scan, research.summarizer.build_research_report, decision_engine.
# engine.make_decision, risk.sizing.build_signal_for_buy, predictions.
# tracker.create_prediction/evaluate_prediction/summarize_predictions,
# learning.analysis.build_learning_report) -- nothing here reimplements
# any of that logic.
#
# HONEST LIMITATION, stated here and in the Phase 27 report: the
# roadmap's own Phase 27 acceptance criterion is to run this "for
# sufficient time before considering higher-risk functionality" --
# that is real-world elapsed time this command cannot fabricate by
# running once. This command is the INFRASTRUCTURE that makes that
# validation possible (e.g. via a scheduler running it periodically);
# it does not itself constitute "sufficient time" evidence.
#
# One symbol's failure never aborts the whole run -- matches
# market_intelligence.scanner's own per-symbol fail-independently
# posture. Still no order, real or paper: no code path here imports
# paper/ or a broker adapter for anything other than an OPTIONAL,
# read-only open-position lookup (--paper-db), identical to `decide`'s
# own existing use of it.
# --------------------------------------------------------------------------


def run_shadow_run_command(args: argparse.Namespace) -> None:
    from pathlib import Path

    from critic.models import CriticVerdict
    from decision_engine.engine import make_decision
    from decision_engine.models import RiskContext
    from decision_engine.store import DecisionStore
    from market.context import get_market_context
    from market_data.universe import MarketUniverse
    from market_intelligence.scanner import run_scan
    from market_intelligence.store import ScanHistoryStore
    from predictions.errors import PredictionUnavailableError
    from predictions.store import PredictionStore
    from predictions.tracker import create_prediction, evaluate_prediction, summarize_predictions
    from research.news import YahooNewsProvider
    from research.sector import YahooSectorInfoProvider
    from research.store import ResearchStore
    from research.summarizer import build_research_report
    from risk.sizing import SizingUnavailableError, build_signal_for_buy

    if args.watchlist_file:
        universe = MarketUniverse.from_yaml_file(args.watchlist_file)
    elif args.symbols:
        symbols = [s for s in args.symbols.split(",") if s.strip()]
        universe = MarketUniverse.from_watchlist(symbols)
    else:
        print("shadow-run: one of --symbols or --watchlist-file is required.", file=sys.stderr)
        sys.exit(2)

    if args.paper_execute and (args.initial_capital is None or not args.paper_db or not args.state_db):
        print(
            "shadow-run: --paper-execute requires --initial-capital, --paper-db, AND --state-db all to be given "
            "(the kill switch must be checkable before any paper order is submitted).",
            file=sys.stderr,
        )
        sys.exit(2)

    paper_engine = None
    paper_engine_store = None
    state_store = None
    if args.paper_execute:
        from live.state_store import LiveStateStore
        from paper.engine import PaperTradingEngine
        from paper.store import PaperStore
        from risk.engine import RiskEngine

        paper_engine_store = PaperStore(args.paper_db)
        paper_engine = PaperTradingEngine(
            paper_engine_store, risk_engine=RiskEngine(_risk_config_from_args(args)),
            initial_capital=args.initial_capital, max_holding_bars=args.max_holding_bars,
        )
        state_store = LiveStateStore(args.state_db)

    provider, resilient = _build_provider(args)
    benchmark_symbol = args.benchmark or None
    live_snapshot_provider = _build_live_snapshot_provider(args)

    print("=" * 70)
    print("SHADOW RUN -- FULL PIPELINE, ONE PASS -- NOT AN ORDER (no real or paper trade is placed)")
    print("=" * 70)
    from live.dhan.market_session import current_market_session

    session = current_market_session()
    print(f"Market session:  {session.state.value} (as of {session.as_of_ist.strftime('%H:%M:%S IST')}, does not account for exchange holidays)")
    print(f"Live overlay:    {'DHAN (--live-source dhan)' if live_snapshot_provider is not None else 'none -- Yahoo historical only'}")

    logger.info("shadow-run: scanning %d symbols", len(universe))
    scan_report = run_scan(
        universe, provider=provider, benchmark_symbol=benchmark_symbol, period=args.period, interval=args.interval,
    )
    scanner_db = args.scanner_db or DEFAULT_SCANNER_DB_PATH
    scan_store = ScanHistoryStore(scanner_db)
    scan_store.save_report(scan_report)
    scan_store.close()
    print(f"\n[1/4] Scan complete: {len(scan_report.candidates)} candidates, {len(scan_report.excluded)} excluded (scan_id={scan_report.scan_id}).")

    decision_db = args.decision_db or DEFAULT_DECISION_DB_PATH
    research_db = args.research_db or DEFAULT_RESEARCH_DB_PATH
    predictions_db = args.predictions_db or DEFAULT_PREDICTIONS_DB_PATH

    decision_store = DecisionStore(decision_db)
    research_store = ResearchStore(research_db)
    prediction_store = PredictionStore(predictions_db)
    news_provider = YahooNewsProvider()
    sector_provider = YahooSectorInfoProvider()

    predictions_recorded = 0
    paper_orders_submitted = 0
    decisions_by_label: dict[str, int] = {}
    critic_verdicts: dict[str, int] = {}

    print(f"\n[2/4] Research + decide + predict for {len(scan_report.candidates)} candidate(s):")
    for candidate in scan_report.candidates:
        symbol = candidate.symbol
        try:
            research_report = build_research_report(
                symbol, news_provider=news_provider, sector_provider=sector_provider,
                candidate_explanation=candidate.explanation, include_ai_summary=args.with_ai, news_limit=args.news_limit,
            )
            research_store.save_report(research_report)

            risk_context = RiskContext.unknown()
            if args.paper_db:
                from paper.store import PaperStore

                paper_store = PaperStore(args.paper_db)
                open_position = paper_store.get_open_position(symbol)
                account = paper_store.get_account()
                risk_context = RiskContext(
                    has_open_position=open_position is not None,
                    consecutive_losses=account.consecutive_losses if account is not None else 0,
                    note=f"Derived from paper account state at {args.paper_db}.",
                )
                paper_store.close()

            market_context = get_market_context(symbol, period=args.period, interval=args.interval, live_snapshot_provider=live_snapshot_provider)
            decision = make_decision(
                symbol, candidate=candidate, research=research_report, market_context=market_context,
                risk_context=risk_context, include_narrative=args.with_ai,
            )
            decision_store.save_decision(decision)
            decisions_by_label[decision.label.value] = decisions_by_label.get(decision.label.value, 0) + 1

            prediction_note = ""
            if decision.label.value == "BUY":
                try:
                    # Phase 36: duplicate prevention -- see run_predict_command's identical check.
                    if prediction_store.has_prediction_for_entry(symbol, market_context.as_of):
                        prediction_note = f" -> no prediction recorded (already have one for entry bar {market_context.as_of.isoformat()})"
                    else:
                        signal = build_signal_for_buy(decision, market_context)

                        critic_assessment = None
                        if not args.skip_critic:
                            from critic.engine import evaluate as critic_evaluate

                            existing_pending = paper_engine.store.get_pending_order(symbol) is not None if paper_engine is not None else False
                            existing_open = paper_engine.store.get_open_position(symbol) is not None if paper_engine is not None else False
                            kill_switch_active = state_store.is_kill_switch_active() if state_store is not None else None
                            critic_assessment = critic_evaluate(
                                decision, signal, kill_switch_active=kill_switch_active,
                                existing_pending_order=existing_pending, existing_open_position=existing_open,
                            )
                            critic_verdicts[critic_assessment.verdict.value] = critic_verdicts.get(critic_assessment.verdict.value, 0) + 1

                        risk_decision = _size_if_requested(decision, market_context=market_context, args=args)
                        prediction = create_prediction(
                            decision, signal, horizon_bars=args.horizon_bars, interval=args.interval,
                            risk_decision=risk_decision, critic_assessment=critic_assessment,
                        )
                        prediction_store.save_prediction(prediction)
                        predictions_recorded += 1
                        sized_note = f", qty={risk_decision.position_size.quantity}" if (risk_decision is not None and risk_decision.position_size is not None) else ""
                        critic_note = f", critic={critic_assessment.verdict.value}" if critic_assessment is not None else ""
                        prediction_note = f" -> prediction recorded ({prediction.prediction_id[:12]}{sized_note}{critic_note})"
                        if args.paper_execute:
                            critic_blocks_execution = critic_assessment is not None and critic_assessment.verdict in (CriticVerdict.REJECT, CriticVerdict.INSUFFICIENT_EVIDENCE)
                            if critic_blocks_execution:
                                paper_outcome = f"SKIPPED (critic {critic_assessment.verdict.value})"
                            else:
                                paper_outcome = _bridge_to_paper_execution(signal, risk_decision, engine=paper_engine, state_store=state_store)
                            if paper_outcome is not None:
                                prediction_note += f" | paper: {paper_outcome}"
                                if paper_outcome == "APPROVED_PENDING":
                                    paper_orders_submitted += 1
                except (SizingUnavailableError, PredictionUnavailableError) as exc:
                    prediction_note = f" -> no prediction recorded ({exc})"

            print(f"  {symbol:12s} composite={candidate.composite_score:+.2f}  decision={decision.label.value:10s}{prediction_note}")
        except Exception as exc:  # noqa: BLE001 -- one symbol's failure must never abort the whole shadow run
            logger.warning("shadow-run: %s failed, continuing with the rest of the universe: %s", symbol, exc)
            print(f"  {symbol:12s} FAILED: {exc}")

    research_store.close()
    decision_store.close()

    paper_orders_advanced = 0
    if paper_engine is not None:
        from paper.advance import advance_pending_paper_orders

        advance_results = advance_pending_paper_orders(paper_engine, provider=provider, period=args.period, interval=args.interval)
        paper_orders_advanced = sum(1 for r in advance_results if r.bars_processed > 0)
        if advance_results:
            print("\nAdvancing existing PENDING paper orders / OPEN positions with fresh data:")
            for r in advance_results:
                if r.error is not None:
                    print(f"  {r.symbol:12s} FAILED: {r.error}")
                elif r.skipped_reason is not None:
                    print(f"  {r.symbol:12s} skipped: {r.skipped_reason}")
                elif r.bars_processed > 0:
                    print(f"  {r.symbol:12s} {r.bars_processed} new bar(s) processed -> {r.last_outcome}")
                else:
                    print(f"  {r.symbol:12s} no new data yet")

    if paper_engine_store is not None:
        paper_engine_store.close()
    if state_store is not None:
        state_store.close()

    if live_snapshot_provider is not None:
        live_snapshot_provider.close()

    if args.skip_evaluate:
        prediction_store.close()
        print("\n[3/4] Evaluation skipped (--skip-evaluate).")
        print("[4/4] Learning summary skipped (--skip-evaluate).")
        _print_shadow_run_footer(scan_report, decisions_by_label, predictions_recorded, paper_orders_submitted, paper_orders_advanced, critic_verdicts)
        _print_provider_metrics(resilient)
        return

    print("\n[3/4] Evaluating all outstanding predictions:")
    pending = prediction_store.list_predictions_needing_evaluation()
    print(f"  {len(pending)} prediction(s) needing evaluation.")
    for prediction in pending:
        try:
            evaluation = evaluate_prediction(prediction, provider=provider, period=args.period)
            prediction_store.save_evaluation(evaluation)
            print(f"  {prediction.symbol:10s} {prediction.prediction_id[:12]}  {evaluation.outcome.value:18s} {evaluation.detail}")
        except Exception as exc:  # noqa: BLE001 -- one prediction's failure must never abort evaluation of the rest of the batch or skip the learning summary below, same posture as this run's own per-symbol scan/decide isolation above.
            logger.warning("shadow-run: evaluating %s (%s) failed, continuing with the rest of the batch: %s", prediction.symbol, prediction.prediction_id, exc)
            print(f"  {prediction.symbol:10s} {prediction.prediction_id[:12]}  FAILED               {exc}")

    summary = summarize_predictions(prediction_store.list_all_evaluations())
    prediction_store.close()

    print("\n[4/4] Learning summary (latest evaluation per prediction):")
    print(f"  Total:             {summary.total_predictions}")
    print(f"  Active:            {summary.active}")
    print(f"  Target hit:        {summary.target_hit}")
    print(f"  Stop hit:          {summary.stop_hit}")
    print(f"  Expired:           {summary.expired}")
    print(f"  Insufficient data: {summary.insufficient_data}")
    print(f"  Win rate:          {_fmt_pct(summary.win_rate)}")
    print(f"  Average return:    {_fmt_pct(summary.average_return)}")

    _print_shadow_run_footer(scan_report, decisions_by_label, predictions_recorded, paper_orders_submitted, paper_orders_advanced)
    _print_provider_metrics(resilient)


def _print_shadow_run_footer(
    scan_report, decisions_by_label: dict[str, int], predictions_recorded: int,
    paper_orders_submitted: int = 0, paper_orders_advanced: int = 0,
    critic_verdicts: dict[str, int] | None = None,
) -> None:
    label_summary = ", ".join(f"{label}={count}" for label, count in sorted(decisions_by_label.items())) or "(none)"
    paper_note = f"; paper orders submitted: {paper_orders_submitted}" if paper_orders_submitted else ""
    print(f"\nRun summary: {len(scan_report.candidates)} candidate(s) scanned; decisions: {label_summary}; predictions recorded: {predictions_recorded}{paper_note}.")
    if critic_verdicts:
        # Audit-trail completeness: an operator seeing 0 paper orders
        # submitted (or fewer than expected) has no way to tell "the
        # critic blocked them" from "risk rejected them" from "nothing
        # was even a BUY" without this line -- found via self-audit of
        # the footer's own existing accounting (it already aggregates
        # decisions_by_label the same way; critic verdicts were
        # computed and printed per-symbol but never rolled up here).
        critic_summary = ", ".join(f"{verdict}={count}" for verdict, count in sorted(critic_verdicts.items()))
        print(f"Critic verdicts: {critic_summary}.")
    if paper_orders_submitted or paper_orders_advanced:
        # Deliberately does NOT claim a specific resulting status (e.g. "still
        # PENDING") -- the advance step run earlier in THIS SAME invocation may
        # already have filled and even closed an order using genuinely later
        # data (see paper/advance.py) -- run `python main.py paper status` for
        # the actual current state, never assumed here.
        parts = []
        if paper_orders_submitted:
            parts.append(f"{paper_orders_submitted} new order(s) submitted this run")
        if paper_orders_advanced:
            parts.append(f"{paper_orders_advanced} existing order/position(s) advanced with new data this run")
        print(f"REAL PAPER order activity (--paper-execute): {', '.join(parts)}. Run `python main.py paper status` for current state.")
        print("No real order was placed by this command, and no real broker was ever contacted for execution.")
    else:
        print("No real or paper order was placed by this command.")
    print("This is ONE pass, not 'sufficient time' -- run `shadow-run` again later (e.g. on a schedule) to accumulate real validation evidence over time.")


# --------------------------------------------------------------------------
# `review` -- Phase 25 AI Multi-Agent Market Research: an independent,
# adversarial second opinion on the latest persisted Decision. Requires
# Ollama (unlike `decide`'s optional narrative, there is no meaningful
# evidence-only fallback for a command whose entire purpose is the AI
# critique) -- fails clearly via check_ollama_availability if unavailable,
# same posture as the `analyze` command. NOT an order; agents/
# decision_reviewer.py cannot change the label, only critique it.
# --------------------------------------------------------------------------


def run_review_command(args: argparse.Namespace) -> None:
    from pathlib import Path

    from decision_engine.store import DecisionStore
    from llm.provider import check_ollama_availability

    normalized = args.symbol.strip().upper()

    decision_db = args.decision_db or DEFAULT_DECISION_DB_PATH
    decision = None
    if Path(decision_db).exists():
        store = DecisionStore(decision_db)
        decision = store.latest_decision_for_symbol(normalized)
        store.close()

    if decision is None:
        print(f"review: no decision found for {normalized} in {decision_db} -- run `decide --symbol {normalized}` first.", file=sys.stderr)
        sys.exit(1)

    check_ollama_availability()

    from agents.decision_reviewer import review_decision

    logger.info("Requesting an independent review of the %s decision for %s", decision.label.value, normalized)
    review = review_decision(decision)

    print("=" * 70)
    print("INDEPENDENT DECISION REVIEW -- AI CRITIQUE ONLY, CANNOT CHANGE THE LABEL")
    print("=" * 70)
    print(f"Symbol:  {decision.symbol}")
    print(f"Label:   {decision.label.value} (decision_id={decision.decision_id})")

    print("\nSupporting points:")
    if not review.supporting_points:
        print("  (none)")
    for point in review.supporting_points:
        print(f"  + {point}")

    print("\nConcerns:")
    if not review.concerns:
        print("  (none)")
    for concern in review.concerns:
        print(f"  - {concern}")

    print(f"\nOverall: {review.overall_assessment}")


# --------------------------------------------------------------------------
# `universe` -- Phase 29 production market universe: prints each symbol's
# derived exchange (NSE/BSE/OTHER, from the Yahoo suffix convention) and,
# optionally, its Dhan broker instrument identifier (via the existing,
# credential-free DhanInstrumentMap.download() -- read-only metadata,
# not a live feed). No trading logic, no recommendation, no order.
# --------------------------------------------------------------------------


def run_universe_command(args: argparse.Namespace) -> None:
    from market_data.universe import MarketUniverse

    if args.watchlist_file:
        universe = MarketUniverse.from_yaml_file(args.watchlist_file)
    elif args.symbols:
        symbols = [s for s in args.symbols.split(",") if s.strip()]
        universe = MarketUniverse.from_watchlist(symbols)
    else:
        print("universe: one of --symbols or --watchlist-file is required.", file=sys.stderr)
        sys.exit(2)

    instrument_map = None
    if args.with_dhan_ids:
        from live.dhan.instruments import DhanInstrumentMap

        logger.info("Downloading Dhan's public instrument master (no credentials required)")
        instrument_map = DhanInstrumentMap.download(force=args.refresh_instrument_map)

    metadata = universe.describe(instrument_map=instrument_map)

    print("=" * 70)
    print("MARKET UNIVERSE -- SYMBOL / EXCHANGE / INSTRUMENT METADATA (no trading logic)")
    print("=" * 70)
    print(f"Universe:  {universe.mode} ({len(universe)} symbols)")
    if args.with_dhan_ids:
        print("Dhan IDs:  resolved via Dhan's public instrument master (no credentials used).")
    print()
    print(f"{'SYMBOL':14s} {'EXCHANGE':8s} {'DHAN SECURITY ID':18s} DHAN DISPLAY NAME")
    for item in metadata:
        if item.dhan_security_id is not None:
            security_id = item.dhan_security_id
        else:
            security_id = "n/a" if not args.with_dhan_ids else "not found"
        print(f"{item.symbol:14s} {item.exchange:8s} {security_id:18s} {item.dhan_display_name or ''}")


# --------------------------------------------------------------------------
# `schedule` -- Phase 28 operational scheduling: makes `shadow-run` (and
# post-market evaluate/learn) capable of running unattended, without
# reimplementing any of that orchestration -- see scheduler/runner.py's
# module docstring. `tick` performs at most ONE check-and-maybe-execute
# cycle and exits; `loop` is the explicit, opt-in continuous mode (never
# the default -- "no infinite loop by default CLI accident" per the
# roadmap). `status` is a read-only audit view over scheduler_runs.db.
# --------------------------------------------------------------------------

DEFAULT_SCHEDULER_DB_PATH = PROJECT_ROOT / "data" / "scheduler_runs.db"


def _load_schedule_config(args: argparse.Namespace):
    from scheduler.config import ScheduleConfig

    if args.config:
        return ScheduleConfig.from_yaml_file(args.config)
    return ScheduleConfig()


def _print_tick_result(result) -> None:
    marker = "RAN" if result.ran else "SKIPPED"
    print(f"[{marker}] {result.reason}")
    if result.reclaimed_run_ids:
        ids = ", ".join(r[:12] for r in result.reclaimed_run_ids)
        print(f"  Reclaimed {len(result.reclaimed_run_ids)} stale lock(s) from a prior crashed/killed run: {ids}")


def _run_tick_from_args(args: argparse.Namespace, schedule_config, store, *, now: datetime | None = None):
    from scheduler.runner import run_tick

    return run_tick(
        schedule_config=schedule_config, run_store=store, symbols=args.symbols, watchlist_file=args.watchlist_file,
        period=args.period, interval=args.interval, benchmark=args.benchmark, news_limit=args.news_limit,
        horizon_bars=args.horizon_bars, paper_db=args.paper_db, with_ai=args.with_ai, resilient=args.resilient,
        live_source=args.live_source, scanner_db=args.scanner_db, research_db=args.research_db,
        decision_db=args.decision_db, predictions_db=args.predictions_db, initial_capital=args.initial_capital,
        paper_execute=args.paper_execute, state_db=args.state_db, max_holding_bars=args.max_holding_bars,
        skip_critic=args.skip_critic, staleness_seconds=args.staleness_seconds, now=now,
    )


def run_schedule_command(args: argparse.Namespace) -> None:
    from scheduler.store import SchedulerRunStore

    run_db_path = args.run_db or DEFAULT_SCHEDULER_DB_PATH

    if args.schedule_command == "status":
        store = SchedulerRunStore(run_db_path)
        runs = store.list_runs(limit=args.limit)
        integrity_result = None
        db_size = None
        if args.check_integrity:
            integrity_result = store.integrity_check()
            db_size = store.db_size_bytes()
        store.close()

        print("=" * 70)
        print("SCHEDULER RUN HISTORY -- READ-ONLY AUDIT")
        print("=" * 70)
        print(f"Database: {run_db_path}\n")
        if args.check_integrity:
            size_kb = db_size / 1024.0
            print(f"Integrity check: {integrity_result}   (file size: {size_kb:.1f} KB)\n")
        if not runs:
            print("No scheduler runs recorded yet -- run `schedule tick` or `schedule loop` first.")
        for run in runs:
            finished = run.finished_at.isoformat() if run.finished_at else "(in progress)"
            print(f"{run.started_at.isoformat()}  {run.slot_name:12s} {run.status.value:10s} finished={finished:32s} {run.detail}")
        return

    schedule_config = _load_schedule_config(args)

    if getattr(args, "log_file", None):
        from core.logging import add_rotating_file_handler

        add_rotating_file_handler(args.log_file)
        logger.info("schedule: file logging enabled at %s (rotating, 10MB x 5 backups)", args.log_file)

    if args.schedule_command == "tick":
        now = datetime.fromisoformat(args.now) if args.now else None
        store = SchedulerRunStore(run_db_path)
        try:
            result = _run_tick_from_args(args, schedule_config, store, now=now)
        finally:
            store.close()
        print("=" * 70)
        print("SCHEDULER TICK -- AT MOST ONE SLOT EXECUTED, THEN EXITS")
        print("=" * 70)
        if args.paper_execute:
            print(f"--paper-execute is ON: a shadow_run slot WILL submit real PENDING paper orders and advance existing ones against database {args.paper_db}.")
        _print_tick_result(result)
        return

    if args.schedule_command == "loop":
        store = SchedulerRunStore(run_db_path)
        print("=" * 70)
        print("SCHEDULER LOOP -- CONTINUOUS, EXPLICIT MODE (Ctrl+C to stop cleanly)")
        print("=" * 70)
        print(f"Polling every {args.interval_seconds:.0f}s. Database: {run_db_path}")
        print("No real broker order is EVER placed by this command (structurally impossible -- no order-placement code path exists anywhere in this project).")
        if args.paper_execute:
            print(f"--paper-execute is ON: shadow_run slots WILL submit real PENDING paper orders and advance existing ones against database {args.paper_db}. Run `python main.py paper status` to see current state.")
        else:
            print("No paper order is placed either -- --paper-execute was not given (shadow_run slots only record shadow predictions).")

        ticks = 0
        tick_failures = 0
        try:
            while args.max_ticks is None or ticks < args.max_ticks:
                try:
                    result = _run_tick_from_args(args, schedule_config, store)
                    _print_tick_result(result)
                except KeyboardInterrupt:
                    raise
                except Exception as exc:  # noqa: BLE001 -- an unexpected TICK-LEVEL failure (e.g. a transient SQLite lock error from another process, or a bug in schedule_config.due_slot) must never kill a long-lived, unattended loop. run_tick already isolates ordinary operational failures (a bad symbol, a provider outage) into a FAILED RunRecord; this is the outer safety net for everything run_tick itself cannot catch.
                    tick_failures += 1
                    logger.exception("schedule loop: tick failed unexpectedly (tick_failures=%d) -- continuing to the next tick.", tick_failures)
                    print(f"\n[SCHEDULER] Tick failed unexpectedly: {type(exc).__name__}: {exc}. Continuing (tick_failures={tick_failures}).")
                ticks += 1
                if args.max_ticks is None or ticks < args.max_ticks:
                    time.sleep(args.interval_seconds)
        except KeyboardInterrupt:
            print("\n[SCHEDULER] Interrupted by user (Ctrl+C) -- shutting down cleanly. No new tick will start.")
        finally:
            store.close()
        print(f"\n[SCHEDULER] Loop stopped after {ticks} tick(s){f', {tick_failures} unexpected tick failure(s)' if tick_failures else ''}.")
        return


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    argv = list(sys.argv[1:] if argv is None else argv)

    # Backward compatibility: `python main.py --symbol AAPL` (Phase 1/2's
    # only interface, no subcommand) keeps working exactly as before by
    # defaulting to the `analyze` subcommand.
    if not argv or (argv[0] not in _KNOWN_COMMANDS and argv[0] not in ("-h", "--help")):
        argv = ["analyze", *argv]

    parser = argparse.ArgumentParser(
        description="AI-assisted market analysis and deterministic strategy backtesting.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    analyze_parser = subparsers.add_parser(
        "analyze",
        help="Run the AI multi-agent market analysis (default). Requires Ollama.",
    )
    analyze_parser.add_argument(
        "--symbol",
        required=True,
        help="Ticker to analyze, as understood by Yahoo Finance (e.g. AAPL, RELIANCE.NS, ^NSEI).",
    )
    analyze_parser.add_argument(
        "--question",
        default=None,
        help="Question to pose to the analysts. Defaults to a generic strategy review.",
    )

    backtest_parser = subparsers.add_parser(
        "backtest",
        help="Run the deterministic strategy backtest. No LLM, no live network dependency beyond data fetch.",
    )
    backtest_parser.add_argument(
        "--symbol",
        required=True,
        help="Ticker to backtest, as understood by Yahoo Finance (e.g. AAPL, RELIANCE.NS).",
    )
    backtest_parser.add_argument(
        "--period",
        default="5y",
        help="Historical window to fetch, Yahoo Finance format (default: 5y).",
    )
    backtest_parser.add_argument(
        "--interval",
        default="1d",
        help="Bar interval (default: 1d).",
    )
    backtest_parser.add_argument(
        "--initial-capital",
        type=float,
        default=100_000.0,
        help="Starting capital for the simulated account (default: 100000).",
    )
    backtest_parser.add_argument(
        "--strategy",
        default="trend_momentum_baseline",
        help="Registered strategy name (default: trend_momentum_baseline).",
    )
    default_risk = RiskConfig()

    def _add_optional_sizing_args(parser: argparse.ArgumentParser) -> None:
        """Autonomous-validation mission requirement (auditability):
        `predict`/`shadow-run` can OPTIONALLY size against real capital/
        risk config at prediction time -- when --initial-capital is
        passed, the resulting risk.contracts.RiskDecision (quantity,
        capital, risk amount -- the actual "trade plan") is persisted on
        the PredictionRecord itself, not just printed and lost. Omitting
        --initial-capital keeps prior behavior byte-for-byte (no sizing
        computed, risk_decision stays None) -- this is purely additive.
        Same flag names/defaults as `size`/`backtest` for consistency,
        factored out here since three commands now need them."""
        parser.add_argument("--initial-capital", type=float, default=None, help="Capital to size against (default: not sized -- the prediction is recorded without a persisted trade plan, exactly like before this flag existed).")
        parser.add_argument("--risk-per-trade", type=float, default=default_risk.risk_per_trade_pct, help=f"Percent of equity risked per trade (default: {default_risk.risk_per_trade_pct}). Only used when --initial-capital is passed.")
        parser.add_argument("--max-daily-loss", type=float, default=default_risk.max_daily_loss_pct, help=f"Percent daily-loss halt threshold (default: {default_risk.max_daily_loss_pct}). Only used when --initial-capital is passed.")
        parser.add_argument("--max-drawdown", type=float, default=default_risk.max_drawdown_pct, help=f"Percent max-drawdown halt threshold (default: {default_risk.max_drawdown_pct}). Only used when --initial-capital is passed.")
        parser.add_argument("--max-exposure", type=float, default=default_risk.max_exposure_pct, help=f"Percent max position-notional/equity exposure (default: {default_risk.max_exposure_pct}). Only used when --initial-capital is passed.")
        parser.add_argument("--max-consecutive-losses", type=int, default=default_risk.max_consecutive_losses, help=f"Losing-streak threshold that triggers reduced-risk sizing (default: {default_risk.max_consecutive_losses}). Only used when --initial-capital is passed.")
        parser.add_argument("--consecutive-loss-risk-multiplier", type=float, default=default_risk.consecutive_loss_risk_multiplier, help=f"Risk-per-trade multiplier while in a loss-streak recovery (default: {default_risk.consecutive_loss_risk_multiplier}). Only used when --initial-capital is passed.")
        parser.add_argument("--consecutive-loss-hard-limit", type=int, default=default_risk.consecutive_loss_hard_limit, help=f"Losing-streak threshold that rejects outright (default: {default_risk.consecutive_loss_hard_limit}). Only used when --initial-capital is passed.")
        parser.add_argument("--min-risk-reward", type=float, default=default_risk.min_risk_reward, help=f"Minimum acceptable signal risk/reward (default: {default_risk.min_risk_reward}). Only used when --initial-capital is passed.")

    backtest_parser.add_argument(
        "--risk-per-trade",
        type=float,
        default=default_risk.risk_per_trade_pct,
        help=f"Percent of equity risked per trade (default: {default_risk.risk_per_trade_pct}).",
    )
    backtest_parser.add_argument(
        "--max-daily-loss",
        type=float,
        default=default_risk.max_daily_loss_pct,
        help=f"Percent daily-loss halt threshold (default: {default_risk.max_daily_loss_pct}).",
    )
    backtest_parser.add_argument(
        "--max-drawdown",
        type=float,
        default=default_risk.max_drawdown_pct,
        help=f"Percent max-drawdown halt threshold (default: {default_risk.max_drawdown_pct}).",
    )
    backtest_parser.add_argument(
        "--max-exposure",
        type=float,
        default=default_risk.max_exposure_pct,
        help=f"Percent max position-notional/equity exposure (default: {default_risk.max_exposure_pct}).",
    )
    backtest_parser.add_argument(
        "--max-consecutive-losses",
        type=int,
        default=default_risk.max_consecutive_losses,
        help=f"Losing-streak threshold that triggers reduced-risk sizing, not a reject (default: {default_risk.max_consecutive_losses}).",
    )
    backtest_parser.add_argument(
        "--consecutive-loss-risk-multiplier",
        type=float,
        default=default_risk.consecutive_loss_risk_multiplier,
        help=f"Risk-per-trade multiplier while in a loss-streak recovery (default: {default_risk.consecutive_loss_risk_multiplier}).",
    )
    backtest_parser.add_argument(
        "--consecutive-loss-hard-limit",
        type=int,
        default=default_risk.consecutive_loss_hard_limit,
        help=(
            f"Losing-streak threshold that DOES reject outright (default: "
            f"{default_risk.consecutive_loss_hard_limit}). Set equal to "
            f"--max-consecutive-losses for Phase 4's original immediate-reject behavior."
        ),
    )
    backtest_parser.add_argument(
        "--min-risk-reward",
        type=float,
        default=default_risk.min_risk_reward,
        help=f"Minimum acceptable signal risk/reward (default: {default_risk.min_risk_reward}).",
    )

    paper_parser = subparsers.add_parser(
        "paper",
        help="Deterministic paper trading + journal (Phase 6). No LLM, no broker, no live orders.",
    )
    paper_parser.add_argument(
        "--db",
        type=str,
        default=None,
        help=f"SQLite journal path (default: {DEFAULT_PAPER_DB_PATH}).",
    )
    paper_parser.add_argument(
        "--initial-capital",
        type=float,
        default=100_000.0,
        help=(
            "Simulated starting capital (default: 100000). Only takes effect the FIRST time this "
            "database is used -- an existing account's capital is never reset by this flag on a later run "
            "(restart-safe, same posture as every other persisted store in this project)."
        ),
    )
    paper_subparsers = paper_parser.add_subparsers(dest="paper_command", required=True)

    paper_subparsers.add_parser("status", help="Show account state, open positions, and reconciliation status.")

    paper_run_parser = paper_subparsers.add_parser("run", help="Replay a symbol's cached history through the paper engine.")
    paper_run_parser.add_argument("--symbol", required=True, help="Ticker to replay (e.g. AAPL, RELIANCE.NS).")
    paper_run_parser.add_argument("--period", default="5y", help="Historical window to fetch (default: 5y).")
    paper_run_parser.add_argument("--interval", default="1d", help="Bar interval (default: 1d).")
    paper_run_parser.add_argument("--strategy", default="trend_momentum_baseline", help="Registered strategy name.")

    paper_subparsers.add_parser("trades", help="List all completed paper trades.")
    paper_subparsers.add_parser("journal", help="List all journal entries (approved, rejected, filled, closed).")

    live_sim_parser = subparsers.add_parser(
        "live-sim",
        help=(
            "Phase 12: replay cached history bar-by-bar through a SIMULATED live pipeline "
            "(MockMarketDataSource -> Strategy -> RiskEngine -> PaperTradingEngine). "
            "NOT connected to any real broker or live feed; places no real orders."
        ),
    )
    live_sim_parser.add_argument("--symbol", required=True, help="Ticker to replay (e.g. AAPL, RELIANCE.NS).")
    live_sim_parser.add_argument("--interval", default="1m", help="Bar interval: 1m, 5m, 15m, 1d, etc. (default: 1m).")
    live_sim_parser.add_argument("--period", default="5d", help="Historical window to fetch for the mock feed (default: 5d).")
    live_sim_parser.add_argument("--strategy", default="trend_momentum_baseline", help="Registered strategy name.")
    live_sim_parser.add_argument("--db", type=str, default=None, help=f"SQLite journal path (default: {DEFAULT_LIVE_SIM_DB_PATH}).")
    live_sim_parser.add_argument("--max-bars", type=int, default=None, help="Stop after this many bars (default: run to feed exhaustion).")
    live_sim_parser.add_argument("--freshness-multiplier", type=float, default=2.0, help="Freshness threshold = multiplier x interval duration (default: 2.0).")
    live_sim_parser.add_argument("--require-human-approval", action="store_true", help="Stop each approved signal at PENDING_HUMAN_APPROVAL instead of auto-executing in paper (default: off).")
    live_sim_parser.add_argument(
        "--initial-capital", type=float, default=100_000.0,
        help="Simulated starting capital (default: 100000). Only takes effect the first time this database is used.",
    )

    paper_live_parser = subparsers.add_parser(
        "paper-live",
        help=(
            "Phase 13: human-operated intraday workstation. Same simulated pipeline as "
            "live-sim, but every approved signal stops for an interactive human "
            "APPROVE/REJECT decision, with a persistent local kill switch and a "
            "second, independent risk check at the moment of approval. "
            "NOT connected to any real broker or live feed; places no real orders."
        ),
    )
    paper_live_parser.add_argument("--symbol", help="Ticker to replay (e.g. AAPL, RELIANCE.NS). Required unless using --kill-switch/--reset-kill-switch.")
    paper_live_parser.add_argument("--interval", default="1m", help="Bar interval: 1m, 5m, 15m, 1d, etc. (default: 1m).")
    paper_live_parser.add_argument("--period", default="1d", help="Historical window to fetch for the mock feed (default: 1d). Ignored when --source dhan.")
    paper_live_parser.add_argument(
        "--source", choices=["mock", "dhan"], default="mock",
        help=(
            "Market data source (default: mock). 'dhan' connects to a REAL Dhan WebSocket feed "
            "(requires DHAN_CLIENT_ID/DHAN_ACCESS_TOKEN env vars) -- execution is ALWAYS paper "
            "regardless of this setting; no real order can be placed through this command."
        ),
    )
    paper_live_parser.add_argument("--refresh-instrument-map", action="store_true", help="Force a fresh download of Dhan's instrument master CSV instead of reusing the local cache. Only used with --source dhan.")
    paper_live_parser.add_argument("--strategy", default="trend_momentum_baseline", help="Registered strategy name.")
    paper_live_parser.add_argument("--db", type=str, default=None, help=f"SQLite paper-trading journal path (default: {DEFAULT_LIVE_SIM_DB_PATH}).")
    paper_live_parser.add_argument("--state-db", type=str, default=None, help=f"SQLite pending-approval/kill-switch state path (default: {DEFAULT_LIVE_STATE_DB_PATH}).")
    paper_live_parser.add_argument("--max-bars", type=int, default=None, help="Stop after this many bars (default: run to feed exhaustion).")
    paper_live_parser.add_argument("--freshness-multiplier", type=float, default=2.0, help="Freshness threshold = multiplier x interval duration (default: 2.0).")
    paper_live_parser.add_argument("--no-human-approval", action="store_true", help="Auto-execute approved signals instead of stopping for human approval (default: human approval required).")
    paper_live_parser.add_argument("--approval-timeout-seconds", type=float, default=None, help="Pending approvals expire (APPROVAL_EXPIRED) after this many seconds (default: 120s; pass 0 or a negative value is rejected -- use a large number to effectively disable).")
    paper_live_parser.add_argument("--no-ai-explanation", action="store_true", help="Skip the optional AI explanation step (default: attempt it, never blocking if Ollama is unavailable).")
    paper_live_parser.add_argument("--auto-approve", action="store_true", help="Automatically answer APPROVE to every pending signal instead of prompting (for scripted/non-interactive runs).")
    paper_live_parser.add_argument("--auto-reject", action="store_true", help="Automatically answer REJECT to every pending signal instead of prompting (for scripted/non-interactive runs).")
    paper_live_parser.add_argument("--kill-switch", action="store_true", help="Activate the local kill switch (blocks all new pending approvals/executions) and exit. Does not touch existing positions.")
    paper_live_parser.add_argument("--kill-switch-reason", type=str, default=None, help="Free-text reason recorded with --kill-switch.")
    paper_live_parser.add_argument("--reset-kill-switch", action="store_true", help="Explicitly clear a previously activated kill switch and exit.")
    paper_live_parser.add_argument(
        "--initial-capital", type=float, default=100_000.0,
        help="Simulated starting capital (default: 100000). Only takes effect the first time this database is used.",
    )

    dashboard_parser = subparsers.add_parser(
        "dashboard",
        help=(
            "Phase 13: minimal local web dashboard for the paper-live workstation "
            "(MARKET/SIGNALS/PENDING APPROVAL/POSITIONS/ACCOUNT/RISK/JOURNAL). "
            "Reads/acts on the same state the paper-live CLI writes to; does not "
            "advance the market itself. Local-only; NOT connected to any real broker."
        ),
    )
    dashboard_parser.add_argument("--host", default="127.0.0.1", help="Bind address (default: 127.0.0.1, local-only).")
    dashboard_parser.add_argument("--port", type=int, default=8765, help="Bind port (default: 8765).")

    universe_parser = subparsers.add_parser(
        "universe",
        help=(
            "Phase 29: describe a watchlist's symbol/exchange/instrument metadata "
            "(NSE/BSE/OTHER, optional Dhan security ID). No trading logic, no recommendation."
        ),
    )
    universe_parser.add_argument("--symbols", type=str, default=None, help="Comma-separated watchlist (e.g. AAPL,MSFT,RELIANCE.NS). Required unless --watchlist-file is given.")
    universe_parser.add_argument("--watchlist-file", type=str, default=None, help="Path to a YAML file with a top-level `market_universe: {mode: watchlist, symbols: [...]}` key (e.g. market_data/watchlists/starter_nse.yaml).")
    universe_parser.add_argument("--with-dhan-ids", action="store_true", help="Also resolve each symbol's Dhan security ID via Dhan's public instrument master (one network download, no credentials required; default off).")
    universe_parser.add_argument("--refresh-instrument-map", action="store_true", help="Force a fresh download of Dhan's instrument master instead of reusing the local cache. Only used with --with-dhan-ids.")

    scan_parser = subparsers.add_parser(
        "scan",
        help=(
            "Phase 19: market scanner -- rank a configured watchlist by trend/momentum/"
            "breakout/relative strength. No AI, no recommendation, no buy/sell/quantity/price level."
        ),
    )
    scan_parser.add_argument("--symbols", type=str, default=None, help="Comma-separated watchlist (e.g. AAPL,MSFT,RELIANCE.NS). Required unless --watchlist-file is given.")
    scan_parser.add_argument("--watchlist-file", type=str, default=None, help="Path to a YAML file with a top-level `market_universe: {mode: watchlist, symbols: [...]}` key.")
    scan_parser.add_argument("--period", default="1y", help="Historical window to fetch per symbol (default: 1y).")
    scan_parser.add_argument("--interval", default="1d", help="Bar interval (default: 1d).")
    scan_parser.add_argument("--benchmark", default="^NSEI", help="Benchmark symbol for relative strength (default: ^NSEI). Pass an empty string to disable.")
    scan_parser.add_argument("--db", type=str, default=None, help=f"SQLite scan-history path (default: {DEFAULT_SCANNER_DB_PATH}).")
    scan_parser.add_argument("--top", type=int, default=10, help="Print only the top N ranked candidates (default: 10).")
    scan_parser.add_argument("--resilient", action="store_true", help="Phase 30: wrap the market-data provider with timeout/retry-with-backoff/circuit-breaker/rate-limit protection for a large watchlist (default: off, matches prior behavior exactly). Prints a provider-metrics summary at the end.")

    regime_parser = subparsers.add_parser(
        "regime",
        help=(
            "Phase 33: market breadth (from the latest scan) + benchmark trend/volatility regime "
            "(one fresh fetch) + optional sector strength. Explainable aggregates only -- no AI, no recommendation."
        ),
    )
    regime_parser.add_argument("--scanner-db", type=str, default=None, help=f"Read the latest scan from this path (default: {DEFAULT_SCANNER_DB_PATH}).")
    regime_parser.add_argument("--benchmark", type=str, default=None, help="Benchmark symbol to classify (default: whatever the latest scan itself used).")
    regime_parser.add_argument("--period", default="2y", help="Historical window for the benchmark's own trend/volatility classification (default: 2y -- SMA200 needs enough warm-up history).")
    regime_parser.add_argument("--interval", default="1d", help="Bar interval (default: 1d).")
    regime_parser.add_argument("--with-sectors", action="store_true", help="Also build a sector-strength ranking (one extra Yahoo fetch per scanned symbol -- default off).")
    regime_parser.add_argument("--resilient", action="store_true", help="Phase 30: wrap the market-data provider with timeout/retry-with-backoff/circuit-breaker protection (default: off).")

    research_parser = subparsers.add_parser(
        "research",
        help=(
            "Phase 20: real Yahoo Finance news + sector classification for one symbol, plus an "
            "optional AI summary (narration only). No recommendation, no buy/sell/quantity/price level."
        ),
    )
    research_parser.add_argument("--symbol", required=True, help="Ticker to research (e.g. AAPL, RELIANCE.NS).")
    research_parser.add_argument("--news-limit", type=int, default=10, help="Max news items to fetch (default: 10).")
    research_parser.add_argument("--no-ai-summary", action="store_true", help="Skip the optional AI summary step (default: attempt it, never blocking if Ollama is unavailable).")
    research_parser.add_argument("--db", type=str, default=None, help=f"SQLite research-history path (default: {DEFAULT_RESEARCH_DB_PATH}).")

    decide_parser = subparsers.add_parser(
        "decide",
        help=(
            "Phase 21: combine the latest persisted scanner + research evidence into a "
            "BUY/WATCH/AVOID/EXIT/NO_ACTION label, with an optional AI narrative. NOT an order -- "
            "places no trade; converting a label into a paper trade remains a separate, manual step."
        ),
    )
    decide_parser.add_argument("--symbol", required=True, help="Ticker to decide on (e.g. AAPL, RELIANCE.NS).")
    decide_parser.add_argument("--scanner-db", type=str, default=None, help=f"Read the latest scan from this path (default: {DEFAULT_SCANNER_DB_PATH}).")
    decide_parser.add_argument("--research-db", type=str, default=None, help=f"Read the latest research report from this path (default: {DEFAULT_RESEARCH_DB_PATH}).")
    decide_parser.add_argument("--paper-db", type=str, default=None, help="Optional: check this paper-trading database for an existing open position, to distinguish BUY/WATCH from EXIT.")
    decide_parser.add_argument("--no-narrative", action="store_true", help="Skip the optional AI narrative step (default: attempt it, never blocking if Ollama is unavailable).")
    decide_parser.add_argument("--db", type=str, default=None, help=f"SQLite decision-history path (default: {DEFAULT_DECISION_DB_PATH}).")

    size_parser = subparsers.add_parser(
        "size",
        help=(
            "Phase 22: preview how the EXISTING, UNCHANGED risk engine would size the latest BUY decision "
            "for a symbol, given the specified capital. NOT an order -- places no real or paper trade."
        ),
    )
    size_parser.add_argument("--symbol", required=True, help="Ticker to size (e.g. AAPL, RELIANCE.NS).")
    size_parser.add_argument("--decision-db", type=str, default=None, help=f"Read the latest decision from this path (default: {DEFAULT_DECISION_DB_PATH}).")
    size_parser.add_argument("--period", default="6mo", help="Historical window to fetch for the current market context (default: 6mo).")
    size_parser.add_argument("--interval", default="1d", help="Bar interval (default: 1d).")
    size_parser.add_argument("--initial-capital", type=float, default=100_000.0, help="Capital to size against (default: 100000).")
    size_parser.add_argument("--risk-per-trade", type=float, default=default_risk.risk_per_trade_pct, help=f"Percent of equity risked per trade (default: {default_risk.risk_per_trade_pct}).")
    size_parser.add_argument("--max-daily-loss", type=float, default=default_risk.max_daily_loss_pct, help=f"Percent daily-loss halt threshold (default: {default_risk.max_daily_loss_pct}).")
    size_parser.add_argument("--max-drawdown", type=float, default=default_risk.max_drawdown_pct, help=f"Percent max-drawdown halt threshold (default: {default_risk.max_drawdown_pct}).")
    size_parser.add_argument("--max-exposure", type=float, default=default_risk.max_exposure_pct, help=f"Percent max position-notional/equity exposure (default: {default_risk.max_exposure_pct}).")
    size_parser.add_argument("--max-consecutive-losses", type=int, default=default_risk.max_consecutive_losses, help=f"Losing-streak threshold that triggers reduced-risk sizing, not a reject (default: {default_risk.max_consecutive_losses}).")
    size_parser.add_argument("--consecutive-loss-risk-multiplier", type=float, default=default_risk.consecutive_loss_risk_multiplier, help=f"Risk-per-trade multiplier while in a loss-streak recovery (default: {default_risk.consecutive_loss_risk_multiplier}).")
    size_parser.add_argument("--consecutive-loss-hard-limit", type=int, default=default_risk.consecutive_loss_hard_limit, help=f"Losing-streak threshold that DOES reject outright (default: {default_risk.consecutive_loss_hard_limit}).")
    size_parser.add_argument("--min-risk-reward", type=float, default=default_risk.min_risk_reward, help=f"Minimum acceptable signal risk/reward (default: {default_risk.min_risk_reward}).")
    size_parser.add_argument("--live-source", choices=["dhan"], default=None, help="Phase 31: overlay the current price with a real Dhan live quote (requires DHAN_CLIENT_ID/DHAN_ACCESS_TOKEN) instead of the Yahoo historical close. Indicators are still computed from Yahoo history either way. A failed/unhealthy live source silently falls back to the Yahoo historical price.")

    predict_parser = subparsers.add_parser(
        "predict",
        help=(
            "Phase 23: record a shadow prediction from the latest BUY decision for a symbol -- tracked "
            "for later outcome evaluation whether or not you trade it. NOT an order."
        ),
    )
    predict_parser.add_argument("--symbol", required=True, help="Ticker to predict on (e.g. AAPL, RELIANCE.NS).")
    predict_parser.add_argument("--decision-db", type=str, default=None, help=f"Read the latest decision from this path (default: {DEFAULT_DECISION_DB_PATH}).")
    predict_parser.add_argument("--period", default="6mo", help="Historical window to fetch for the current market context (default: 6mo).")
    predict_parser.add_argument("--interval", default="1d", help="Bar interval, also used for later evaluation (default: 1d).")
    predict_parser.add_argument("--horizon-bars", type=int, default=20, help="Bars after entry before an unresolved prediction is marked EXPIRED (default: 20).")
    predict_parser.add_argument("--db", type=str, default=None, help=f"SQLite prediction-history path (default: {DEFAULT_PREDICTIONS_DB_PATH}).")
    predict_parser.add_argument("--live-source", choices=["dhan"], default=None, help="Phase 31: overlay the entry price with a real Dhan live quote (requires DHAN_CLIENT_ID/DHAN_ACCESS_TOKEN) instead of the Yahoo historical close. A failed/unhealthy live source silently falls back to the Yahoo historical price.")
    _add_optional_sizing_args(predict_parser)

    evaluate_parser = subparsers.add_parser(
        "evaluate",
        help=(
            "Phase 23: check real subsequent market data against every open shadow prediction "
            "(TARGET_HIT/STOP_HIT/EXPIRED/ACTIVE), and print a win-rate/return/profit-factor summary."
        ),
    )
    evaluate_parser.add_argument("--db", type=str, default=None, help=f"SQLite prediction-history path (default: {DEFAULT_PREDICTIONS_DB_PATH}).")
    evaluate_parser.add_argument("--period", default="1y", help="Historical window to fetch per symbol when checking for a resolution (default: 1y).")
    evaluate_parser.add_argument("--resilient", action="store_true", help="Phase 30: wrap the market-data provider with timeout/retry-with-backoff/circuit-breaker protection when evaluating many predictions (default: off).")

    learn_parser = subparsers.add_parser(
        "learn",
        help=(
            "Phase 24: READ-ONLY performance analysis over evaluated predictions -- strategy comparison, market "
            "regime performance, confidence calibration, signal quality. Changes no configuration, places no order."
        ),
    )
    learn_parser.add_argument("--predictions-db", type=str, default=None, help=f"SQLite prediction-history path (default: {DEFAULT_PREDICTIONS_DB_PATH}).")
    learn_parser.add_argument("--decision-db", type=str, default=None, help=f"SQLite decision-history path, for strategy/calibration grouping (default: {DEFAULT_DECISION_DB_PATH}).")
    learn_parser.add_argument("--resilient", action="store_true", help="Phase 30: wrap the market-data provider with timeout/retry-with-backoff/circuit-breaker protection for regime-performance lookups (default: off).")

    experiment_parser = subparsers.add_parser(
        "experiment",
        help=(
            "Phase 37: register/track named experiments over decision_engine/scanner/risk config versions -- "
            "a dataset/time-boundary comparison, not a lifetime aggregate. Never changes any configuration."
        ),
    )
    experiment_subparsers = experiment_parser.add_subparsers(dest="experiment_command", required=True)

    experiment_start_parser = experiment_subparsers.add_parser("start", help="Register a new experiment -- records the CURRENT default config's version_id for --config-type and starts its comparison window now.")
    experiment_start_parser.add_argument("--name", required=True, help="Short, human-readable experiment name.")
    experiment_start_parser.add_argument("--config-type", choices=["decision_engine", "scanner", "risk"], required=True, help="Which existing, unmodified versioned config this experiment tracks.")
    experiment_start_parser.add_argument("--description", type=str, default=None, help="Free-text: what is being tried and why.")
    experiment_start_parser.add_argument("--db", type=str, default=None, help=f"SQLite experiment-registry path (default: {DEFAULT_EXPERIMENTS_DB_PATH}).")

    experiment_end_parser = experiment_subparsers.add_parser("end", help="Mark an experiment ended -- closes its comparison window now. Never rewrites the original registration, only appends an ENDED event.")
    experiment_end_parser.add_argument("--experiment-id", required=True, help="The experiment_id printed by `experiment start`/`experiment list`.")
    experiment_end_parser.add_argument("--note", type=str, default=None, help="Free-text: why this experiment is ending / what was observed.")
    experiment_end_parser.add_argument("--db", type=str, default=None, help=f"SQLite experiment-registry path (default: {DEFAULT_EXPERIMENTS_DB_PATH}).")

    experiment_list_parser = experiment_subparsers.add_parser("list", help="Read-only: list every registered experiment and its derived status (ONGOING/ENDED).")
    experiment_list_parser.add_argument("--db", type=str, default=None, help=f"SQLite experiment-registry path (default: {DEFAULT_EXPERIMENTS_DB_PATH}).")
    experiment_list_parser.add_argument("--limit", type=int, default=50, help="Max experiments to list, most recent first (default: 50).")

    experiment_compare_parser = experiment_subparsers.add_parser("compare", help="Read-only: win rate/avg return/profit factor for every registered experiment, computed ONLY over predictions within its own dataset/time boundary.")
    experiment_compare_parser.add_argument("--db", type=str, default=None, help=f"SQLite experiment-registry path (default: {DEFAULT_EXPERIMENTS_DB_PATH}).")
    experiment_compare_parser.add_argument("--predictions-db", type=str, default=None, help=f"SQLite prediction-history path (default: {DEFAULT_PREDICTIONS_DB_PATH}).")
    experiment_compare_parser.add_argument("--decision-db", type=str, default=None, help=f"SQLite decision-history path (default: {DEFAULT_DECISION_DB_PATH}).")
    experiment_compare_parser.add_argument("--limit", type=int, default=50, help="Max experiments to compare (default: 50).")

    experiment_recommend_parser = experiment_subparsers.add_parser(
        "recommend",
        help=(
            "Phase 38: read-only promotion RECOMMENDATION between two already-registered experiments -- "
            "never changes any configuration. See learning.adaptation for the fixed evidence thresholds."
        ),
    )
    experiment_recommend_parser.add_argument("--baseline-id", required=True, help="experiment_id of the baseline (current/reference) experiment.")
    experiment_recommend_parser.add_argument("--candidate-id", required=True, help="experiment_id of the candidate (deliberately changed) experiment.")
    experiment_recommend_parser.add_argument("--db", type=str, default=None, help=f"SQLite experiment-registry path (default: {DEFAULT_EXPERIMENTS_DB_PATH}).")
    experiment_recommend_parser.add_argument("--predictions-db", type=str, default=None, help=f"SQLite prediction-history path (default: {DEFAULT_PREDICTIONS_DB_PATH}).")
    experiment_recommend_parser.add_argument("--decision-db", type=str, default=None, help=f"SQLite decision-history path (default: {DEFAULT_DECISION_DB_PATH}).")

    review_parser = subparsers.add_parser(
        "review",
        help=(
            "Phase 25: an independent, adversarial AI second opinion on the latest decision for a symbol. "
            "Requires Ollama. Cannot change the label -- narration/critique only, not an order."
        ),
    )
    review_parser.add_argument("--symbol", required=True, help="Ticker to review (e.g. AAPL, RELIANCE.NS).")
    review_parser.add_argument("--decision-db", type=str, default=None, help=f"Read the latest decision from this path (default: {DEFAULT_DECISION_DB_PATH}).")

    shadow_run_parser = subparsers.add_parser(
        "shadow-run",
        help=(
            "Phase 27: one full pass through scan -> research -> decide -> predict -> evaluate -> learn for a "
            "watchlist. Orchestration only -- reuses each stage's own existing function. NOT an order; places no trade."
        ),
    )
    shadow_run_parser.add_argument("--symbols", type=str, default=None, help="Comma-separated watchlist (e.g. AAPL,MSFT,RELIANCE.NS). Required unless --watchlist-file is given.")
    shadow_run_parser.add_argument("--watchlist-file", type=str, default=None, help="Path to a YAML file with a top-level `market_universe: {mode: watchlist, symbols: [...]}` key.")
    shadow_run_parser.add_argument("--period", default="1y", help="Historical window used for scanning, market context, and evaluation (default: 1y).")
    shadow_run_parser.add_argument("--interval", default="1d", help="Bar interval (default: 1d).")
    shadow_run_parser.add_argument("--benchmark", default="^NSEI", help="Benchmark symbol for scanner relative strength (default: ^NSEI). Pass an empty string to disable.")
    shadow_run_parser.add_argument("--news-limit", type=int, default=10, help="Max news items to fetch per symbol (default: 10).")
    shadow_run_parser.add_argument("--horizon-bars", type=int, default=20, help="Bars after entry before an unresolved prediction is marked EXPIRED (default: 20).")
    shadow_run_parser.add_argument("--paper-db", type=str, default=None, help="Optional: check this paper-trading database for an existing open position per symbol, to distinguish BUY/WATCH from EXIT.")
    shadow_run_parser.add_argument("--with-ai", action="store_true", help="Include the optional AI research summary and decision narrative for every symbol (default: off, to avoid an LLM call per symbol in a bulk run).")
    shadow_run_parser.add_argument("--skip-evaluate", action="store_true", help="Stop after recording predictions -- skip the evaluate/learn tail (default: run the full pipeline through learning).")
    shadow_run_parser.add_argument("--scanner-db", type=str, default=None, help=f"SQLite scan-history path (default: {DEFAULT_SCANNER_DB_PATH}).")
    shadow_run_parser.add_argument("--research-db", type=str, default=None, help=f"SQLite research-history path (default: {DEFAULT_RESEARCH_DB_PATH}).")
    shadow_run_parser.add_argument("--decision-db", type=str, default=None, help=f"SQLite decision-history path (default: {DEFAULT_DECISION_DB_PATH}).")
    shadow_run_parser.add_argument("--predictions-db", type=str, default=None, help=f"SQLite prediction-history path (default: {DEFAULT_PREDICTIONS_DB_PATH}).")
    shadow_run_parser.add_argument("--resilient", action="store_true", help="Phase 30: wrap the market-data provider with timeout/retry-with-backoff/circuit-breaker/rate-limit protection across the whole run (default: off, matches prior behavior exactly). Prints a provider-metrics summary at the end.")
    shadow_run_parser.add_argument("--live-source", choices=["dhan"], default=None, help="Phase 32: overlay every candidate's price with a real Dhan live quote (requires DHAN_CLIENT_ID/DHAN_ACCESS_TOKEN) instead of the Yahoo historical close. One adapter is built for the whole run and closed at the end. A failed/unhealthy live source silently falls back to the Yahoo historical price per symbol.")
    _add_optional_sizing_args(shadow_run_parser)
    shadow_run_parser.add_argument(
        "--paper-execute", action="store_true",
        help=(
            "Explicit opt-in: bridge each risk-approved BUY into a REAL paper.engine.PaperTradingEngine order via "
            "the SAME idempotent submit_signal() `paper`/`paper-live` already use (default: off -- shadow-run only "
            "ever records a shadow prediction, exactly as before this flag existed). Requires --initial-capital, "
            "--paper-db, and --state-db all given, and is refused with a clear error otherwise. HONEST SCOPE: this "
            "creates a PENDING order, not an immediately open position -- PaperTradingEngine's own execution model "
            "fills a PENDING order at the NEXT bar's open, which by definition does not exist yet at decision time; "
            "advancing/filling it against a genuinely later bar is a separate mechanism this flag does not attempt. "
            "The kill switch (--state-db) is checked before every submission; an active kill switch skips paper "
            "execution for that symbol without affecting the shadow prediction itself."
        ),
    )
    shadow_run_parser.add_argument("--state-db", type=str, default=None, help=f"SQLite kill-switch/pending-approval state path (default: {DEFAULT_LIVE_STATE_DB_PATH}). Required when --paper-execute is passed.")
    shadow_run_parser.add_argument(
        "--max-holding-bars", type=int, default=None,
        help=(
            "Explicit opt-in, default None (unlimited hold -- same behavior as before this flag existed): force-close "
            "a PENDING order's eventual OPEN position after this many bars if neither its stop nor target has been hit "
            "yet, at that bar's close (ExitReason.EXPIRED). Only takes effect once the order actually fills; only "
            "meaningful together with --paper-execute. Mirrors --horizon-bars, which does the same thing for an "
            "unresolved shadow PREDICTION -- this is the equivalent for a real paper POSITION."
        ),
    )
    shadow_run_parser.add_argument(
        "--skip-critic", action="store_true",
        help=(
            "Explicit opt-OUT, default off: the deterministic critic (critic.engine.evaluate) runs by default for "
            "every BUY once this flag is not passed -- it independently re-examines the proposed trade (data "
            "freshness, trade structure, duplicate exposure, kill switch, indicator contradictions, regime, "
            "risk/reward, evidence completeness) and its verdict is persisted on the prediction. A REJECT or "
            "INSUFFICIENT_EVIDENCE verdict prevents --paper-execute from submitting a real paper order for that "
            "symbol this run -- the shadow prediction itself is still recorded regardless, exactly like a rejected "
            "risk_decision already is. Pass --skip-critic to preserve the exact prior behavior (no critic call at "
            "all, no verdict persisted, --paper-execute unaffected by anything but risk/kill-switch as before)."
        ),
    )

    schedule_parser = subparsers.add_parser(
        "schedule",
        help=(
            "Phase 28: run shadow-run (and post-market evaluate/learn) on a configurable schedule, unattended. "
            "`tick` runs at most one due slot and exits; `loop` is explicit continuous mode; `status` audits run history."
        ),
    )
    schedule_subparsers = schedule_parser.add_subparsers(dest="schedule_command", required=True)

    def _add_schedule_common_args(p: argparse.ArgumentParser) -> None:
        p.add_argument("--symbols", type=str, default=None, help="Comma-separated watchlist (e.g. AAPL,MSFT,RELIANCE.NS). Required (or --watchlist-file) for any shadow_run slot to be able to execute.")
        p.add_argument("--watchlist-file", type=str, default=None, help="Path to a YAML file with a top-level `market_universe: {mode: watchlist, symbols: [...]}` key.")
        p.add_argument("--config", type=str, default=None, help="Path to a YAML schedule-definition file (slots + holidays). Default: the built-in pre_market/market_open/intraday/pre_close/post_market schedule.")
        p.add_argument("--period", default="1y", help="Historical window used for scanning, market context, and evaluation (default: 1y).")
        p.add_argument("--interval", default="1d", help="Bar interval (default: 1d).")
        p.add_argument("--benchmark", default="^NSEI", help="Benchmark symbol for scanner relative strength (default: ^NSEI). Pass an empty string to disable.")
        p.add_argument("--news-limit", type=int, default=10, help="Max news items to fetch per symbol (default: 10).")
        p.add_argument("--horizon-bars", type=int, default=20, help="Bars after entry before an unresolved prediction is marked EXPIRED (default: 20).")
        p.add_argument("--paper-db", type=str, default=None, help="Optional: check this paper-trading database for an existing open position per symbol, to distinguish BUY/WATCH from EXIT.")
        p.add_argument("--with-ai", action="store_true", help="Include the optional AI research summary and decision narrative for every symbol (default: off).")
        p.add_argument("--resilient", action="store_true", help="Phase 30: wrap the market-data provider with timeout/retry-with-backoff/circuit-breaker/rate-limit protection for every tick (default: off, recommended for unattended `schedule loop` operation).")
        p.add_argument("--live-source", choices=["dhan"], default=None, help="Phase 32: overlay every candidate's price with a real Dhan live quote on shadow_run slots (requires DHAN_CLIENT_ID/DHAN_ACCESS_TOKEN). Ignored for evaluate_and_learn slots.")
        p.add_argument("--scanner-db", type=str, default=None, help=f"SQLite scan-history path (default: {DEFAULT_SCANNER_DB_PATH}).")
        p.add_argument("--research-db", type=str, default=None, help=f"SQLite research-history path (default: {DEFAULT_RESEARCH_DB_PATH}).")
        p.add_argument("--decision-db", type=str, default=None, help=f"SQLite decision-history path (default: {DEFAULT_DECISION_DB_PATH}).")
        p.add_argument("--predictions-db", type=str, default=None, help=f"SQLite prediction-history path (default: {DEFAULT_PREDICTIONS_DB_PATH}).")
        p.add_argument("--initial-capital", type=float, default=None, help="Capital to size each BUY prediction against on shadow_run slots (default: not sized -- predictions are recorded without a persisted trade plan, matching `shadow-run`'s own default). Ignored for evaluate_and_learn slots.")
        p.add_argument("--run-db", type=str, default=None, help=f"SQLite scheduler-run-history path (default: {DEFAULT_SCHEDULER_DB_PATH}).")
        p.add_argument("--staleness-seconds", type=float, default=1800.0, help="A RUNNING lock older than this with no completion is treated as an orphaned/crashed run and reclaimed (default: 1800 = 30 minutes).")
        p.add_argument("--log-file", type=str, default=None, help="Phase 39: also write logs to this path via a size-bounded, rotating file handler (default: 10MB x 5 backups) -- console output is unchanged either way. Recommended for `schedule loop` run unattended for days.")
        p.add_argument(
            "--paper-execute", action="store_true",
            help=(
                "Explicit opt-in, default OFF: forward --paper-execute to every shadow_run slot this scheduler runs, "
                "so unattended ticks also submit real PENDING paper orders AND advance existing ones with fresh data "
                "(the same paper/advance.py mechanism `shadow-run --paper-execute` itself uses -- not a second "
                "execution path). Without this flag, `schedule tick`/`schedule loop` only ever records shadow "
                "predictions, exactly as before this flag existed. Requires --initial-capital, --paper-db, and "
                "--state-db all given, same as `shadow-run --paper-execute` -- refused with a clear error otherwise."
            ),
        )
        p.add_argument("--state-db", type=str, default=None, help=f"SQLite kill-switch/pending-approval state path (default: {DEFAULT_LIVE_STATE_DB_PATH}). Required when --paper-execute is passed.")
        p.add_argument(
            "--max-holding-bars", type=int, default=None,
            help=(
                "Forwarded to every shadow_run slot's `shadow-run --max-holding-bars` -- force-close a filled paper "
                "position after this many bars if neither stop nor target has been hit (default: None, unlimited "
                "hold). Only meaningful together with --paper-execute."
            ),
        )
        p.add_argument(
            "--skip-critic", action="store_true",
            help="Forwarded to every shadow_run slot's `shadow-run --skip-critic` (default off -- the deterministic critic runs by default).",
        )

    tick_parser = schedule_subparsers.add_parser("tick", help="Check whether a configured slot is due right now; if so, run it exactly once, then exit. Never loops.")
    _add_schedule_common_args(tick_parser)
    tick_parser.add_argument("--now", type=str, default=None, help="ISO 8601 datetime to evaluate against instead of the real current time (for a dry-run / 'what would run at 09:20 IST' check, and for deterministic tests).")

    loop_parser = schedule_subparsers.add_parser("loop", help="Explicit continuous mode: poll and tick repeatedly until Ctrl+C (or --max-ticks is reached). Never the default -- must be requested explicitly.")
    _add_schedule_common_args(loop_parser)
    loop_parser.add_argument("--interval-seconds", type=float, default=60.0, help="Seconds to sleep between ticks (default: 60).")
    loop_parser.add_argument("--max-ticks", type=int, default=None, help="Stop after this many ticks (default: run until Ctrl+C).")

    status_parser = schedule_subparsers.add_parser("status", help="Read-only: print recent scheduler run history (audit trail).")
    status_parser.add_argument("--run-db", type=str, default=None, help=f"SQLite scheduler-run-history path (default: {DEFAULT_SCHEDULER_DB_PATH}).")
    status_parser.add_argument("--limit", type=int, default=20, help="Max runs to print, most recent first (default: 20).")
    status_parser.add_argument("--check-integrity", action="store_true", help="Phase 39: also run a read-only `PRAGMA integrity_check` and print the database file size -- useful after long unattended `schedule loop` operation.")

    return parser.parse_args(argv)


def main() -> None:
    setup_logging()
    args = parse_args()

    try:
        if args.command == "backtest":
            run_backtest_command(args)
        elif args.command == "paper":
            run_paper_command(args)
        elif args.command == "live-sim":
            run_live_sim_command(args)
        elif args.command == "paper-live":
            if not args.symbol and not (args.kill_switch or args.reset_kill_switch):
                print("paper-live: --symbol is required unless using --kill-switch/--reset-kill-switch.", file=sys.stderr)
                sys.exit(2)
            run_paper_live_command(args)
        elif args.command == "dashboard":
            run_dashboard_command(args)
        elif args.command == "scan":
            run_scan_command(args)
        elif args.command == "research":
            run_research_command(args)
        elif args.command == "decide":
            run_decide_command(args)
        elif args.command == "size":
            run_size_command(args)
        elif args.command == "predict":
            run_predict_command(args)
        elif args.command == "evaluate":
            run_evaluate_command(args)
        elif args.command == "learn":
            run_learn_command(args)
        elif args.command == "review":
            run_review_command(args)
        elif args.command == "shadow-run":
            run_shadow_run_command(args)
        elif args.command == "schedule":
            run_schedule_command(args)
        elif args.command == "universe":
            run_universe_command(args)
        elif args.command == "regime":
            run_regime_command(args)
        elif args.command == "experiment":
            run_experiment_command(args)
        else:
            run_analyze_command(args)
    except _CONTROLLED_ERRORS as exc:
        print(f"\n{args.command.capitalize()} failed: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
