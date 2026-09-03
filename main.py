import argparse
import logging
import sys
import time

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
from rag.errors import RagStoreNotFoundError
from risk.config import RiskConfig
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

_KNOWN_COMMANDS = ("analyze", "backtest", "paper", "live-sim", "paper-live", "dashboard", "scan", "research", "decide")

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
    engine = PaperTradingEngine(store)

    if args.paper_command == "status":
        account = engine.account
        open_positions = [p for p in store.list_positions() if p.status.value == "OPEN"]
        journal = store.list_journal_entries()
        trades = store.list_trades()
        print("=" * 50)
        print("PAPER TRADING STATUS")
        print("=" * 50)
        print(f"\nDatabase: {db_path}")
        print(f"\nEquity:              {account.equity:,.2f}")
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
    engine = PaperTradingEngine(store)
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
    engine = PaperTradingEngine(store)
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


def run_scan_command(args: argparse.Namespace) -> None:
    from backtesting.cache import CachedMarketDataProvider
    from market.data_provider import get_market_data_provider
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

    provider = CachedMarketDataProvider(get_market_data_provider())
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
        else:
            run_analyze_command(args)
    except _CONTROLLED_ERRORS as exc:
        print(f"\n{args.command.capitalize()} failed: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
