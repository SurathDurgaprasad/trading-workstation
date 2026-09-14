"""Autonomous hardening cycle 36 -- tests for live/prediction_recorder.py,
the new bridge between LiveSimPipeline's real-time signal generation and
predictions/'s existing immutable prediction ledger + outcome-resolution
engine. See that module's own docstring for the architectural gap this
closes.
"""
from datetime import datetime, timedelta

import pytest

from live.freshness import FreshnessPolicy
from live.mock_source import MockMarketDataSource, MockScriptEvent, make_mock_bar
from live.pipeline import LiveSimPipeline
from live.prediction_recorder import evaluate_pending_predictions, record_prediction_for_signal
from market.data_provider import OHLCV, MarketDataError, OHLCVBar
from paper.engine import PaperTradingEngine
from paper.store import PaperStore
from predictions.errors import DuplicatePredictionError
from predictions.models import PredictionOutcomeState
from predictions.store import PredictionStore
from strategy.signal import ReasonCode, Side, Signal


def _qualifying_bar(day, hour=9, minute=15, **overrides):
    base = dict(timestamp=datetime(2026, 1, day, hour, minute), open=100.0, high=101.0, low=99.0, close=100.0, volume=1_000_000.0)
    base.update(overrides)
    return make_mock_bar(**base)


class _ScriptedStrategy:
    """Fires a fixed LONG Signal on every call -- deterministic, matches
    tests/test_live_pipeline.py's own established double for this exact
    purpose."""

    name = "scripted_test_strategy"
    version = "1.0"

    def __init__(self, *, stop_price: float = 95.0, target_price: float = 110.0, side: Side = Side.LONG):
        self._stop_price = stop_price
        self._target_price = target_price
        self._side = side

    def generate_signal(self, indicator_series, index, symbol):
        row = indicator_series.iloc[index]
        return Signal(
            symbol=symbol, generated_at=indicator_series.index[index], side=self._side,
            reference_price=float(row["close"]), stop_price=self._stop_price, target_price=self._target_price,
            risk_reward=2.0, strategy_name=self.name, reason_codes=[ReasonCode.TREND_CONFIRMED],
        )


def _pipeline(script, *, tmp_path, require_human_approval=True, strategy=None):
    store = PaperStore(tmp_path / "p.db")
    engine = PaperTradingEngine(store, initial_capital=100_000.0)
    pipeline = LiveSimPipeline(
        source=MockMarketDataSource(script), engine=engine, strategy=strategy or _ScriptedStrategy(), symbols=["TEST"], interval="1m",
        require_human_approval=require_human_approval, freshness_policy=FreshnessPolicy(multiplier=1_000_000.0),
        clock=lambda: datetime(2026, 1, 1, 9, 20),
    )
    return pipeline, engine, store


def test_a_pending_human_approval_signal_gets_an_immutable_prediction_recorded(tmp_path):
    bar = _qualifying_bar(1)
    script = [MockScriptEvent.bar_event("TEST", bar)]
    pipeline, engine, store = _pipeline(script, tmp_path=tmp_path)
    prediction_store = PredictionStore(tmp_path / "predictions.db")

    result = pipeline.process_next()
    assert result.kind == "PENDING_HUMAN_APPROVAL"

    prediction = record_prediction_for_signal(result, pipeline=pipeline, engine=engine, prediction_store=prediction_store, horizon_bars=20)

    assert prediction is not None
    assert prediction.symbol == "TEST"
    assert prediction.entry_price == pytest.approx(100.0)
    assert prediction.stop_price == pytest.approx(95.0)
    assert prediction.target_price == pytest.approx(110.0)
    assert prediction.horizon_bars == 20
    assert prediction.interval == "1m"
    # Honest provenance: this signal never went through a scan.
    assert prediction.risk_decision is not None
    assert prediction.risk_decision.approved is True  # a real, freshly-computed RiskEngine result

    stored = prediction_store.get_prediction(prediction.prediction_id)
    assert stored == prediction
    prediction_store.close()


def test_a_critic_rejected_signal_still_gets_recorded_as_a_no_trade_data_point(tmp_path):
    """Mission requirement: a vetoed signal is exactly as valuable a
    research data point as an executed one -- recording must not be
    gated on the signal having survived every downstream gate."""
    from critic.models import CriticAssessment, CriticVerdict
    from live.critic_gate import CriticGateResult

    bar = _qualifying_bar(1)
    script = [MockScriptEvent.bar_event("TEST", bar)]
    blocking_assessment = CriticAssessment(
        verdict=CriticVerdict.REJECT, checks=(), failed_checks=("KILL_SWITCH",),
        warnings=(), reasons=["test rejection"], config_version="test",
    )

    class _FakeCriticGate:
        def evaluate(self, signal, **kwargs):
            return CriticGateResult(blocked=True, block_reason="test rejection", assessment=blocking_assessment, decision=None)

    store = PaperStore(tmp_path / "p.db")
    engine = PaperTradingEngine(store, initial_capital=100_000.0)
    pipeline = LiveSimPipeline(
        source=MockMarketDataSource(script), engine=engine, strategy=_ScriptedStrategy(), symbols=["TEST"], interval="1m",
        critic_gate=_FakeCriticGate(), freshness_policy=FreshnessPolicy(multiplier=1_000_000.0),
        clock=lambda: datetime(2026, 1, 1, 9, 20),
    )
    prediction_store = PredictionStore(tmp_path / "predictions.db")

    result = pipeline.process_next()
    assert result.kind == "CRITIC_REJECTED"
    assert result.signal is not None

    prediction = record_prediction_for_signal(result, pipeline=pipeline, engine=engine, prediction_store=prediction_store, horizon_bars=20)

    assert prediction is not None
    assert prediction.critic_assessment is blocking_assessment
    prediction_store.close()


