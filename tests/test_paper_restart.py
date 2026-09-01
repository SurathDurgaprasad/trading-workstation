"""Level 3: real file-backed SQLite, real process-boundary simulation (spec
§15/§26 — the mandatory restart test). Compares an uninterrupted run against
one paused halfway through, persisted, and resumed from a freshly-opened
PaperStore/PaperTradingEngine — proving state genuinely survives a restart,
not just that the Python objects survive within one process.
"""

import uuid
from pathlib import Path

import pytest

from paper.engine import PaperTradingEngine
from paper.reconciliation import reconcile
from paper.replay import replay_historical
from paper.store import PaperStore
from risk.config import RiskConfig
from strategy.baseline import TrendMomentumBaseline
from tests.conftest import make_bar, make_indicator_series


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
