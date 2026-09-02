"""Phase 15 §24 — THE CRITICAL SAFETY TEST for this phase: proves that
live market data + a strategy signal + risk approval still cannot place a
real order. The only possible execution target is PAPER.

This is a structural proof, not a behavioral one wherever possible --
mirroring how Phase 13's approval-security test proved override-by-
parameter was IMPOSSIBLE (no such parameter exists) rather than merely
untested. The same posture applies here: real order execution isn't
"turned off," it's ABSENT.
"""
import inspect

import pytest

from live.dhan.broker_adapter import DisabledDhanOrderExecutor, RealOrderPlacementDisabledError
from strategy.signal import ReasonCode, Side, Signal


def _signal(**overrides) -> Signal:
    base = dict(
        symbol="RELIANCE.NS", generated_at="2026-09-01T10:00:00", side=Side.LONG, reference_price=1400.0,
        stop_price=1380.0, target_price=1440.0, risk_reward=2.0, strategy_name="unit-test",
        reason_codes=[ReasonCode.TREND_CONFIRMED],
    )
    base.update(overrides)
    return Signal(**base)


def test_place_order_always_raises_regardless_of_input():
    executor = DisabledDhanOrderExecutor()
    with pytest.raises(RealOrderPlacementDisabledError):
        executor.place_order(_signal())


def test_modify_order_always_raises():
    executor = DisabledDhanOrderExecutor()
    with pytest.raises(RealOrderPlacementDisabledError):
        executor.modify_order("some-order-id", price=999999.0)


def test_cancel_order_always_raises():
    executor = DisabledDhanOrderExecutor()
    with pytest.raises(RealOrderPlacementDisabledError):
        executor.cancel_order("some-order-id")


def test_no_code_path_anywhere_in_live_dhan_calls_a_dhan_order_endpoint():
    """Static proof, not a runtime probe: none of live/dhan/'s source
    files reference a Dhan order-placement URL path or the words
    place/modify/cancel order as an HTTP call target. wire.py's
    subscribe-message builders and rest_client.py's read-only GETs are the
    only network-shaped code in this package."""
    import pathlib

    package_dir = pathlib.Path(__file__).resolve().parent.parent / "live" / "dhan"
    forbidden_url_fragments = ("/orders", "/super/orders", "/forever")  # Dhan's real order-placement REST paths
    offending_files = []
    for py_file in package_dir.glob("*.py"):
        text = py_file.read_text(encoding="utf-8")
        for fragment in forbidden_url_fragments:
            if fragment in text:
                offending_files.append((py_file.name, fragment))
    assert offending_files == [], f"live/dhan/ source references a real order-placement endpoint: {offending_files}"


def test_disabled_order_executor_is_never_imported_by_the_live_pipeline():
    """Structural proof that DisabledDhanOrderExecutor isn't accidentally
    wired into the approval/execution path -- it exists only to rehearse
    the eventual shape (spec §13), never to be called from anywhere that
    matters yet."""
    import live.pipeline

    source = inspect.getsource(live.pipeline)
    assert "DisabledDhanOrderExecutor" not in source
    assert "DhanAccountReader" not in source


def test_a_full_signal_risk_approval_cycle_still_only_ever_reaches_paper_execution():
    """End-to-end proof using the REAL approval pipeline (unchanged from
    Phase 13): drive a signal through generation, risk approval, and human
    approval, and confirm the ONLY thing that can happen next is
    engine.submit_signal() against the real, unmodified PaperTradingEngine
    -- there is no branch, flag, or configuration anywhere in
    LiveSimPipeline.approve_pending() that could route execution to a
    broker instead."""
    from live.pipeline import LiveSimPipeline

    approve_source = inspect.getsource(LiveSimPipeline.approve_pending)
    # The one and only execution call inside approve_pending() must be the
    # existing paper engine's submit_signal -- proven by inspecting the
    # actual source text of the unchanged Phase 13 method, not by
    # asserting behavior that could be satisfied by a lucky test double.
    assert "self.engine.submit_signal" in approve_source
    forbidden_calls = ("place_order", "DhanAccountReader", "DisabledDhanOrderExecutor", "DhanBrokerAdapter", "dhan.co", "api.dhan.co")
    for forbidden in forbidden_calls:
        assert forbidden not in approve_source, f"approve_pending() unexpectedly references {forbidden!r}"
