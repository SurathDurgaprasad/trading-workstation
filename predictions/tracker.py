"""Phase 23 -- shadow prediction recording and outcome monitoring.

create_prediction turns a BUY Decision + the Signal risk.sizing built for
it into a trackable PredictionRecord -- no new price-level math, just
carrying forward what Phase 22 already computed.

evaluate_prediction reuses backtesting.execution.check_exit and
OpenPosition DIRECTLY for the same-bar-ambiguity stop/target check
("if a single bar's range could have hit both, assume the stop was hit
first") -- this is a deliberate reuse of already-tested logic, not a
second, competing implementation of that rule.

Nothing here places a trade. This module only reads historical market
data (via the existing MarketDataProvider Protocol) to see what
subsequently happened to a price level that was already recorded.
"""

from datetime import datetime, timezone

import pandas as pd

from backtesting.execution import OpenPosition, check_exit
from backtesting.trade import ExitReason
from decision_engine.models import Decision, DecisionLabel
from market.data_provider import MarketDataError, MarketDataProvider
from predictions.errors import PredictionUnavailableError
from predictions.models import PredictionEvaluation, PredictionOutcomeState, PredictionRecord, PredictionSummary
from risk.contracts import RiskDecision
from strategy.signal import ReasonCode, Side, Signal


def create_prediction(
    decision: Decision,
    signal: Signal,
    *,
    horizon_bars: int = 20,
    interval: str = "1d",
    now: datetime | None = None,
    risk_decision: RiskDecision | None = None,
) -> PredictionRecord:
    """`risk_decision` is OPTIONAL (see PredictionRecord.risk_decision's
    own docstring) -- when the caller has capital/risk-config to size
    against (predict/shadow-run's --initial-capital et al), pass the
    risk.sizing.size_decision(decision, market_context=..., account=...)
    result here to persist the full trade plan (quantity/capital/risk
    amount) alongside the prediction, not just print it and lose it.
    Never computed inside this function -- create_prediction stays a
    pure carry-forward of already-computed values, same posture as
    entry/stop/target above."""
    if decision.label != DecisionLabel.BUY:
        raise PredictionUnavailableError(
            f"Cannot record a trackable prediction for a {decision.label.value} decision -- "
            "only BUY has concrete price levels to monitor."
        )
    if decision.symbol != signal.symbol:
        raise PredictionUnavailableError(
            f"Decision symbol {decision.symbol!r} does not match signal symbol {signal.symbol!r}."
        )

    return PredictionRecord(
        prediction_id=PredictionRecord.new_id(),
        decision_id=decision.decision_id,
        symbol=decision.symbol,
        created_at=now or datetime.now(timezone.utc),
        label=decision.label,
        entry_price=signal.reference_price,
        stop_price=signal.stop_price,
        target_price=signal.target_price,
        entry_time=signal.generated_at,
        horizon_bars=horizon_bars,
        interval=interval,
        risk_decision=risk_decision,
    )


ANOMALOUS_BAR_GAP_THRESHOLD = 0.5
"""Phase 36 -- this project integrates no stock-split/dividend
adjustment source (YahooFinanceProvider fetches with auto_adjust=False).
A split between a prediction's entry and its evaluation would make the
raw, un-adjusted post-split price look like a catastrophic (and entirely
fabricated) move relative to the pre-split price the prior bar actually
closed at -- resolving that as a genuine STOP_HIT would be silently
wrong. 50% is a deliberately conservative threshold: even extreme
single-day news-driven equity moves rarely approach it, so this is
unlikely to misclassify genuine (if severe) price action as an anomaly,
while reliably catching the 2:1-or-larger splits/reverse-splits that
would otherwise corrupt an evaluation."""


