"""Phase 13 §17 — THE critical security test: a client cannot force
quantity/stop/target values into execution through the approval API.

The proof is structural, not behavioral: approve_pending()/reject_pending()
do not have a parameter that could carry such a value in the first place --
calling with one raises TypeError before any of this module's logic even
runs. This mirrors the exact pattern Phase 6/9 already established
(Signal/FilteredStrategy have no field a caller could use to override
price/quantity).
"""
import inspect

import pytest

from live.pipeline import LiveSimPipeline


def test_approve_pending_signature_has_no_execution_override_parameters():
    sig = inspect.signature(LiveSimPipeline.approve_pending)
    param_names = set(sig.parameters) - {"self"}
    assert param_names == {"signal_id", "reason"}
    for forbidden in ("quantity", "stop", "target", "price", "approved", "size"):
        assert forbidden not in param_names


def test_reject_pending_signature_has_no_execution_override_parameters():
    sig = inspect.signature(LiveSimPipeline.reject_pending)
    param_names = set(sig.parameters) - {"self"}
    assert param_names == {"signal_id", "reason"}


def test_calling_approve_pending_with_a_quantity_kwarg_raises_typeerror():
    """The literal attack this test proves impossible: approve(quantity=100000, stop=0, target=999999)."""
    with pytest.raises(TypeError):
        LiveSimPipeline.approve_pending(
            object(), signal_id="anything", quantity=100_000, stop=0, target=999_999,  # type: ignore[call-arg]
        )


def test_calling_reject_pending_with_execution_kwargs_raises_typeerror():
    with pytest.raises(TypeError):
        LiveSimPipeline.reject_pending(object(), signal_id="anything", quantity=100_000)  # type: ignore[call-arg]


def test_approved_execution_uses_the_signals_own_immutable_price_levels(tmp_path):
    """End-to-end reinforcement: even with a fully real pending approval,
    the executed order's stop/target come from the ORIGINAL frozen Signal
    -- there is no code path between PENDING_HUMAN_APPROVAL and EXECUTED
    that reads a stop/target/quantity from anywhere other than that Signal
    and a fresh RiskEngine evaluation."""
    from datetime import datetime

    from live.freshness import FreshnessPolicy
    from live.mock_source import MockMarketDataSource
    from live.state_store import LiveStateStore
    from paper.engine import PaperTradingEngine
    from paper.store import PaperStore
    from strategy.baseline import TrendMomentumBaseline
    from tests.conftest import AAPL_CACHE_PATH, real_aapl_mock_script

    if not AAPL_CACHE_PATH.exists():
        pytest.skip(f"No cached AAPL data at {AAPL_CACHE_PATH}")

    script = real_aapl_mock_script()
    store = PaperStore(tmp_path / "p.db")
    engine = PaperTradingEngine(store, initial_capital=100_000.0)
    pipeline = LiveSimPipeline(
        source=MockMarketDataSource(script), engine=engine, strategy=TrendMomentumBaseline(), symbols=["AAPL"], interval="1d",
        require_human_approval=True, state_store=LiveStateStore(tmp_path / "s.db"),
        freshness_policy=FreshnessPolicy(multiplier=1_000_000.0), clock=lambda: datetime(2026, 8, 26),
    )
    result = None
    while True:
        result = pipeline.process_next()
        if result.kind in ("PENDING_HUMAN_APPROVAL", "FEED_EXHAUSTED"):
            break
    assert result.kind == "PENDING_HUMAN_APPROVAL"
    original_signal = result.signal

    action = pipeline.approve_pending(original_signal.stable_id())
    assert action.outcome.value == "APPROVED"

    order = store.get_pending_order("AAPL")
    assert order.stop_price == original_signal.stop_price
    assert order.target_price == original_signal.target_price
    assert order.requested_price == original_signal.reference_price
