"""Level 1/2 (mostly real components, in-memory SQLite — no mocks on any
paper-trading internals; only the data itself is synthetic)."""

from datetime import datetime

import pytest

from paper.engine import Bar, PaperTradingEngine
from paper.models import JournalOutcome, OrderStatus, PositionStatus
from paper.reconciliation import reconcile
from paper.store import PaperStore
from risk.config import RiskConfig
from risk.engine import RiskEngine
from strategy.signal import ReasonCode, Side, Signal


def _signal(**overrides) -> Signal:
    base = dict(
        symbol="TEST", generated_at=datetime(2026, 1, 1), side=Side.LONG,
        reference_price=100.0, stop_price=95.0, target_price=110.0, risk_reward=2.0,
        strategy_name="unit-test", reason_codes=[ReasonCode.TREND_CONFIRMED],
    )
    base.update(overrides)
    return Signal(**base)


@pytest.fixture
def engine() -> PaperTradingEngine:
    return PaperTradingEngine(PaperStore(":memory:"), initial_capital=100_000.0)


def test_submit_signal_creates_a_pending_order(engine):
    journal = engine.submit_signal(_signal())
    assert journal.outcome == JournalOutcome.APPROVED_PENDING
    assert journal.order_id is not None

    order = engine.store.get_pending_order("TEST")
    assert order is not None
    assert order.status == OrderStatus.PENDING


def test_submit_signal_is_idempotent_sequentially(engine):
    signal = _signal()
    first = engine.submit_signal(signal)
    second = engine.submit_signal(signal)
    assert first.journal_entry_id == second.journal_entry_id
    assert len(engine.store.list_journal_entries()) == 1


def test_submit_signal_is_idempotent_under_real_concurrent_contention(tmp_path):
    """Autonomous hardening cycle 15: a real, reproduced race -- found via
    a genuine multi-threaded test, not theoretical. submit_signal()'s own
    "does a journal entry already exist" check and the transaction that
    inserts a new one are two separate steps (a classic check-then-act
    TOCTOU): two SEPARATE connections/engines on the SAME db file (the
    faithful simulation of two independent processes -- e.g. a manually
    triggered shadow-run racing an independent scheduler tick, or two
    concurrent MCP paper_trade_signal_tool calls) racing on the IDENTICAL
    signal previously left the LOSER with a raw, uncaught
    sqlite3.IntegrityError instead of gracefully returning the winner's
    own already-committed JournalEntry -- violating this method's own
    documented idempotency contract under real contention, even though
    the DB-level UNIQUE constraints already prevented an actual duplicate
    row from ever being created."""
    import threading

    db_path = tmp_path / "race.db"
    PaperStore(db_path).close()  # create the schema before threads race on it
    signal = _signal()

    results: dict[str, object] = {}
    barrier = threading.Barrier(2)

    def _attempt(key: str) -> None:
        store = PaperStore(db_path)
        engine_instance = PaperTradingEngine(store, initial_capital=100_000.0)
        try:
            barrier.wait()
            journal = engine_instance.submit_signal(signal)
            results[key] = journal.journal_entry_id
        finally:
            store.close()

    t1 = threading.Thread(target=_attempt, args=("a",))
    t2 = threading.Thread(target=_attempt, args=("b",))
    t1.start()
    t2.start()
    t1.join(timeout=10)
    t2.join(timeout=10)

    assert set(results.keys()) == {"a", "b"}, f"one side crashed instead of returning gracefully: {results}"
    assert results["a"] == results["b"], "both racing callers must agree on the SAME journal entry"

    verify_store = PaperStore(db_path)
    assert len(verify_store.list_journal_entries()) == 1  # never a duplicate row
    verify_store.close()


# --- G9: dashboard/CLI dual-writer risk (continuous red-team, 2026-09-23) --
#
# G9 (docs/MASTER_KNOWN_ISSUES.md): the dashboard's single-symbol workstation
# pages and a separate `paper-live` CLI session (no --runtime-dir) share the
# SAME default data/live_sim_trading.db -- a documented, supported use case
# (see live/workstation.py's own module docstring). Each is a SEPARATE
# PaperTradingEngine instance, in a separate OS process; before this fix,
# `self.account` was loaded once at construction and never refreshed, so one
# process's committed account changes were invisible to the other's risk
# decisions/mutations for its entire lifetime.