def evaluate_prediction(
    prediction: PredictionRecord,
    *,
    provider: MarketDataProvider,
    period: str = "1y",
    now: datetime | None = None,
) -> PredictionEvaluation:
    eval_time = now or datetime.now(timezone.utc)

    try:
        ohlcv = provider.fetch_ohlcv(prediction.symbol, period=period, interval=prediction.interval)
    except MarketDataError as exc:
        return _evaluation(
            prediction, eval_time, outcome=PredictionOutcomeState.INSUFFICIENT_DATA, bars_observed=0,
            detail=f"Failed to fetch market data for {prediction.symbol}: {exc}",
        )

    frame = ohlcv.to_dataframe()
    subsequent = frame[frame.index > prediction.entry_time]

    if subsequent.empty:
        return _evaluation(
            prediction, eval_time, outcome=PredictionOutcomeState.ACTIVE, bars_observed=0,
            max_favorable_excursion=0.0, max_adverse_excursion=0.0,
            detail="No bars observed yet after the entry timestamp.",
        )

    position = _open_position(prediction)

    mfe = 0.0
    mae = 0.0
    bars_observed = 0
    previous_close = prediction.entry_price
    for timestamp, row in subsequent.iterrows():
        bars_observed += 1
        high, low, close = float(row["High"]), float(row["Low"]), float(row["Close"])

        # Corporate-action / data-anomaly guard -- see ANOMALOUS_BAR_GAP_THRESHOLD's
        # own docstring. Checked against the PREVIOUS bar's close (not the
        # original entry_price), so a genuine gradual decline over many bars
        # is never mistaken for a sudden anomaly -- only an implausible
        # bar-to-bar jump is.
        if low < previous_close * (1 - ANOMALOUS_BAR_GAP_THRESHOLD) or high > previous_close * (1 + ANOMALOUS_BAR_GAP_THRESHOLD):
            return _evaluation(
                prediction, eval_time, outcome=PredictionOutcomeState.INSUFFICIENT_DATA, bars_observed=bars_observed,
                max_favorable_excursion=mfe, max_adverse_excursion=mae,
                detail=(
                    f"Bar {bars_observed} shows an implausible >={ANOMALOUS_BAR_GAP_THRESHOLD:.0%} move from the "
                    f"previous close ({previous_close:.2f}) to this bar's range (low={low:.2f}, high={high:.2f}) -- "
                    "likely an unadjusted stock split/reverse-split or a data error, not resolved as a genuine target/stop hit."
                ),
            )

        mfe = max(mfe, (high - prediction.entry_price) / prediction.entry_price)
        mae = max(mae, (prediction.entry_price - low) / prediction.entry_price)

        result = check_exit(position, pd.Series({"high": high, "low": low}))
        if result is not None:
            exit_price, exit_reason = result
            outcome = PredictionOutcomeState.TARGET_HIT if exit_reason == ExitReason.TARGET else PredictionOutcomeState.STOP_HIT
            return _evaluation(
                prediction, eval_time, outcome=outcome, bars_observed=bars_observed,
                exit_time=_naive(timestamp), exit_price=exit_price,
                actual_return=exit_price / prediction.entry_price - 1,
                max_favorable_excursion=mfe, max_adverse_excursion=mae,
                detail=f"{exit_reason.value} at bar {bars_observed} of up to {prediction.horizon_bars}.",
            )

        if bars_observed >= prediction.horizon_bars:
            return _evaluation(
                prediction, eval_time, outcome=PredictionOutcomeState.EXPIRED, bars_observed=bars_observed,
                max_favorable_excursion=mfe, max_adverse_excursion=mae,
                detail=f"Neither target nor stop hit within the {prediction.horizon_bars}-bar horizon.",
            )

        previous_close = close

    return _evaluation(
        prediction, eval_time, outcome=PredictionOutcomeState.ACTIVE, bars_observed=bars_observed,
        max_favorable_excursion=mfe, max_adverse_excursion=mae,
        detail=f"Still open after {bars_observed} of up to {prediction.horizon_bars} bars -- not enough data yet to resolve.",
    )


