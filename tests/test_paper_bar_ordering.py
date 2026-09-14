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


# --- is_fresh (autonomous hardening cycle 22) -----------------------------------


def test_is_fresh_false_never_fills_a_pending_order():
    """Direct unit-level proof of the cycle-22 fix, one level below
    tests/test_live_pipeline.py's own end-to-end reproduction: process_bar
    is the single chokepoint every bar-ingestion path goes through, so
    this guarantee must hold here directly, not just via the live
    pipeline's own wiring of it."""
    store = PaperStore(":memory:")
    engine = PaperTradingEngine(store, initial_capital=100_000.0)

    from strategy.signal import ReasonCode, Side, Signal

    engine.submit_signal(
        Signal(
            symbol="TEST", generated_at=datetime(2026, 1, 1), side=Side.LONG, reference_price=100.0,
            stop_price=95.0, target_price=110.0, risk_reward=2.0, strategy_name="unit-test",
            reason_codes=[ReasonCode.TREND_CONFIRMED],
        )
    )
    assert store.get_pending_order("TEST") is not None

    fill_bar = _bar(2, open=101.0, high=101.5, low=100.5, close=101.0)
    outcome = engine.process_bar("TEST", fill_bar, is_fresh=False)

    assert outcome == BarOutcome.STALE_SKIPPED
    assert store.get_open_position("TEST") is None
    assert store.get_pending_order("TEST") is not None  # untouched, still awaiting a fresh bar

    report = reconcile(store)
    assert report.ok, report.issues


def test_is_fresh_false_never_checks_an_open_positions_stop_or_target():
    store = PaperStore(":memory:")
    engine = PaperTradingEngine(store, initial_capital=100_000.0)

    from strategy.signal import ReasonCode, Side, Signal

    engine.submit_signal(
        Signal(
            symbol="TEST", generated_at=datetime(2026, 1, 1), side=Side.LONG, reference_price=100.0,
            stop_price=95.0, target_price=110.0, risk_reward=2.0, strategy_name="unit-test",
            reason_codes=[ReasonCode.TREND_CONFIRMED],
        )
    )
    fill_bar = _bar(2, open=101.0, high=101.5, low=100.5, close=101.0)
    assert engine.process_bar("TEST", fill_bar) == BarOutcome.PROCESSED
    opened = store.get_open_position("TEST")
    assert opened is not None

    # This bar's low would hit the stop_price of 95.0 if actually checked.
    breach_bar = _bar(3, open=96.0, high=96.5, low=90.0, close=91.0)
    outcome = engine.process_bar("TEST", breach_bar, is_fresh=False)

    assert outcome == BarOutcome.STALE_SKIPPED
    still_open = store.get_open_position("TEST")
    assert still_open is not None
    assert still_open.position_id == opened.position_id  # untouched -- not closed on stale data

    report = reconcile(store)
    assert report.ok, report.issues


def test_allow_new_fill_false_never_fills_a_pending_order():
    """Autonomous hardening cycle 24: direct unit-level proof, mirroring
    is_fresh's own tests above -- a PENDING order must not fill when
    allow_new_fill=False (simulating an active kill switch or account
    circuit breaker), and the order must remain untouched, awaiting the
    next bar."""
    store = PaperStore(":memory:")
    engine = PaperTradingEngine(store, initial_capital=100_000.0)

    from strategy.signal import ReasonCode, Side, Signal

    engine.submit_signal(
        Signal(
            symbol="TEST", generated_at=datetime(2026, 1, 1), side=Side.LONG, reference_price=100.0,
            stop_price=95.0, target_price=110.0, risk_reward=2.0, strategy_name="unit-test",
            reason_codes=[ReasonCode.TREND_CONFIRMED],
        )
    )
    assert store.get_pending_order("TEST") is not None

    fill_bar = _bar(2, open=101.0, high=101.5, low=100.5, close=101.0)
    outcome = engine.process_bar("TEST", fill_bar, allow_new_fill=False)

    assert outcome == BarOutcome.EXECUTION_HALTED_SKIPPED
    assert store.get_open_position("TEST") is None
    assert store.get_pending_order("TEST") is not None  # untouched, still awaiting a bar where filling is allowed

    report = reconcile(store)
    assert report.ok, report.issues