def test_the_same_signal_is_never_recorded_twice(tmp_path, caplog):
    import logging

    bar = _qualifying_bar(1)
    script = [MockScriptEvent.bar_event("TEST", bar), MockScriptEvent.bar_event("TEST", bar)]
    pipeline, engine, store = _pipeline(script, tmp_path=tmp_path)
    prediction_store = PredictionStore(tmp_path / "predictions.db")

    first_result = pipeline.process_next()
    assert first_result.kind == "PENDING_HUMAN_APPROVAL"
    first = record_prediction_for_signal(first_result, pipeline=pipeline, engine=engine, prediction_store=prediction_store, horizon_bars=20)
    assert first is not None

    # Call the recorder a second time with the SAME result object directly
    # -- proves the recorder's own duplicate-prevention independent of
    # whatever bar-delivery scenario would realistically trigger it.
    with caplog.at_level(logging.WARNING, logger="live.prediction_recorder"):
        second = record_prediction_for_signal(first_result, pipeline=pipeline, engine=engine, prediction_store=prediction_store, horizon_bars=20)
    assert second is None  # DuplicatePredictionError caught internally, not re-raised

    assert len(prediction_store.list_predictions_for_symbol("TEST")) == 1
    # An expected, already-recorded duplicate must never be logged as a
    # failure (only the generic best-effort handler logs an exception;
    # the dedicated DuplicatePredictionError branch does not).
    assert not any(r.levelno >= logging.WARNING for r in caplog.records), \
        f"a duplicate prediction must not be logged as an error/warning: {[r.message for r in caplog.records]}"
    prediction_store.close()


def test_a_non_long_signal_is_skipped_not_crashed(tmp_path):
    bar = _qualifying_bar(1)
    script = [MockScriptEvent.bar_event("TEST", bar)]
    pipeline, engine, store = _pipeline(script, tmp_path=tmp_path, strategy=_ScriptedStrategy(side=Side.SHORT))
    prediction_store = PredictionStore(tmp_path / "predictions.db")

    result = pipeline.process_next()
    assert result.signal is not None
    assert result.signal.side == Side.SHORT

    prediction = record_prediction_for_signal(result, pipeline=pipeline, engine=engine, prediction_store=prediction_store, horizon_bars=20)

    assert prediction is None
    assert prediction_store.list_predictions_for_symbol("TEST") == []
    prediction_store.close()


def test_no_signal_this_call_returns_none_cleanly(tmp_path):
    pipeline, engine, store = _pipeline([], tmp_path=tmp_path)
    prediction_store = PredictionStore(tmp_path / "predictions.db")

    result = pipeline.process_next()
    assert result.kind == "FEED_EXHAUSTED"
    assert result.signal is None

    prediction = record_prediction_for_signal(result, pipeline=pipeline, engine=engine, prediction_store=prediction_store, horizon_bars=20)
    assert prediction is None
    prediction_store.close()


def test_a_recording_failure_never_raises_into_the_caller(tmp_path, monkeypatch):
    """The mission's own explicit requirement: recording is best-effort
    observability and must never break the real trading loop."""
    bar = _qualifying_bar(1)
    script = [MockScriptEvent.bar_event("TEST", bar)]
    pipeline, engine, store = _pipeline(script, tmp_path=tmp_path)
    prediction_store = PredictionStore(tmp_path / "predictions.db")

    def _broken_save(prediction):
        raise RuntimeError("simulated disk-full or corruption during prediction persistence")

    monkeypatch.setattr(prediction_store, "save_prediction", _broken_save)

    result = pipeline.process_next()
    assert result.kind == "PENDING_HUMAN_APPROVAL"

    # Must not raise.
    outcome = record_prediction_for_signal(result, pipeline=pipeline, engine=engine, prediction_store=prediction_store, horizon_bars=20)
    assert outcome is None
    prediction_store.close()


# --- evaluate_pending_predictions -------------------------------------------
# Real-time strategy validation mission, Phase C: closes the "recorded but
# never resolved without a separate manual `evaluate` invocation" gap --
# see evaluate_pending_predictions's own docstring.