def summarize_predictions(evaluations: list[PredictionEvaluation]) -> PredictionSummary:
    """Deduplicates to the LATEST evaluation per prediction_id first -- an
    older ACTIVE row for a since-resolved prediction must never be
    double-counted alongside its own later TARGET_HIT/STOP_HIT row."""
    latest_by_prediction: dict[str, PredictionEvaluation] = {}
    for evaluation in evaluations:
        current = latest_by_prediction.get(evaluation.prediction_id)
        if current is None or evaluation.evaluated_at > current.evaluated_at:
            latest_by_prediction[evaluation.prediction_id] = evaluation

    latest = list(latest_by_prediction.values())
    active = sum(1 for e in latest if e.outcome == PredictionOutcomeState.ACTIVE)
    target_hit = sum(1 for e in latest if e.outcome == PredictionOutcomeState.TARGET_HIT)
    stop_hit = sum(1 for e in latest if e.outcome == PredictionOutcomeState.STOP_HIT)
    expired = sum(1 for e in latest if e.outcome == PredictionOutcomeState.EXPIRED)
    insufficient_data = sum(1 for e in latest if e.outcome == PredictionOutcomeState.INSUFFICIENT_DATA)

    resolved_returns = [
        e.actual_return for e in latest
        if e.outcome in (PredictionOutcomeState.TARGET_HIT, PredictionOutcomeState.STOP_HIT) and e.actual_return is not None
    ]
    resolved_count = target_hit + stop_hit

    win_rate = (target_hit / resolved_count) if resolved_count > 0 else None
    average_return = (sum(resolved_returns) / len(resolved_returns)) if resolved_returns else None

    gains = sum(r for r in resolved_returns if r > 0)
    losses = sum(r for r in resolved_returns if r < 0)
    profit_factor = (gains / abs(losses)) if losses < 0 else None

    return PredictionSummary(
        total_predictions=len(latest), active=active, target_hit=target_hit, stop_hit=stop_hit,
        expired=expired, insufficient_data=insufficient_data,
        win_rate=win_rate, average_return=average_return, profit_factor=profit_factor,
    )


def _open_position(prediction: PredictionRecord) -> OpenPosition:
    risk_per_unit = prediction.entry_price - prediction.stop_price
    reward_per_unit = prediction.target_price - prediction.entry_price
    risk_reward = (reward_per_unit / risk_per_unit) if risk_per_unit > 0 else 0.0001

    dummy_signal = Signal(
        symbol=prediction.symbol, generated_at=prediction.entry_time, side=Side.LONG,
        reference_price=prediction.entry_price, stop_price=prediction.stop_price, target_price=prediction.target_price,
        risk_reward=max(risk_reward, 0.0001), strategy_name="prediction_tracker",
        reason_codes=[ReasonCode.DECISION_ENGINE_SCORED],
    )
    return OpenPosition(
        signal=dummy_signal, entry_time=prediction.entry_time, entry_price=prediction.entry_price,
        quantity=1, stop_price=prediction.stop_price, target_price=prediction.target_price,
    )


def _evaluation(
    prediction: PredictionRecord, eval_time: datetime, *, outcome: PredictionOutcomeState, bars_observed: int,
    exit_time: datetime | None = None, exit_price: float | None = None, actual_return: float | None = None,
    max_favorable_excursion: float | None = None, max_adverse_excursion: float | None = None, detail: str,
) -> PredictionEvaluation:
    return PredictionEvaluation(
        evaluation_id=PredictionEvaluation.new_id(), prediction_id=prediction.prediction_id, evaluated_at=eval_time,
        outcome=outcome, bars_observed=bars_observed, exit_time=exit_time, exit_price=exit_price,
        actual_return=actual_return, max_favorable_excursion=max_favorable_excursion,
        max_adverse_excursion=max_adverse_excursion, detail=detail,
    )


def _naive(value) -> datetime:
    if not isinstance(value, datetime):
        value = pd.Timestamp(value).to_pydatetime()
    if value.tzinfo is not None:
        value = value.replace(tzinfo=None)
    return value