def test_submit_signal_sees_a_second_processs_committed_account_changes(tmp_path):
    """G9 core fix: PaperTradingEngine._refresh_account(), called inside
    submit_signal's own transaction. Simulates the real scenario: engine_a
    is constructed first (like a dashboard singleton, long-lived); a
    SEPARATE process (engine_b, its own connection) then drives the
    account into a real, persisted consecutive-loss circuit-breaker state.
    engine_a's own submit_signal call, made AFTER that -- with no bar ever
    processed by engine_a itself -- must still see and honor it, not the
    healthy snapshot it was constructed with."""
    db_path = tmp_path / "g9_stale_account.db"
    store_a = PaperStore(db_path)
    engine_a = PaperTradingEngine(store_a, initial_capital=100_000.0)
    assert engine_a.account.consecutive_losses == 0  # healthy at construction time

    # A second, independent connection/engine -- the faithful simulation of
    # a separate OS process (e.g. the `paper-live` CLI actually driving
    # bars) -- persists a real circuit-breaker-tripped account state.
    store_b = PaperStore(db_path)
    tripped_account = store_b.get_account()
    tripped_account.consecutive_losses = RiskConfig().consecutive_loss_hard_limit
    store_b.save_account(tripped_account)
    store_b.close()

    # engine_a's own in-memory copy is still the healthy one it was
    # constructed with -- unchanged so far, proving this isn't a fluke of
    # construction order.
    assert engine_a.account.consecutive_losses == 0

    journal = engine_a.submit_signal(_signal())
    assert journal.outcome == JournalOutcome.REJECTED, (
        "a stale cached account would have wrongly approved this signal -- "
        "the circuit breaker tripped by the OTHER process must be honored"
    )
    assert engine_a.account.consecutive_losses == RiskConfig().consecutive_loss_hard_limit

    store_a.close()


def test_two_engine_instances_racing_different_signals_for_the_same_symbol_never_both_open_an_order(tmp_path):
    """G9 concurrency fix: PaperStore.transaction() now uses BEGIN
    IMMEDIATE, not the SQLite-default DEFERRED BEGIN. Two DIFFERENT
    signals (distinct stable_id()s -- cycle 15's same-signal idempotency
    fix does not apply here) for the SAME symbol, submitted by two
    separate engine instances (separate connections) on the same db file
    at the same synchronized moment: the "already_active" check
    (get_pending_order/get_open_position) that gates order creation must
    never let both callers see "nothing active yet" -- exactly one side
    may create the PENDING order; the loser must see the winner's
    already-committed order and skip."""
    import threading

    db_path = tmp_path / "g9_same_symbol_race.db"
    PaperStore(db_path).close()  # create the schema before threads race on it

    signal_a = _signal(generated_at=datetime(2026, 1, 1, 9, 15), reference_price=100.0)
    signal_b = _signal(generated_at=datetime(2026, 1, 1, 9, 16), reference_price=101.0)
    assert signal_a.stable_id() != signal_b.stable_id()

    results: dict[str, str] = {}
    barrier = threading.Barrier(2)

    def _attempt(key: str, signal: Signal) -> None:
        store = PaperStore(db_path)
        engine_instance = PaperTradingEngine(store, initial_capital=100_000.0)
        try:
            barrier.wait()
            journal = engine_instance.submit_signal(signal)
            results[key] = journal.outcome.value
        finally:
            store.close()

    t1 = threading.Thread(target=_attempt, args=("a", signal_a))
    t2 = threading.Thread(target=_attempt, args=("b", signal_b))
    t1.start()
    t2.start()
    t1.join(timeout=15)
    t2.join(timeout=15)

    assert set(results.keys()) == {"a", "b"}, f"one side crashed/hung instead of resolving cleanly: {results}"
    outcomes = {results["a"], results["b"]}
    assert outcomes == {JournalOutcome.APPROVED_PENDING.value, JournalOutcome.SKIPPED_ALREADY_ACTIVE.value}, (
        f"exactly one side must win the symbol's single PENDING-order slot, never both/neither: {results}"
    )

    verify_store = PaperStore(db_path)
    pending = verify_store.get_pending_order("TEST")
    assert pending is not None
    all_orders_for_symbol = [o for o in verify_store.list_pending_orders() if o.symbol == "TEST"]
    assert len(all_orders_for_symbol) == 1, "at most one PENDING order may ever exist for a symbol"
    verify_store.close()


# --- decision_id correlation (LIVE SYSTEM HARDENING mission, Issue 3) -------


