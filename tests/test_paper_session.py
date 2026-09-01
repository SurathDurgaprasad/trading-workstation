"""Phase 7A §3/§5: PaperSession's start/process/inspect/stop/resume lifecycle,
and the restart-vs-uninterrupted guarantee via PaperSession specifically
(tests/test_paper_restart.py already proves this at the
PaperTradingEngine/replay_historical level for Phase 6; this file proves the
NEW session wrapper preserves the exact same guarantee, deriving its resume
point from the persisted bar cursor instead of a caller-supplied index).
"""

import uuid
from pathlib import Path

import pytest

from backtesting.cache import CACHE_ROOT, CachedMarketDataProvider
from market.indicators import compute_indicator_series
from paper.engine import BarOutcome, PaperTradingEngine
from paper.reconciliation import reconcile
from paper.session import PaperSession
from paper.store import PaperStore
from risk.config import RiskConfig
from risk.engine import RiskEngine
from strategy.baseline import TrendMomentumBaseline
from tests.conftest import make_bar, make_indicator_series

_AAPL_CACHE = CACHE_ROOT / "AAPL" / "1d.csv"


class _NoNetworkProvider:
    def fetch_ohlcv(self, symbol, *, period="1y", interval="1d"):
        raise AssertionError(f"Real-data restart test attempted a live fetch for {symbol} — cache should have served this.")


def _volatile_series(n: int = 60):
    bars = []
    for i in range(n):
        if i % 5 == 0:
            bars.append(make_bar(close=100 + (i % 20), open=100 + (i % 20), high=102 + (i % 20), low=97 + (i % 20)))
        else:
            bars.append(make_bar(sma_20=80.0, sma_50=90.0, close=100 + (i % 20), open=100 + (i % 20), high=102 + (i % 20), low=97 + (i % 20)))
    return make_indicator_series(bars)


def _tmp_db_path(tmp_path: Path) -> Path:
    return tmp_path / f"session_test_{uuid.uuid4().hex}.db"


def test_paper_session_is_llm_free_structurally():
    """Spec §15: AI stays out of the bar-processing loop entirely."""
    import inspect

    import paper.session

    source = inspect.getsource(paper.session)
    assert "signal_explainer" not in source
    assert "agents" not in source
    assert "ollama" not in source.lower()


def test_session_must_be_started_before_processing_bars():
    store = PaperStore(":memory:")
    engine = PaperTradingEngine(store, initial_capital=100_000.0)
    session = PaperSession(engine, symbol="TEST", indicator_series=_volatile_series(5), strategy=TrendMomentumBaseline())

    with pytest.raises(RuntimeError):
        session.process_next_bar()


def test_session_processes_one_bar_at_a_time_and_reports_status():
    store = PaperStore(":memory:")
    engine = PaperTradingEngine(store, initial_capital=100_000.0)
    series = _volatile_series(10)
    session = PaperSession(engine, symbol="TEST", indicator_series=series, strategy=TrendMomentumBaseline()).start()

    status_before = session.status()
    assert status_before.next_index == 0
    assert not status_before.finished

    outcome = session.process_next_bar()
    assert outcome == BarOutcome.PROCESSED

    status_after = session.status()
    assert status_after.next_index == 1
    assert status_after.bars_processed_this_session == 1


def test_run_to_end_processes_the_whole_series_and_reconciles():
    store = PaperStore(":memory:")
    engine = PaperTradingEngine(store, initial_capital=100_000.0)
    series = _volatile_series(40)
    session = PaperSession(engine, symbol="TEST", indicator_series=series, strategy=TrendMomentumBaseline()).start()

    session.run_to_end()

    status = session.status()
    assert status.finished
    assert status.bars_processed_this_session == len(series)
    assert session.process_next_bar() is None  # exhausted -- calling again is a safe no-op

    report = reconcile(store)
    assert report.ok, report.issues


