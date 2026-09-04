from datetime import datetime, timedelta, timezone

import pytest

from decision_engine.models import Decision, DecisionLabel, RiskContext
from market.data_provider import OHLCV, MarketDataError, OHLCVBar
from market_intelligence.models import CandidateScore
from predictions.errors import PredictionUnavailableError
from predictions.models import PredictionEvaluation, PredictionOutcomeState
from predictions.tracker import create_prediction, evaluate_prediction, summarize_predictions
from strategy.signal import ReasonCode, Side, Signal

_START = datetime(2024, 1, 2)


def _bars(highs_lows: list[tuple[float, float]]) -> list[OHLCVBar]:
    bars = []
    for i, (high, low) in enumerate(highs_lows):
        close = (high + low) / 2
        bars.append(OHLCVBar(timestamp=_START + timedelta(days=i), open=close, high=high, low=low, close=close, volume=1000.0))
    return bars


def _ohlcv(symbol: str, highs_lows: list[tuple[float, float]]) -> OHLCV:
    return OHLCV(symbol=symbol, interval="1d", bars=_bars(highs_lows))


class _FakeProvider:
    def __init__(self, ohlcv: OHLCV | None = None, error: Exception | None = None):
        self._ohlcv = ohlcv
        self._error = error

    def fetch_ohlcv(self, symbol, *, period="1y", interval="1d"):
        if self._error is not None:
            raise self._error
        return self._ohlcv


def _candidate() -> CandidateScore:
    return CandidateScore(
        symbol="AAPL", as_of=_START, last_close=100.0, avg_daily_value=1_000_000.0,
        volume_ratio=1.1, trend_score=1.0, momentum_score=0.5, breakout_score=0.01,
        relative_strength_score=0.02, sector_strength_score=None, composite_score=1.5,
        explanation=["fake"],
    )


def _decision(label: DecisionLabel = DecisionLabel.BUY, symbol: str = "AAPL") -> Decision:
    return Decision(
        decision_id="dec-1", symbol=symbol, as_of=datetime(2024, 1, 2, 12, 0, 0, tzinfo=timezone.utc), label=label,
        rationale=["fake"], config_version="cfg1",
        scanner_evidence=_candidate() if label != DecisionLabel.NO_ACTION else None,
        research_evidence=None, market_context=None, risk_context=RiskContext.unknown(),
        narrative=None, narrative_unavailable_reason=None,
    )


def _signal(symbol: str = "AAPL", entry_price: float = 100.0, stop_price: float = 95.0, target_price: float = 110.0) -> Signal:
    return Signal(
        symbol=symbol, generated_at=_START, side=Side.LONG, reference_price=entry_price,
        stop_price=stop_price, target_price=target_price, risk_reward=2.0,
        strategy_name="decision_engine_buy_bridge", reason_codes=[ReasonCode.DECISION_ENGINE_SCORED],
    )


def _prediction(*, horizon_bars: int = 20, entry_price=100.0, stop_price=95.0, target_price=110.0):
    return create_prediction(_decision(), _signal(entry_price=entry_price, stop_price=stop_price, target_price=target_price), horizon_bars=horizon_bars)


# --- create_prediction ------------------------------------------------------


def test_create_prediction_carries_forward_the_signals_price_levels():
    prediction = _prediction()
    assert prediction.symbol == "AAPL"
    assert prediction.decision_id == "dec-1"
    assert prediction.entry_price == 100.0
    assert prediction.stop_price == 95.0
    assert prediction.target_price == 110.0
    assert prediction.label == DecisionLabel.BUY


@pytest.mark.parametrize("label", [DecisionLabel.WATCH, DecisionLabel.AVOID, DecisionLabel.EXIT, DecisionLabel.NO_ACTION])
def test_create_prediction_rejects_every_non_buy_label(label):
    with pytest.raises(PredictionUnavailableError):
        create_prediction(_decision(label), _signal())


def test_create_prediction_rejects_mismatched_symbols():
    with pytest.raises(PredictionUnavailableError):
        create_prediction(_decision(symbol="AAPL"), _signal(symbol="MSFT"))


def test_create_prediction_leaves_risk_decision_none_by_default():
    prediction = create_prediction(_decision(), _signal())
    assert prediction.risk_decision is None