def test_submit_signal_with_no_decision_id_is_honestly_none(engine):
    # A signal that never went through decision_engine (e.g. a plain
    # Strategy in live/pipeline.py) must carry decision_id=None through
    # to the journal entry -- never fabricated.
    journal = engine.submit_signal(_signal())
    assert journal.decision_id is None


def test_submit_signal_carries_the_decision_id_into_the_journal_entry(engine):
    journal = engine.submit_signal(_signal(decision_id="dec-live-123"))
    assert journal.decision_id == "dec-live-123"

    # Re-read from the store fresh (not the in-memory return value) --
    # proves it is genuinely PERSISTED, not just present on this one object.
    reloaded = engine.store.find_journal_entry_by_signal_id(_signal(decision_id="dec-live-123").stable_id())
    assert reloaded is not None
    assert reloaded.decision_id == "dec-live-123"


def test_decision_id_survives_a_fill_and_close_lifecycle(engine):
    # The two journal.model_copy(update={...}) calls in paper/engine.py
    # (on fill, on close) must preserve decision_id -- it is never one of
    # the fields those updates explicitly override.
    engine.submit_signal(_signal(decision_id="dec-live-456", stop_price=95.0, target_price=110.0))
    engine.process_bar("TEST", Bar(timestamp=datetime(2026, 1, 2), open=101.0, high=101.5, low=100.5, close=101.0))
    journal = engine.store.find_journal_entry_by_signal_id(_signal(decision_id="dec-live-456").stable_id())
    assert journal.outcome == JournalOutcome.APPROVED_FILLED_OPEN
    assert journal.decision_id == "dec-live-456"

    engine.process_bar("TEST", Bar(timestamp=datetime(2026, 1, 3), open=101.0, high=120.0, low=100.0, close=115.0))
    journal = engine.store.find_journal_entry_by_signal_id(_signal(decision_id="dec-live-456").stable_id())
    assert journal.outcome == JournalOutcome.APPROVED_FILLED_CLOSED
    assert journal.decision_id == "dec-live-456"


def test_pending_order_fills_at_the_next_bars_open_not_the_signal_bars_price(engine):
    engine.submit_signal(_signal(reference_price=100.0))
    engine.process_bar("TEST", Bar(timestamp=datetime(2026, 1, 2), open=103.0, high=103.5, low=102.5, close=103.2))

    position = engine.store.get_open_position("TEST")
    assert position is not None
    assert position.entry_price != 100.0  # not the signal's reference_price
    assert abs(position.entry_price - 103.0) < 1.0  # slippage-adjusted, close to the bar's open


def test_target_hit_closes_the_position_and_records_a_trade(engine):
    engine.submit_signal(_signal(stop_price=95.0, target_price=110.0))
    engine.process_bar("TEST", Bar(timestamp=datetime(2026, 1, 2), open=101.0, high=101.5, low=100.5, close=101.0))
    engine.process_bar("TEST", Bar(timestamp=datetime(2026, 1, 3), open=101.0, high=120.0, low=100.0, close=115.0))

    position = engine.store.get_open_position("TEST")
    assert position is None  # no longer open

    trades = engine.store.list_trades()
    assert len(trades) == 1
    assert trades[0].exit_price == 110.0

    journal = engine.store.find_journal_entry_by_signal_id(_signal().stable_id())
    assert journal.outcome == JournalOutcome.APPROVED_FILLED_CLOSED
    assert journal.trade_id is not None


def test_stop_hit_closes_the_position_at_the_stop_price(engine):
    engine.submit_signal(_signal(stop_price=95.0, target_price=110.0))
    engine.process_bar("TEST", Bar(timestamp=datetime(2026, 1, 2), open=101.0, high=101.5, low=100.5, close=101.0))
    engine.process_bar("TEST", Bar(timestamp=datetime(2026, 1, 3), open=101.0, high=102.0, low=90.0, close=93.0))

    trades = engine.store.list_trades()
    assert len(trades) == 1
    assert trades[0].exit_price == 95.0
    from backtesting.trade import ExitReason
    assert trades[0].exit_reason == ExitReason.STOP


