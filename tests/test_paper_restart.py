"""Level 3: real file-backed SQLite, real process-boundary simulation (spec
§15/§26 — the mandatory restart test). Compares an uninterrupted run against
one paused halfway through, persisted, and resumed from a freshly-opened
PaperStore/PaperTradingEngine — proving state genuinely survives a restart,
not just that the Python objects survive within one process.
"""

import uuid
from datetime import datetime
from pathlib import Path

import pytest

from paper.engine import Bar, PaperTradingEngine
from paper.reconciliation import reconcile
from paper.replay import replay_historical
from paper.store import PaperStore
from risk.config import RiskConfig
from strategy.baseline import TrendMomentumBaseline
from strategy.signal import ReasonCode, Side, Signal
from tests.conftest import make_bar, make_indicator_series


def _expiry_signal(**overrides) -> Signal:
    base = dict(
        symbol="TEST", generated_at=datetime(2026, 1, 1), side=Side.LONG,
        reference_price=100.0, stop_price=50.0, target_price=500.0,  # unreachable -- only expiry can close it
        risk_reward=2.0, strategy_name="unit-test", reason_codes=[ReasonCode.TREND_CONFIRMED],
    )
    base.update(overrides)
    return Signal(**base)


def _volatile_series(n: int = 60):
    """Enough qualifying + disqualifying bars to generate multiple signals,
    fills, and exits across the run — a quiet series would make this test
    trivially pass by having nothing happen at all."""
    bars = []
    for i in range(n):
        if i % 5 == 0:
            bars.append(make_bar(close=100 + (i % 20), open=100 + (i % 20), high=102 + (i % 20), low=97 + (i % 20)))
        else:
            bars.append(make_bar(sma_20=80.0, sma_50=90.0, close=100 + (i % 20), open=100 + (i % 20), high=102 + (i % 20), low=97 + (i % 20)))
    return make_indicator_series(bars)


def _business_state(store: PaperStore) -> dict:
    """Everything EXCEPT random UUIDs — spec §17 explicitly allows those to
    differ between runs; business values must not."""
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


def _tmp_db_path(tmp_path: Path) -> Path:
    return tmp_path / f"restart_test_{uuid.uuid4().hex}.db"


def test_restarted_replay_matches_an_uninterrupted_one(tmp_path):
    series = _volatile_series()
    risk_config = RiskConfig()  # identical config on both sides

    # --- uninterrupted ---
    uninterrupted_db = _tmp_db_path(tmp_path)
    store_a = PaperStore(uninterrupted_db)
    engine_a = PaperTradingEngine(store_a, risk_engine=engine_risk(risk_config), initial_capital=100_000.0)
    replay_historical(engine_a, symbol="TEST", indicator_series=series, strategy=TrendMomentumBaseline())
    state_uninterrupted = _business_state(store_a)
    store_a.close()

    # --- restarted: process 1 runs half, persists, "terminates"; process 2 resumes ---
    restarted_db = _tmp_db_path(tmp_path)
    midpoint = len(series) // 2

    store_b1 = PaperStore(restarted_db)
    engine_b1 = PaperTradingEngine(store_b1, risk_engine=engine_risk(risk_config), initial_capital=100_000.0)
    replay_historical(engine_b1, symbol="TEST", indicator_series=series, strategy=TrendMomentumBaseline(), end_index=midpoint)
    store_b1.close()  # simulates process termination

    store_b2 = PaperStore(restarted_db)  # fresh connection, fresh engine -- loads persisted state
    engine_b2 = PaperTradingEngine(store_b2, risk_engine=engine_risk(risk_config), initial_capital=100_000.0)
    replay_historical(engine_b2, symbol="TEST", indicator_series=series, strategy=TrendMomentumBaseline(), start_index=midpoint)
    state_restarted = _business_state(store_b2)

    assert state_restarted == state_uninterrupted, (
        f"Restarted run diverged from an uninterrupted one.\n"
        f"uninterrupted={state_uninterrupted}\nrestarted={state_restarted}"
    )

    report = reconcile(store_b2)
    assert report.ok, report.issues
    store_b2.close()


def engine_risk(risk_config: RiskConfig):
    from risk.engine import RiskEngine

    return RiskEngine(risk_config)


def test_position_expiry_bars_held_survives_a_restart(tmp_path):
    """Genuine gap found via self-audit: the existing restart test above
    (and every test in tests/test_paper_engine.py, by that file's own
    stated ":memory:"-only convention) never exercises max_holding_bars,
    so bars_held's restart-safety had only ever been proven via repeated
    calls on the SAME in-memory engine object -- never a real
    process-boundary restart. Same methodology as
    test_restarted_replay_matches_an_uninterrupted_one: compares an
    uninterrupted 3-bar run (max_holding_bars=3, expiring on the 3rd bar,
    stop/target set unreachable so ONLY expiry can close it) against one
    paused after 2 bars, persisted, and resumed from a freshly-opened
    PaperStore/PaperTradingEngine."""
    signal = _expiry_signal()
    bars = [
        Bar(timestamp=datetime(2026, 1, 2), open=101.0, high=102.0, low=100.5, close=101.5),
        Bar(timestamp=datetime(2026, 1, 3), open=101.5, high=102.5, low=101.0, close=102.0),
        Bar(timestamp=datetime(2026, 1, 4), open=102.0, high=103.0, low=101.5, close=102.5),
    ]

    # --- uninterrupted ---
    uninterrupted_db = _tmp_db_path(tmp_path)
    store_a = PaperStore(uninterrupted_db)
    engine_a = PaperTradingEngine(store_a, initial_capital=100_000.0, max_holding_bars=3)
    engine_a.submit_signal(signal)
    for bar in bars:
        engine_a.process_bar("TEST", bar)
    state_uninterrupted = _business_state(store_a)
    assert engine_a.store.get_open_position("TEST") is None  # expired
    store_a.close()

    # --- restarted: process 1 runs 2 bars (not yet expired), persists,
    # "terminates"; process 2 resumes and processes the 3rd (expires) ---
    restarted_db = _tmp_db_path(tmp_path)

    store_b1 = PaperStore(restarted_db)
    engine_b1 = PaperTradingEngine(store_b1, initial_capital=100_000.0, max_holding_bars=3)
    engine_b1.submit_signal(signal)
    engine_b1.process_bar("TEST", bars[0])
    engine_b1.process_bar("TEST", bars[1])
    assert engine_b1.store.get_open_position("TEST").bars_held == 2  # not yet expired
    store_b1.close()  # simulates process termination

    store_b2 = PaperStore(restarted_db)  # fresh connection, fresh engine -- loads persisted state
    engine_b2 = PaperTradingEngine(store_b2, initial_capital=100_000.0, max_holding_bars=3)
    # The resumed process must recover the CORRECT bars_held (2, not 0)
    # from the persisted Position row -- if this were lost on restart, the
    # position would incorrectly need 3 MORE bars to expire instead of 1.
    assert engine_b2.store.get_open_position("TEST").bars_held == 2
    engine_b2.process_bar("TEST", bars[2])
    state_restarted = _business_state(store_b2)

    assert state_restarted == state_uninterrupted, (
        f"Restarted run diverged from an uninterrupted one.\n"
        f"uninterrupted={state_uninterrupted}\nrestarted={state_restarted}"
    )
    assert engine_b2.store.get_open_position("TEST") is None  # expired, same as the uninterrupted run

    report = reconcile(store_b2)
    assert report.ok, report.issues
    store_b2.close()