def test_create_prediction_persists_a_real_risk_decision_when_given_one():
    """Mission auditability requirement: create_prediction never computes
    sizing itself (stays a pure carry-forward), but must faithfully
    persist a real risk.contracts.RiskDecision the caller already
    computed via risk.sizing.size_decision."""
    from market.context import MarketContext
    from risk.account import new_account
    from risk.sizing import size_decision

    decision = _decision()
    market_context = MarketContext(symbol="AAPL", as_of=_START, price=100.0, atr_14=2.5)
    account = new_account(20_000.0)
    risk_decision = size_decision(decision, market_context=market_context, account=account)

    prediction = create_prediction(decision, _signal(), risk_decision=risk_decision)

    assert prediction.risk_decision is not None
    assert prediction.risk_decision.account_equity == 20_000.0
    assert prediction.risk_decision == risk_decision  # exact carry-forward, not a re-derivation


def test_prediction_record_with_risk_decision_round_trips_through_json():
    """The risk_decision field must survive PredictionStore's own
    model_dump_json()/model_validate_json() persistence round trip --
    the actual mechanism that makes it a real audit record, not just an
    in-memory convenience."""
    from market.context import MarketContext
    from risk.account import new_account
    from risk.sizing import size_decision

    decision = _decision()
    market_context = MarketContext(symbol="AAPL", as_of=_START, price=100.0, atr_14=2.5)
    risk_decision = size_decision(decision, market_context=market_context, account=new_account(20_000.0))
    prediction = create_prediction(decision, _signal(), risk_decision=risk_decision)

    from predictions.models import PredictionRecord

    restored = PredictionRecord.model_validate_json(prediction.model_dump_json())
    assert restored.risk_decision is not None
    assert restored.risk_decision.position_size.quantity == risk_decision.position_size.quantity
    assert restored == prediction


# --- evaluate_prediction -----------------------------------------------------


def test_evaluate_prediction_target_hit():
    # bar 0 = entry bar (excluded); bar 1 hits target, no stop touch
    provider = _FakeProvider(_ohlcv("AAPL", [(101.0, 99.0), (112.0, 101.0)]))
    prediction = _prediction(horizon_bars=5)

    evaluation = evaluate_prediction(prediction, provider=provider)

    assert evaluation.outcome == PredictionOutcomeState.TARGET_HIT
    assert evaluation.bars_observed == 1
    assert evaluation.exit_price == 110.0
    assert evaluation.actual_return == pytest.approx(0.10)


def test_evaluate_prediction_stop_hit():
    provider = _FakeProvider(_ohlcv("AAPL", [(101.0, 99.0), (103.0, 93.0)]))
    prediction = _prediction(horizon_bars=5)

    evaluation = evaluate_prediction(prediction, provider=provider)

    assert evaluation.outcome == PredictionOutcomeState.STOP_HIT
    assert evaluation.exit_price == 95.0
    assert evaluation.actual_return == pytest.approx(-0.05)


def test_evaluate_prediction_same_bar_ambiguity_reuses_check_exits_stop_wins_rule():
    # A single bar whose range spans BOTH target and stop -- proves this
    # module reuses backtesting.execution.check_exit's own conservative
    # rule rather than a differently-behaved reimplementation.
    provider = _FakeProvider(_ohlcv("AAPL", [(101.0, 99.0), (115.0, 90.0)]))
    prediction = _prediction(horizon_bars=5)

    evaluation = evaluate_prediction(prediction, provider=provider)

    assert evaluation.outcome == PredictionOutcomeState.STOP_HIT


def test_evaluate_prediction_never_resolves_against_the_entry_bar_itself():
    """Real look-ahead-adjacent boundary this project's existing tests never
    actually exercised: evaluate_prediction's own guard is
    `subsequent = frame[frame.index > prediction.entry_time]` (strict `>`,
    excluding the entry bar). Every existing target/stop test's own bar 0
    happens to be harmless regardless of whether it's included or excluded
    (its range never touches stop/target) -- so a regression changing `>`
    to `>=` would pass the entire existing suite silently. This test's bar
    0 (timestamp == entry_time exactly, since _bars() starts at _START and
    _signal()'s generated_at is also _START) deliberately has a low of 50.0
    -- catastrophically below stop_price=95.0 -- so an evaluation that
    wrongly includes it would immediately report STOP_HIT at bar 1 with
    exit_price=95.0. The correct, entry-bar-excluding evaluation must
    instead resolve TARGET_HIT from the later, genuinely-subsequent bars.

    Verified this test is meaningful (not vacuous) by temporarily changing
    `>` to `>=` in predictions/tracker.py and confirming it then failed
    with STOP_HIT/bars_observed=1, before restoring the real guard."""
    provider = _FakeProvider(_ohlcv("AAPL", [
        (101.0, 50.0),    # bar 0 == entry_time exactly -- must be excluded
        (105.0, 99.0),    # bar 1: genuinely subsequent, no hit
        (112.0, 101.0),   # bar 2: genuinely subsequent, hits target
    ]))
    prediction = _prediction(horizon_bars=5)

    evaluation = evaluate_prediction(prediction, provider=provider)

    assert evaluation.outcome == PredictionOutcomeState.TARGET_HIT
    assert evaluation.bars_observed == 2
    assert evaluation.exit_price == 110.0