def _ohlcv_bars(entries: list[tuple[datetime, float, float, float]]) -> list[OHLCVBar]:
    return [
        OHLCVBar(timestamp=ts, open=close, high=high, low=low, close=close, volume=1_000_000.0)
        for ts, high, low, close in entries
    ]


class _StubProvider:
    """Returns a fixed OHLCV regardless of symbol -- records every
    (period, interval) it was called with, so a test can prove
    evaluate_pending_predictions actually forwards the corrected period
    (predictions.tracker.resolution_period_for_interval), not just that
    the helper function computes the right string in isolation."""

    def __init__(self, ohlcv: OHLCV | None = None, error: Exception | None = None):
        self._ohlcv = ohlcv
        self._error = error
        self.calls: list[tuple[str, str]] = []

    def fetch_ohlcv(self, symbol, *, period="1y", interval="1d"):
        self.calls.append((period, interval))
        if self._error is not None:
            raise self._error
        return self._ohlcv


def _recorded_prediction(tmp_path, *, day=1):
    """Records one real PredictionRecord through the same pipeline ->
    record_prediction_for_signal path the earlier tests in this file
    already exercise, so evaluate_pending_predictions is tested against a
    genuinely recorded prediction, not a hand-built one."""
    bar = _qualifying_bar(day)
    script = [MockScriptEvent.bar_event("TEST", bar)]
    pipeline, engine, store = _pipeline(script, tmp_path=tmp_path)
    prediction_store = PredictionStore(tmp_path / "predictions.db")

    result = pipeline.process_next()
    assert result.kind == "PENDING_HUMAN_APPROVAL"
    prediction = record_prediction_for_signal(result, pipeline=pipeline, engine=engine, prediction_store=prediction_store, horizon_bars=20)
    assert prediction is not None
    return prediction, prediction_store


def test_evaluate_pending_predictions_resolves_and_persists_a_target_hit(tmp_path):
    prediction, prediction_store = _recorded_prediction(tmp_path)
    # entry_time = 2026-01-01 09:15 (naive), target=110.0 -- one later bar
    # whose range reaches it.
    ohlcv = OHLCV(symbol="TEST", interval="1m", bars=_ohlcv_bars([
        (datetime(2026, 1, 1, 9, 16), 112.0, 108.0, 111.0),
    ]))
    provider = _StubProvider(ohlcv)

    evaluated = evaluate_pending_predictions(prediction_store, provider=provider)

    assert evaluated == 1
    assert prediction_store.list_predictions_needing_evaluation() == []
    evaluations = prediction_store.list_all_evaluations()
    assert len(evaluations) == 1
    assert evaluations[0].outcome == PredictionOutcomeState.TARGET_HIT
    prediction_store.close()


def test_evaluate_pending_predictions_forwards_the_corrected_intraday_period(tmp_path):
    """The recorded prediction's interval is "1m" (this file's own
    _pipeline() default) -- evaluate_pending_predictions must never pass
    the raw default period ("1y") straight through to the provider, or
    every live-recorded prediction would silently never resolve (the
    real, empirically-confirmed Yahoo Finance defect
    predictions.tracker.resolution_period_for_interval fixes)."""
    _, prediction_store = _recorded_prediction(tmp_path)
    ohlcv = OHLCV(symbol="TEST", interval="1m", bars=[])
    provider = _StubProvider(ohlcv)

    evaluate_pending_predictions(prediction_store, provider=provider, requested_period="1y")

    assert provider.calls == [("7d", "1m")]
    prediction_store.close()


def test_evaluate_pending_predictions_isolates_one_predictions_failure_from_the_rest(tmp_path):
    first, prediction_store = _recorded_prediction(tmp_path, day=1)
    second, _ = _recorded_prediction(tmp_path, day=2)
    assert first.prediction_id != second.prediction_id

    class _FirstSymbolFailsProvider:
        def __init__(self):
            self.calls = 0

        def fetch_ohlcv(self, symbol, *, period="1y", interval="1d"):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("simulated unexpected provider failure -- not a MarketDataError")
            return OHLCV(symbol=symbol, interval="1m", bars=[])

    provider = _FirstSymbolFailsProvider()

    evaluated = evaluate_pending_predictions(prediction_store, provider=provider)

    # One failed (unexpected exception, isolated -- stays pending), one
    # succeeded (returned ACTIVE, since no bars were supplied -- also
    # still pending, but WAS evaluated and persisted this cycle).
    assert evaluated == 1
    assert provider.calls == 2
    prediction_store.close()


def test_evaluate_pending_predictions_never_raises_when_listing_itself_fails(tmp_path, monkeypatch):
    _, prediction_store = _recorded_prediction(tmp_path)

    def _broken_list(limit=200):
        raise RuntimeError("simulated database corruption")

    monkeypatch.setattr(prediction_store, "list_predictions_needing_evaluation", _broken_list)

    evaluated = evaluate_pending_predictions(prediction_store, provider=_StubProvider(OHLCV(symbol="TEST", interval="1m", bars=[])))

    assert evaluated == 0
    prediction_store.close()
