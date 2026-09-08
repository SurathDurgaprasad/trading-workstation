"""NSE PREDICTION ENGINE mission, Phase 5/6: outcome tracking for the
UP/DOWN/NO_EDGE directional forecast (decision_engine.direction.
classify_direction), completing the "PREDICTION != TRADE" loop the
mission's own Phase 4/6 explicitly asks for.

Deliberately a SEPARATE, much simpler record than predictions.models.
PredictionRecord: a directional forecast has no entry/stop/target price
levels (there is no trade plan behind it -- this project places no
short/sell-to-open order and must never grow a code path that looks
like it could), so it needs none of PredictionRecord's stop<entry<target
invariant, risk_decision, or critic_assessment machinery. It only needs
enough to later ask "which way did price actually move, and did that
match the forecast" -- a plain N-bar-forward return against the
forecast's own as_of close.

Same "write once, evaluations are separate append-only rows" convention
as predictions/models.py + predictions/store.py.
"""

import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict

from decision_engine.direction import DirectionalAssessment, DirectionLabel
from market.data_provider import MarketDataError, MarketDataProvider

ANOMALOUS_BAR_GAP_THRESHOLD = 0.5
"""Same corporate-action / data-anomaly guard as predictions/tracker.py's
own constant of the same name and value -- this project integrates no
stock-split/dividend adjustment source, so an unadjusted post-split price
must not be silently scored as a genuine, enormous directional move.
Not imported from predictions.tracker to avoid a forecast-tracking module
depending on the BUY-price-level tracker for one float constant -- the
two modules are deliberately independent, per this module's own
docstring above."""


class DirectionForecastRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    forecast_id: str
    symbol: str
    created_at: datetime
    """UTC-aware: when this forecast was recorded."""
    as_of: datetime
    """The bar this forecast's evidence was computed against (the
    CandidateScore.as_of it came from) -- monitoring only ever looks at
    bars strictly after this timestamp, same convention as
    PredictionRecord.entry_time."""

    direction: DirectionLabel
    confidence: float
    reference_price: float
    """The as_of bar's own close -- captured at creation time so
    evaluation only ever needs to fetch FORWARD bars, never re-derive
    this bar's price from a possibly-different later fetch."""

    horizon_bars: int
    interval: str
    scan_id: str | None = None
    """Correlates back to the market_intelligence.regime_store.
    MarketRegimeStore snapshot and ScanReport this forecast was made
    alongside, when known -- same field, same purpose as
    decision_engine.models.Decision.scan_id."""

    bullish_evidence: tuple[str, ...] = ()
    bearish_evidence: tuple[str, ...] = ()

    @classmethod
    def new_id(cls) -> str:
        return uuid.uuid4().hex

    @classmethod
    def from_assessment(
        cls, assessment: DirectionalAssessment, *, as_of: datetime, reference_price: float,
        horizon_bars: int = 5, interval: str = "1d", now: datetime | None = None, scan_id: str | None = None,
    ) -> "DirectionForecastRecord":
        return cls(
            forecast_id=cls.new_id(), symbol=assessment.symbol, created_at=now or datetime.now(timezone.utc),
            as_of=as_of, direction=assessment.label, confidence=assessment.confidence, reference_price=reference_price,
            horizon_bars=horizon_bars, interval=interval, scan_id=scan_id,
            bullish_evidence=assessment.bullish_evidence, bearish_evidence=assessment.bearish_evidence,
        )


class DirectionForecastEvaluation(BaseModel):
    model_config = ConfigDict(frozen=True)

    evaluation_id: str
    forecast_id: str
    evaluated_at: datetime

    resolved: bool
    """True once `horizon_bars` bars have been observed after `as_of`
    (or a data anomaly forced early resolution) -- False means still
    waiting, re-evaluate later, same as PredictionOutcomeState.ACTIVE."""
    bars_observed: int
    actual_return: float | None
    """(price_at_horizon / reference_price - 1), None until resolved."""
    correct: bool | None
    """True/False once resolved for a UP/DOWN forecast (did price move
    the predicted way); always None for a NO_EDGE forecast (nothing was
    predicted to be right or wrong about) even once resolved -- never
    fabricated as a coin-flip grade."""
    detail: str

    @classmethod
    def new_id(cls) -> str:
        return uuid.uuid4().hex