def test_evaluate_prediction_expired_when_horizon_reached_with_no_hit():
    provider = _FakeProvider(_ohlcv("AAPL", [(101.0, 99.0), (102.0, 98.0), (103.0, 97.0), (104.0, 96.0)]))
    prediction = _prediction(horizon_bars=3)

    evaluation = evaluate_prediction(prediction, provider=provider)

    assert evaluation.outcome == PredictionOutcomeState.EXPIRED
    assert evaluation.bars_observed == 3
    assert evaluation.exit_price is None
    assert evaluation.actual_return is None


def test_evaluate_prediction_hit_on_the_exact_horizon_bar_takes_priority_over_expiration():
    # horizon_bars=3, and bar 3 (the last allowed bar) is the one that hits
    # target -- must report TARGET_HIT, not EXPIRED.
    provider = _FakeProvider(_ohlcv("AAPL", [(101.0, 99.0), (102.0, 98.0), (103.0, 97.0), (112.0, 101.0)]))
    prediction = _prediction(horizon_bars=3)

    evaluation = evaluate_prediction(prediction, provider=provider)

    assert evaluation.outcome == PredictionOutcomeState.TARGET_HIT
    assert evaluation.bars_observed == 3


def test_evaluate_prediction_active_when_bars_run_out_before_horizon_or_a_hit():
    provider = _FakeProvider(_ohlcv("AAPL", [(101.0, 99.0), (102.0, 98.0)]))
    prediction = _prediction(horizon_bars=20)

    evaluation = evaluate_prediction(prediction, provider=provider)

    assert evaluation.outcome == PredictionOutcomeState.ACTIVE
    assert evaluation.bars_observed == 1


def test_evaluate_prediction_active_with_zero_bars_observed_when_none_exist_yet():
    # Only the entry bar itself exists in the fetched history -- nothing
    # strictly after it yet. Must not crash; must report ACTIVE, bars_observed=0.
    provider = _FakeProvider(_ohlcv("AAPL", [(101.0, 99.0)]))
    prediction = _prediction(horizon_bars=20)

    evaluation = evaluate_prediction(prediction, provider=provider)

    assert evaluation.outcome == PredictionOutcomeState.ACTIVE
    assert evaluation.bars_observed == 0
    assert evaluation.max_favorable_excursion == 0.0
    assert evaluation.max_adverse_excursion == 0.0


def test_evaluate_prediction_insufficient_data_on_fetch_failure():
    provider = _FakeProvider(error=MarketDataError("simulated outage"))
    prediction = _prediction()

    evaluation = evaluate_prediction(prediction, provider=provider)

    assert evaluation.outcome == PredictionOutcomeState.INSUFFICIENT_DATA
    assert "simulated outage" in evaluation.detail


def test_evaluate_prediction_tracks_max_favorable_and_adverse_excursion():
    # bar1: up to 106 (favorable +6%), down to 99 (adverse +1%); bar2: hits target
    provider = _FakeProvider(_ohlcv("AAPL", [(101.0, 99.0), (106.0, 99.0), (112.0, 101.0)]))
    prediction = _prediction(horizon_bars=5)

    evaluation = evaluate_prediction(prediction, provider=provider)

    assert evaluation.outcome == PredictionOutcomeState.TARGET_HIT
    assert evaluation.max_favorable_excursion == pytest.approx(0.12)  # from bar2's high=112


# --- Phase 36: corporate-action / data-anomaly guard --------------------------


def test_evaluate_prediction_flags_an_implausible_single_bar_gap_as_insufficient_data():
    """A ~55% overnight drop with no preceding gradual decline is far
    beyond ordinary equity volatility -- consistent with an unadjusted
    stock split, not a genuine stop-hit. Must not be silently resolved
    as STOP_HIT."""
    provider = _FakeProvider(_ohlcv("AAPL", [(101.0, 99.0), (46.0, 44.0)]))  # bar1 normal, bar2 collapses relative to bar1's ~100 close
    prediction = _prediction(horizon_bars=20)

    evaluation = evaluate_prediction(prediction, provider=provider)

    assert evaluation.outcome == PredictionOutcomeState.INSUFFICIENT_DATA
    assert "implausible" in evaluation.detail
    assert "split" in evaluation.detail


