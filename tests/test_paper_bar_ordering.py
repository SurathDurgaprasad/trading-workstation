"""Phase 7A §6/§7/§9: duplicate-bar idempotency and out-of-order rejection,
directly against PaperTradingEngine.process_bar() — the single chokepoint
every bar-ingestion path (historical replay, PaperSession, the MCP
submit_paper_market_bar_tool) goes through, so these guarantees apply
everywhere at once rather than being reimplemented per-caller.
"""

from datetime import datetime

import pytest

from paper.engine import Bar, BarOutcome, PaperTradingEngine
from paper.errors import OutOfOrderBarError
from paper.reconciliation import reconcile
from paper.store import PaperStore


def _bar(day: int, **overrides) -> Bar:
    base = dict(timestamp=datetime(2026, 1, day), open=100.0, high=101.0, low=99.0, close=100.0)
    base.update(overrides)
    return Bar(**base)


def test_first_bar_for_a_symbol_is_always_processed():
    store = PaperStore(":memory:")
    engine = PaperTradingEngine(store, initial_capital=100_000.0)
    assert engine.process_bar("TEST", _bar(2)) == BarOutcome.PROCESSED


def test_resubmitting_the_identical_bar_is_a_no_op_not_an_error():
    store = PaperStore(":memory:")
    engine = PaperTradingEngine(store, initial_capital=100_000.0)

    bar = _bar(2)
    assert engine.process_bar("TEST", bar) == BarOutcome.PROCESSED
    equity_after_first = engine.account.equity

    # Resubmit the SAME bar object -- must not corrupt state or double-count
    # anything (spec §6's explicit test: "bar X, bar X again").
    assert engine.process_bar("TEST", bar) == BarOutcome.DUPLICATE_SKIPPED
    assert engine.account.equity == equity_after_first

    report = reconcile(store)
    assert report.ok, report.issues


def test_duplicate_detection_survives_a_position_being_open():
    """The duplicate check must fire even when there IS an open
    position/pending order for the symbol -- not just on quiet bars."""
    store = PaperStore(":memory:")
    engine = PaperTradingEngine(store, initial_capital=100_000.0)

    from datetime import datetime as dt

    from strategy.signal import ReasonCode, Side, Signal

    engine.submit_signal(
        Signal(
            symbol="TEST", generated_at=dt(2026, 1, 1), side=Side.LONG, reference_price=100.0,
            stop_price=95.0, target_price=110.0, risk_reward=2.0, strategy_name="unit-test",
            reason_codes=[ReasonCode.TREND_CONFIRMED],
        )
    )
    fill_bar = _bar(2, open=101.0, high=101.5, low=100.5, close=101.0)
    assert engine.process_bar("TEST", fill_bar) == BarOutcome.PROCESSED
    position_after_first = store.get_open_position("TEST")
    assert position_after_first is not None

    assert engine.process_bar("TEST", fill_bar) == BarOutcome.DUPLICATE_SKIPPED
    position_after_second = store.get_open_position("TEST")
    # Exactly the same position -- no second fill, no second position created.
    assert position_after_second.position_id == position_after_first.position_id
    assert len(store.list_positions()) == 1


def test_a_bar_older_than_the_last_one_processed_raises_out_of_order():
    store = PaperStore(":memory:")
    engine = PaperTradingEngine(store, initial_capital=100_000.0)

    engine.process_bar("TEST", _bar(5))
    with pytest.raises(OutOfOrderBarError) as excinfo:
        engine.process_bar("TEST", _bar(3))

    assert excinfo.value.symbol == "TEST"
    # State must be unchanged by the rejected bar -- the transaction rolled back.
    report = reconcile(store)
    assert report.ok, report.issues


def test_out_of_order_bars_are_tracked_independently_per_symbol():
    store = PaperStore(":memory:")
    engine = PaperTradingEngine(store, initial_capital=100_000.0)

    engine.process_bar("AAA", _bar(5))
    # A bar for a DIFFERENT symbol at an earlier date is not "out of order"
    # -- each symbol has its own cursor.
    assert engine.process_bar("BBB", _bar(2)) == BarOutcome.PROCESSED


def test_a_large_gap_between_bars_is_logged_not_rejected(caplog):
    import logging

    store = PaperStore(":memory:")
    engine = PaperTradingEngine(store, initial_capital=100_000.0)

    engine.process_bar("TEST", _bar(1))
    with caplog.at_level(logging.WARNING, logger="paper.engine"):
        outcome = engine.process_bar("TEST", Bar(timestamp=datetime(2026, 3, 1), open=100.0, high=101.0, low=99.0, close=100.0))

    assert outcome == BarOutcome.PROCESSED  # never rejected -- observational only
    assert any("Large gap" in record.message for record in caplog.records)