def evaluate_forecast(
    forecast: DirectionForecastRecord, *, provider: MarketDataProvider, period: str = "1y", now: datetime | None = None,
) -> DirectionForecastEvaluation:
    eval_time = now or datetime.now(timezone.utc)

    try:
        ohlcv = provider.fetch_ohlcv(forecast.symbol, period=period, interval=forecast.interval)
    except MarketDataError as exc:
        return _evaluation(
            forecast, eval_time, resolved=False, bars_observed=0,
            detail=f"Failed to fetch market data for {forecast.symbol}: {exc}",
        )

    frame = ohlcv.to_dataframe()
    as_of = forecast.as_of.replace(tzinfo=None) if forecast.as_of.tzinfo is not None else forecast.as_of
    subsequent = frame[frame.index > as_of]

    if subsequent.empty:
        return _evaluation(
            forecast, eval_time, resolved=False, bars_observed=0,
            detail="No bars observed yet after the forecast's as_of timestamp.",
        )

    previous_close = forecast.reference_price
    bars_observed = 0
    for timestamp, row in subsequent.iterrows():
        bars_observed += 1
        close = float(row["Close"])

        if close < previous_close * (1 - ANOMALOUS_BAR_GAP_THRESHOLD) or close > previous_close * (1 + ANOMALOUS_BAR_GAP_THRESHOLD):
            return _evaluation(
                forecast, eval_time, resolved=False, bars_observed=bars_observed,
                detail=(
                    f"Bar {bars_observed} shows an implausible >={ANOMALOUS_BAR_GAP_THRESHOLD:.0%} move from the "
                    f"previous close ({previous_close:.2f}) to {close:.2f} -- likely an unadjusted stock split/"
                    "reverse-split or a data error, not resolved as a genuine directional outcome."
                ),
            )

        if bars_observed >= forecast.horizon_bars:
            actual_return = close / forecast.reference_price - 1
            correct = (
                None if forecast.direction == DirectionLabel.NO_EDGE
                else (actual_return > 0) if forecast.direction == DirectionLabel.UP
                else (actual_return < 0)
            )
            return _evaluation(
                forecast, eval_time, resolved=True, bars_observed=bars_observed, actual_return=actual_return, correct=correct,
                detail=f"Resolved at bar {bars_observed} of {forecast.horizon_bars}: actual_return={actual_return:+.4%}.",
            )

        previous_close = close

    return _evaluation(
        forecast, eval_time, resolved=False, bars_observed=bars_observed,
        detail=f"Still open after {bars_observed} of {forecast.horizon_bars} bars -- not enough data yet to resolve.",
    )


def _evaluation(
    forecast: DirectionForecastRecord, eval_time: datetime, *, resolved: bool, bars_observed: int,
    actual_return: float | None = None, correct: bool | None = None, detail: str,
) -> DirectionForecastEvaluation:
    return DirectionForecastEvaluation(
        evaluation_id=DirectionForecastEvaluation.new_id(), forecast_id=forecast.forecast_id, evaluated_at=eval_time,
        resolved=resolved, bars_observed=bars_observed, actual_return=actual_return, correct=correct, detail=detail,
    )


class DirectionForecastSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    total: int
    resolved: int
    correct: int
    incorrect: int
    no_edge: int
    """Resolved NO_EDGE forecasts -- never counted as correct or incorrect."""
    accuracy: float | None
    """correct / (correct + incorrect); None if nothing directional has resolved yet."""
    average_return: float | None
    """Mean actual_return over resolved UP/DOWN forecasts (NOT sign-adjusted --
    a raw price-return average, not a 'did I make money' figure, since there is
    no trade behind this)."""


def summarize_forecasts(evaluations: list[DirectionForecastEvaluation], forecasts_by_id: dict[str, DirectionForecastRecord]) -> DirectionForecastSummary:
    """`forecasts_by_id` is required (unlike predictions.tracker.
    summarize_predictions) because correctness needs each evaluation's
    own forecast's `direction` -- NO_EDGE forecasts must be excluded from
    accuracy even though their `correct` field is already None, since a
    caller could otherwise double-count them as neither by accident."""
    latest_by_forecast: dict[str, DirectionForecastEvaluation] = {}
    for evaluation in evaluations:
        current = latest_by_forecast.get(evaluation.forecast_id)
        if current is None or evaluation.evaluated_at > current.evaluated_at:
            latest_by_forecast[evaluation.forecast_id] = evaluation

    latest = list(latest_by_forecast.values())
    resolved = [e for e in latest if e.resolved]
    directional_resolved = [e for e in resolved if forecasts_by_id[e.forecast_id].direction != DirectionLabel.NO_EDGE]
    no_edge_resolved = [e for e in resolved if forecasts_by_id[e.forecast_id].direction == DirectionLabel.NO_EDGE]

    correct = sum(1 for e in directional_resolved if e.correct is True)
    incorrect = sum(1 for e in directional_resolved if e.correct is False)
    accuracy = (correct / (correct + incorrect)) if (correct + incorrect) > 0 else None

    returns = [e.actual_return for e in directional_resolved if e.actual_return is not None]
    average_return = (sum(returns) / len(returns)) if returns else None

    return DirectionForecastSummary(
        total=len(latest), resolved=len(resolved), correct=correct, incorrect=incorrect,
        no_edge=len(no_edge_resolved), accuracy=accuracy, average_return=average_return,
    )