def test_evaluate_prediction_does_not_flag_a_gradual_decline_over_many_bars():
    """A genuine, if severe, multi-bar decline (each individual bar-to-bar
    step well under the anomaly threshold) must resolve normally -- only
    a SUDDEN single-bar jump is an anomaly, not a large cumulative move."""
    # 100 -> ~60 over 10 bars, each bar roughly -4.5% from the prior close -- ordinary bad price action, not a split.
    bars = [(100.0 - i * 4.0, 100.0 - i * 4.0 - 2.0) for i in range(1, 11)]
    provider = _FakeProvider(_ohlcv("AAPL", bars))
    prediction = _prediction(stop_price=65.0, target_price=200.0, horizon_bars=20)  # within reach of the decline (lowest low ~58), so STOP_HIT resolves it, not the guard

    evaluation = evaluate_prediction(prediction, provider=provider)

    assert evaluation.outcome == PredictionOutcomeState.STOP_HIT  # resolved normally, never flagged as an anomaly


def test_evaluate_prediction_flags_an_implausible_single_bar_spike_upward():
    provider = _FakeProvider(_ohlcv("AAPL", [(101.0, 99.0), (170.0, 165.0)]))  # bar2 spikes ~65% above bar1's ~100 close
    prediction = _prediction(horizon_bars=20)

    evaluation = evaluate_prediction(prediction, provider=provider)

    assert evaluation.outcome == PredictionOutcomeState.INSUFFICIENT_DATA


def test_evaluate_prediction_anomaly_guard_never_fabricates_a_return():
    provider = _FakeProvider(_ohlcv("AAPL", [(101.0, 99.0), (46.0, 44.0)]))
    prediction = _prediction(horizon_bars=20)

    evaluation = evaluate_prediction(prediction, provider=provider)

    assert evaluation.actual_return is None
    assert evaluation.exit_price is None


# --- summarize_predictions ---------------------------------------------------


def _eval(prediction_id, outcome, *, evaluated_at=None, actual_return=None):
    return PredictionEvaluation(
        evaluation_id=f"eval-{prediction_id}-{outcome.value}", prediction_id=prediction_id,
        evaluated_at=evaluated_at or datetime.now(timezone.utc), outcome=outcome, bars_observed=1,
        exit_time=None, exit_price=None, actual_return=actual_return,
        max_favorable_excursion=0.0, max_adverse_excursion=0.0, detail="test",
    )


def test_summarize_predictions_computes_win_rate_and_average_return():
    evaluations = [
        _eval("p1", PredictionOutcomeState.TARGET_HIT, actual_return=0.10),
        _eval("p2", PredictionOutcomeState.STOP_HIT, actual_return=-0.05),
        _eval("p3", PredictionOutcomeState.ACTIVE),
    ]
    summary = summarize_predictions(evaluations)

    assert summary.total_predictions == 3
    assert summary.target_hit == 1
    assert summary.stop_hit == 1
    assert summary.active == 1
    assert summary.win_rate == pytest.approx(0.5)
    assert summary.average_return == pytest.approx(0.025)
    assert summary.profit_factor == pytest.approx(0.10 / 0.05)


def test_summarize_predictions_handles_zero_resolved_predictions():
    evaluations = [_eval("p1", PredictionOutcomeState.ACTIVE), _eval("p2", PredictionOutcomeState.EXPIRED)]
    summary = summarize_predictions(evaluations)

    assert summary.win_rate is None
    assert summary.average_return is None
    assert summary.profit_factor is None


def test_summarize_predictions_handles_empty_input():
    summary = summarize_predictions([])
    assert summary.total_predictions == 0
    assert summary.win_rate is None


def test_summarize_predictions_uses_only_the_latest_evaluation_per_prediction():
    older = _eval("p1", PredictionOutcomeState.ACTIVE, evaluated_at=datetime(2024, 1, 1, tzinfo=timezone.utc))
    newer = _eval("p1", PredictionOutcomeState.TARGET_HIT, evaluated_at=datetime(2024, 1, 5, tzinfo=timezone.utc), actual_return=0.08)

    summary = summarize_predictions([older, newer])

    assert summary.total_predictions == 1
    assert summary.target_hit == 1
    assert summary.active == 0
    assert summary.average_return == pytest.approx(0.08)


def test_summarize_predictions_profit_factor_is_none_with_no_losses():
    evaluations = [_eval("p1", PredictionOutcomeState.TARGET_HIT, actual_return=0.10)]
    summary = summarize_predictions(evaluations)
    assert summary.profit_factor is None