def test_same_bar_stop_and_target_ambiguity_resolves_to_stop_matching_the_backtester(engine):
    engine.submit_signal(_signal(stop_price=95.0, target_price=110.0))
    engine.process_bar("TEST", Bar(timestamp=datetime(2026, 1, 2), open=101.0, high=101.5, low=100.5, close=101.0))
    # This single bar's range spans BOTH stop (95) and target (110).
    engine.process_bar("TEST", Bar(timestamp=datetime(2026, 1, 3), open=101.0, high=115.0, low=90.0, close=98.0))

    trades = engine.store.list_trades()
    assert len(trades) == 1
    assert trades[0].exit_price == 95.0
    from backtesting.trade import ExitReason
    assert trades[0].exit_reason == ExitReason.STOP


def test_end_of_data_forces_a_close_at_the_last_bars_close(engine):
    engine.submit_signal(_signal(stop_price=50.0, target_price=500.0))  # unreachable levels
    engine.process_bar("TEST", Bar(timestamp=datetime(2026, 1, 2), open=101.0, high=102.0, low=100.5, close=101.5))
    last_bar = Bar(timestamp=datetime(2026, 1, 3), open=101.5, high=103.0, low=101.0, close=102.0)
    engine.process_bar("TEST", last_bar)
    engine.close_at_end_of_data("TEST", last_bar)

    trades = engine.store.list_trades()
    assert len(trades) == 1
    from backtesting.trade import ExitReason
    assert trades[0].exit_reason == ExitReason.END_OF_DATA


# --- max_holding_bars / ExitReason.EXPIRED ---------------------------------------


def test_max_holding_bars_defaults_to_none_positions_never_expire(engine):
    """Default OFF, byte-for-byte unchanged behavior: with no
    max_holding_bars given, a position that never hits stop or target
    stays open indefinitely -- exactly as before this feature existed."""
    from datetime import timedelta

    engine.submit_signal(_signal(stop_price=50.0, target_price=500.0))  # unreachable levels
    for day_offset in range(1, 39):
        engine.process_bar("TEST", Bar(timestamp=datetime(2026, 1, 1) + timedelta(days=day_offset), open=101.0, high=102.0, low=100.5, close=101.5))

    position = engine.store.get_open_position("TEST")
    assert position is not None  # still open after 38 bars
    assert engine.store.list_trades() == []


def test_max_holding_bars_force_closes_after_n_bars_with_no_stop_or_target_hit():
    from backtesting.trade import ExitReason

    engine = PaperTradingEngine(PaperStore(":memory:"), initial_capital=100_000.0, max_holding_bars=2)
    signal = _signal(stop_price=50.0, target_price=500.0)  # unreachable levels
    engine.submit_signal(signal)
    engine.process_bar("TEST", Bar(timestamp=datetime(2026, 1, 2), open=101.0, high=102.0, low=100.5, close=101.5))  # fills -- bars_held becomes 1
    assert engine.store.get_open_position("TEST") is not None  # not yet expired

    engine.process_bar("TEST", Bar(timestamp=datetime(2026, 1, 3), open=101.5, high=102.5, low=101.0, close=102.0))  # bars_held becomes 2 -- expires here

    assert engine.store.get_open_position("TEST") is None
    trades = engine.store.list_trades()
    assert len(trades) == 1
    assert trades[0].exit_reason == ExitReason.EXPIRED
    assert trades[0].exit_price != 102.0  # slippage-adjusted, same treatment as END_OF_DATA -- not the raw close

    journal = engine.store.find_journal_entry_by_signal_id(signal.stable_id())
    assert journal.outcome == JournalOutcome.APPROVED_FILLED_CLOSED


def test_max_holding_bars_does_not_override_a_genuine_target_hit_on_the_same_bar():
    """A real stop/target hit always wins over expiry, even on the exact
    bar that would otherwise have expired the position."""
    from backtesting.trade import ExitReason

    engine = PaperTradingEngine(PaperStore(":memory:"), initial_capital=100_000.0, max_holding_bars=1)
    engine.submit_signal(_signal(stop_price=95.0, target_price=110.0))
    # The very first (fill) bar ALSO hits target -- max_holding_bars=1 would
    # otherwise expire on this exact bar; the real target hit must win.
    engine.process_bar("TEST", Bar(timestamp=datetime(2026, 1, 2), open=101.0, high=120.0, low=100.0, close=115.0))

    trades = engine.store.list_trades()
    assert len(trades) == 1
    assert trades[0].exit_reason == ExitReason.TARGET
    assert trades[0].exit_price == 110.0  # exact target level, not slippage-adjusted


