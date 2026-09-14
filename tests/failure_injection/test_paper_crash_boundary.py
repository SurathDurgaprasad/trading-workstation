"""Autonomous hardening cycle 8 -- crash-boundary attack on paper/engine.py's
PaperOrder->Position fill sequence, using a REAL temporary SQLite file (per
this cycle's own mission instructions: "do not rely exclusively on mocks").

tests/test_paper_restart.py already proves the "commit succeeded, then the
process died, then a re-delivered bar after restart is a safe no-op" case in
depth (test_replaying_an_already_processed_bar_after_a_restart_does_not_
duplicate_state). This file covers the ONE boundary that was still
untested: a crash DURING the transaction itself, before it ever commits --
i.e. nothing at all should persist, not a partial fill, not an orphaned
order status, not an advanced bar cursor.

The actual state machine, derived from paper/engine.py and paper/models.py
(read directly, not assumed):

    PaperOrder:  PENDING --(fill)--> FILLED [terminal]
    Position:    (created OPEN at fill time) --(stop/target/expiry/EOD)--> CLOSED [terminal]

Both terminal transitions are additionally guarded at the store layer
(paper/store.py's update_order/update_position, `WHERE status != <terminal>`)
-- a defense-in-depth layer this file's crash-injection test also
incidentally exercises (the retry-after-crash path calls _fill_pending_order
again from a clean PENDING order, never revisiting an already-FILLED one).
"""
from datetime import datetime
from pathlib import Path

import pytest

from paper.engine import Bar, BarOutcome, PaperTradingEngine
from paper.models import OrderStatus
from paper.store import PaperStore

from tests.test_paper_restart import _expiry_signal, _tmp_db_path


def test_a_crash_inside_the_fill_transaction_persists_nothing_at_all(tmp_path: Path):
    """Deterministic crash injection (mission section 15): fail partway
    through the SAME transaction process_bar() wraps _fill_pending_order
    in, AFTER the fill row would have been written but BEFORE the position
    row is. A real, uncommitted SQLite transaction must roll back
    completely on ANY exception -- not just the specific write that
    failed -- so the order must still be PENDING, no fill or position row
    may exist, and the bar cursor must not have advanced, all verified
    against a REAL temp file re-opened as a genuinely separate connection
    (not just re-reading the same in-memory Python objects)."""
    signal = _expiry_signal()
    fill_bar = Bar(timestamp=datetime(2026, 1, 2), open=101.0, high=102.0, low=100.5, close=101.5)
    db_path = _tmp_db_path(tmp_path)

    store = PaperStore(db_path)
    engine = PaperTradingEngine(store, initial_capital=100_000.0)
    journal = engine.submit_signal(signal)
    assert journal.order_id is not None

    original_save_position = PaperStore.save_position

    def _crash_after_fill_before_position(self, position):
        raise RuntimeError("simulated process crash: killed after the fill was written, before the position was")

    PaperStore.save_position = _crash_after_fill_before_position
    try:
        with pytest.raises(RuntimeError, match="simulated process crash"):
            engine.process_bar("TEST", fill_bar)
    finally:
        PaperStore.save_position = original_save_position
    store.close()

    # Re-open as a genuinely fresh connection to the same file -- proves
    # this is real, committed-or-not disk state, not an in-memory artifact.
    verify_store = PaperStore(db_path)
    order = verify_store.get_pending_order("TEST")
    assert order is not None
    assert order.status == OrderStatus.PENDING  # NOT left FILLED by the aborted transaction
    assert verify_store.get_open_position("TEST") is None  # no orphaned position
    assert len(verify_store._fetch_all_json("paper_fills")) == 0  # no orphaned fill either
    assert verify_store.get_last_bar_timestamp("TEST") is None  # bar cursor never advanced
    verify_store.close()

    # The crash-recovery path: a fresh process (real restart) retries the
    # SAME bar with the bug now gone -- must fill cleanly exactly once,
    # with no leftover partial state from the aborted attempt interfering.
    recovered_store = PaperStore(db_path)
    recovered_engine = PaperTradingEngine(recovered_store, initial_capital=100_000.0)
    outcome = recovered_engine.process_bar("TEST", fill_bar)

    assert outcome == BarOutcome.PROCESSED
    assert len(recovered_store.list_positions()) == 1
    assert len(recovered_store._fetch_all_json("paper_fills")) == 1
    assert recovered_store.get_pending_order("TEST") is None  # no longer pending -- it filled
    recovered_store.close()


def test_a_crash_after_commit_but_before_the_caller_observes_the_result_is_safe_on_retry(tmp_path: Path):
    """The complementary boundary: the transaction DID commit (the fill,
    order-status-update, and position are all genuinely persisted), but
    the process dies before returning control to whatever called
    process_bar() (e.g. a scheduler tick, or paper/replay.py's own loop) --
    so the caller has no way to know whether the bar was actually
    processed and, from its own point of view, must be prepared to retry
    the identical call after a restart. This is exactly what bar_cursor
    idempotency already exists for; this test pins the specific "crash
    right after commit" framing as its own named boundary rather than
    only being implied by the broader restart test in
    tests/test_paper_restart.py."""
    signal = _expiry_signal()
    fill_bar = Bar(timestamp=datetime(2026, 1, 2), open=101.0, high=102.0, low=100.5, close=101.5)
    db_path = _tmp_db_path(tmp_path)

    store = PaperStore(db_path)
    engine = PaperTradingEngine(store, initial_capital=100_000.0)
    engine.submit_signal(signal)
    outcome = engine.process_bar("TEST", fill_bar)
    assert outcome == BarOutcome.PROCESSED
    # The transaction is already committed at this point -- simulate the
    # process dying HERE, before the caller (whoever invoked process_bar)
    # ever gets to act on the return value.
    store.close()

    # A fresh "process" retries the identical call, believing it may not
    # have gone through.
    retry_store = PaperStore(db_path)
    retry_engine = PaperTradingEngine(retry_store, initial_capital=100_000.0)
    retry_outcome = retry_engine.process_bar("TEST", fill_bar)

    assert retry_outcome == BarOutcome.DUPLICATE_SKIPPED
    assert len(retry_store.list_positions()) == 1  # still exactly one
    assert len(retry_store._fetch_all_json("paper_fills")) == 1  # still exactly one
    retry_store.close()