def test_allow_new_fill_false_still_checks_an_open_positions_stop_or_target():
    """The critical asymmetry: allow_new_fill=False must NEVER block
    managing an already-OPEN position -- refusing to check its stop/
    target during a halt/kill-switch event would strand it with no way
    to exit, a worse bug than the one this cycle fixes."""
    store = PaperStore(":memory:")
    engine = PaperTradingEngine(store, initial_capital=100_000.0)

    from strategy.signal import ReasonCode, Side, Signal

    engine.submit_signal(
        Signal(
            symbol="TEST", generated_at=datetime(2026, 1, 1), side=Side.LONG, reference_price=100.0,
            stop_price=95.0, target_price=110.0, risk_reward=2.0, strategy_name="unit-test",
            reason_codes=[ReasonCode.TREND_CONFIRMED],
        )
    )
    fill_bar = _bar(2, open=101.0, high=101.5, low=100.5, close=101.0)
    assert engine.process_bar("TEST", fill_bar) == BarOutcome.PROCESSED
    opened = store.get_open_position("TEST")
    assert opened is not None

    # This bar's low would hit the stop_price of 95.0 -- must still be
    # checked and close the position, even with allow_new_fill=False.
    breach_bar = _bar(3, open=96.0, high=96.5, low=90.0, close=91.0)
    outcome = engine.process_bar("TEST", breach_bar, allow_new_fill=False)

    assert outcome == BarOutcome.PROCESSED  # a real action happened -- not EXECUTION_HALTED_SKIPPED
    assert store.get_open_position("TEST") is None  # closed via stop, exactly as if allow_new_fill had been True

    report = reconcile(store)
    assert report.ok, report.issues


def test_allow_new_fill_true_is_the_unaffected_default_for_every_non_live_caller():
    """Every non-live caller (backtest replay, paper/advance.py's own
    catch-up fills -- which apply the EQUIVALENT guard at ITS OWN call
    site already, direct calls like every other test in this file) omits
    allow_new_fill entirely -- must remain byte-for-byte the
    pre-cycle-24 behavior (PROCESSED, real fill)."""
    store = PaperStore(":memory:")
    engine = PaperTradingEngine(store, initial_capital=100_000.0)

    from strategy.signal import ReasonCode, Side, Signal

    engine.submit_signal(
        Signal(
            symbol="TEST", generated_at=datetime(2026, 1, 1), side=Side.LONG, reference_price=100.0,
            stop_price=95.0, target_price=110.0, risk_reward=2.0, strategy_name="unit-test",
            reason_codes=[ReasonCode.TREND_CONFIRMED],
        )
    )
    fill_bar = _bar(2, open=101.0, high=101.5, low=100.5, close=101.0)
    outcome = engine.process_bar("TEST", fill_bar)  # no allow_new_fill kwarg at all

    assert outcome == BarOutcome.PROCESSED
    assert store.get_open_position("TEST") is not None


def test_is_fresh_true_is_the_unaffected_default_for_every_non_live_caller():
    """Every non-live caller (backtest replay, paper/advance.py's catch-up
    fills, direct calls like every other test in this file) omits
    is_fresh entirely -- this must remain byte-for-byte the pre-cycle-22
    behavior (PROCESSED, real fill), never STALE_SKIPPED by default."""
    store = PaperStore(":memory:")
    engine = PaperTradingEngine(store, initial_capital=100_000.0)

    from strategy.signal import ReasonCode, Side, Signal

    engine.submit_signal(
        Signal(
            symbol="TEST", generated_at=datetime(2026, 1, 1), side=Side.LONG, reference_price=100.0,
            stop_price=95.0, target_price=110.0, risk_reward=2.0, strategy_name="unit-test",
            reason_codes=[ReasonCode.TREND_CONFIRMED],
        )
    )
    fill_bar = _bar(2, open=101.0, high=101.5, low=100.5, close=101.0)
    outcome = engine.process_bar("TEST", fill_bar)  # no is_fresh kwarg at all

    assert outcome == BarOutcome.PROCESSED
    assert store.get_open_position("TEST") is not None