def test_bars_held_persists_across_separate_process_bar_calls():
    """Restart-safety: bars_held is durably persisted on the Position row
    after every bar (paper.store.PaperStore.transaction() per
    process_bar() call, same guarantee every other mutation here already
    has) -- a fresh read after each call proves it, not just an in-memory
    counter that would be lost on a crash/restart."""
    engine = PaperTradingEngine(PaperStore(":memory:"), initial_capital=100_000.0, max_holding_bars=3)
    engine.submit_signal(_signal(stop_price=50.0, target_price=500.0))  # unreachable levels

    engine.process_bar("TEST", Bar(timestamp=datetime(2026, 1, 2), open=101.0, high=102.0, low=100.5, close=101.5))
    assert engine.store.get_open_position("TEST").bars_held == 1

    engine.process_bar("TEST", Bar(timestamp=datetime(2026, 1, 3), open=101.5, high=102.5, low=101.0, close=102.0))
    assert engine.store.get_open_position("TEST").bars_held == 2

    engine.process_bar("TEST", Bar(timestamp=datetime(2026, 1, 4), open=102.0, high=103.0, low=101.5, close=102.5))
    assert engine.store.get_open_position("TEST") is None  # expired on the 3rd bar


def test_rejected_signal_is_journaled_not_silently_dropped():
    strict = PaperTradingEngine(PaperStore(":memory:"), risk_engine=RiskEngine(RiskConfig(min_risk_reward=5.0)))
    journal = strict.submit_signal(_signal(risk_reward=2.0))
    assert journal.outcome == JournalOutcome.REJECTED
    assert strict.store.get_pending_order("TEST") is None


def test_duplicate_signal_does_not_create_a_duplicate_order_or_journal_row(engine):
    signal = _signal()
    j1 = engine.submit_signal(signal)
    j2 = engine.submit_signal(signal)
    assert j1.journal_entry_id == j2.journal_entry_id
    assert len(engine.store.list_journal_entries()) == 1


def test_a_second_signal_while_one_is_pending_does_not_stack_a_position(engine):
    first = _signal(generated_at=datetime(2026, 1, 1))
    second = _signal(generated_at=datetime(2026, 1, 1, 1))  # different bar -> different stable_id
    assert first.stable_id() != second.stable_id()

    j1 = engine.submit_signal(first)
    j2 = engine.submit_signal(second)

    assert j1.outcome == JournalOutcome.APPROVED_PENDING
    assert j2.outcome == JournalOutcome.SKIPPED_ALREADY_ACTIVE
    assert len(engine.store._fetch_all_json("paper_orders")) == 1


def test_a_second_signal_while_a_position_is_open_does_not_stack(engine):
    # Here account.open_positions is already 1 by the time the second signal
    # is evaluated, so RiskEngine's OWN POSITION_ALREADY_OPEN veto fires
    # (Phase 4 behavior) -- REJECTED, not the engine-level SKIPPED_ALREADY_ACTIVE
    # path (that one is specifically for the narrower pending-order gap,
    # tested separately above, where account state hasn't caught up yet).
    first = _signal(generated_at=datetime(2026, 1, 1))
    engine.submit_signal(first)
    engine.process_bar("TEST", Bar(timestamp=datetime(2026, 1, 2), open=101.0, high=101.5, low=100.5, close=101.0))
    assert engine.store.get_open_position("TEST") is not None

    second = _signal(generated_at=datetime(2026, 1, 2, 1))
    j2 = engine.submit_signal(second)
    assert j2.outcome == JournalOutcome.REJECTED
    from risk.veto import VetoReason
    risk_decision = engine.store.get_risk_decision(j2.risk_decision_id)
    assert VetoReason.POSITION_ALREADY_OPEN in risk_decision.veto_reasons
    assert len(engine.store.list_positions()) == 1


def test_account_reconciles_cleanly_after_a_full_lifecycle(engine):
    engine.submit_signal(_signal())
    engine.process_bar("TEST", Bar(timestamp=datetime(2026, 1, 2), open=101.0, high=101.5, low=100.5, close=101.0))
    engine.process_bar("TEST", Bar(timestamp=datetime(2026, 1, 3), open=101.0, high=120.0, low=100.0, close=115.0))

    report = reconcile(engine.store)
    assert report.ok, report.issues


def test_journal_carries_explicit_versions_not_latest(engine):
    journal = engine.submit_signal(_signal())
    assert journal.strategy_version != "latest"
    assert journal.risk_config_version != "latest"
    assert journal.execution_model_version != "latest"
    assert len(journal.risk_config_version) > 0