def test_session_resumes_from_the_persisted_cursor_after_a_restart(tmp_path):
    """Spec §5's exact example: bars 1-500 -> persist -> stop -> restart ->
    bars 501-1000 must match an uninterrupted run bar-for-bar in business
    terms. Here with a 60-bar series split at bar 30."""
    series = _volatile_series(60)
    risk_config = RiskConfig()

    # --- uninterrupted ---
    uninterrupted_db = _tmp_db_path(tmp_path)
    store_a = PaperStore(uninterrupted_db)
    engine_a = PaperTradingEngine(store_a, risk_engine=RiskEngine(risk_config), initial_capital=100_000.0)
    PaperSession(engine_a, symbol="TEST", indicator_series=series, strategy=TrendMomentumBaseline()).start().run_to_end()
    state_uninterrupted = _business_state(store_a)
    store_a.close()

    # --- restarted: session 1 runs the first half, "terminates"; session 2 resumes ---
    restarted_db = _tmp_db_path(tmp_path)
    midpoint = 30

    store_b1 = PaperStore(restarted_db)
    engine_b1 = PaperTradingEngine(store_b1, risk_engine=RiskEngine(risk_config), initial_capital=100_000.0)
    # The FULL series is passed even though only a prefix will be processed
    # -- see PaperSession.process_bars' docstring for why a truncated series
    # here would incorrectly trigger an end-of-data forced close.
    session_b1 = PaperSession(engine_b1, symbol="TEST", indicator_series=series, strategy=TrendMomentumBaseline()).start()
    processed = session_b1.process_bars(midpoint)
    assert processed == midpoint
    session_b1.stop()
    store_b1.close()  # simulates process termination

    store_b2 = PaperStore(restarted_db)  # fresh connection -- loads persisted state
    engine_b2 = PaperTradingEngine(store_b2, risk_engine=RiskEngine(risk_config), initial_capital=100_000.0)
    # The FULL series is handed to the resumed session -- it must derive on
    # its own, from the persisted bar cursor, that bars 0..29 are already
    # done and it should continue from index 30. No start_index is passed.
    session_b2 = PaperSession(engine_b2, symbol="TEST", indicator_series=series, strategy=TrendMomentumBaseline())
    assert session_b2.status().next_index == midpoint  # resume point derived correctly
    session_b2.start().run_to_end()
    state_restarted = _business_state(store_b2)

    assert state_restarted == state_uninterrupted, (
        f"Session-based restarted run diverged from an uninterrupted one.\n"
        f"uninterrupted={state_uninterrupted}\nrestarted={state_restarted}"
    )

    report = reconcile(store_b2)
    assert report.ok, report.issues
    store_b2.close()


@pytest.mark.skipif(not _AAPL_CACHE.exists(), reason=f"No cached AAPL data at {_AAPL_CACHE}")
def test_real_aapl_session_restart_matches_uninterrupted_replay(tmp_path):
    """Spec Phase 7A §13's named CRITICAL TEST, over real historical data
    rather than a synthetic series: process bars -> terminate -> reopen
    SQLite -> continue bars -> compare with an uninterrupted run."""
    provider = CachedMarketDataProvider(_NoNetworkProvider())
    ohlcv = provider.fetch_ohlcv("AAPL", interval="1d")
    series = compute_indicator_series(ohlcv)
    risk_config = RiskConfig()

    uninterrupted_db = _tmp_db_path(tmp_path)
    store_a = PaperStore(uninterrupted_db)
    engine_a = PaperTradingEngine(store_a, risk_engine=RiskEngine(risk_config), initial_capital=100_000.0)
    PaperSession(engine_a, symbol="AAPL", indicator_series=series, strategy=TrendMomentumBaseline()).start().run_to_end()
    state_uninterrupted = _business_state(store_a)
    store_a.close()

    restarted_db = _tmp_db_path(tmp_path)
    midpoint = len(series) // 2

    store_b1 = PaperStore(restarted_db)
    engine_b1 = PaperTradingEngine(store_b1, risk_engine=RiskEngine(risk_config), initial_capital=100_000.0)
    session_b1 = PaperSession(engine_b1, symbol="AAPL", indicator_series=series, strategy=TrendMomentumBaseline()).start()
    session_b1.process_bars(midpoint)
    session_b1.stop()
    store_b1.close()  # simulates process termination

    store_b2 = PaperStore(restarted_db)
    engine_b2 = PaperTradingEngine(store_b2, risk_engine=RiskEngine(risk_config), initial_capital=100_000.0)
    session_b2 = PaperSession(engine_b2, symbol="AAPL", indicator_series=series, strategy=TrendMomentumBaseline())
    assert session_b2.status().next_index == midpoint
    session_b2.start().run_to_end()
    state_restarted = _business_state(store_b2)

    assert state_restarted == state_uninterrupted, (
        f"Real-AAPL restarted session diverged from an uninterrupted one.\n"
        f"uninterrupted={state_uninterrupted}\nrestarted={state_restarted}"
    )
    report = reconcile(store_b2)
    assert report.ok, report.issues
    store_b2.close()

    print(f"\nAAPL session restart parity: {state_uninterrupted['trade_count']} trades, "
          f"equity {state_uninterrupted['equity']:.2f} (both uninterrupted and restarted)")


def _business_state(store: PaperStore) -> dict:
    account = store.get_account()
    trades = store.list_trades()
    journal = store.list_journal_entries()
    return {
        "equity": account.equity,
        "cash": account.cash,
        "realized_pnl": account.realized_pnl,
        "total_trades": account.total_trades,
        "trade_count": len(trades),
        "trade_pnls": sorted(t.net_pnl for t in trades),
        "trade_entries_exits": sorted((t.entry_price, t.exit_price, t.exit_reason.value) for t in trades),
        "journal_outcomes": sorted(j.outcome.value for j in journal),
        "signals_generated": len(journal),
    }
