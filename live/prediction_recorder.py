"""Autonomous hardening cycle 36 -- closes a real architectural gap found
during the "real-time strategy validation" mission's own Phase A audit:
this project already has two genuinely thorough, independently-built
systems that had never been wired together.

    predictions/ (Phase 23+): an immutable PredictionRecord ledger, an
    automatic triple-barrier-style outcome-resolution engine
    (predictions/tracker.py::evaluate_prediction, reused verbatim here,
    not reimplemented), and a `python main.py evaluate` CLI command that
    already resolves ACTIVE predictions against real subsequent market
    data. But every prediction was recorded ONLY by the daily,
    scanner-driven `predict`/`shadow-run` research commands
    (decision_engine.models.Decision -> risk.sizing.build_signal_for_buy
    -> predictions.tracker.create_prediction) -- never by the live,
    scheduler/paper-live path.

    live/pipeline.py (Phase 12/13+): the real-time/paper-live engine
    (LiveSimPipeline), which generates Signals directly via
    strategy.generate_signal() and risk-approves/paper-executes them --
    with no decision_engine.Decision anywhere in that flow, and no
    prediction ever recorded.

This module is the bridge, built as a SEPARATE, ADDITIVE layer rather
than a change to live/pipeline.py's own core loop (one of this project's
8 sacred live-execution-safety files).

A first implementation attempt tried to reuse predictions.tracker.
create_prediction(decision, signal, ...) by constructing a synthetic
decision_engine.models.Decision to carry the live signal through it --
and was correctly rejected by Decision's OWN model validator: "A BUY
decision must be backed by recorded scanner evidence." This is not an
oversight to work around; it is a deliberate invariant of the
scanner-driven research pipeline Decision belongs to, and this module
must not fabricate scanner_evidence just to satisfy it (the same
"never fabricate, None when not computed" posture this whole project
already applies everywhere else). The correct fix, found by reading
predictions.models.PredictionRecord itself rather than assuming
create_prediction was the only way to build one: `decision_id` is a
PLAIN STRING field, not a reference to an actual Decision object --
create_prediction's own body does nothing more than extract
decision.decision_id/symbol/label as plain values before constructing a
PredictionRecord directly. This module does exactly that same
construction directly, using signal.stable_id() as decision_id, with NO
Decision object (and therefore no scanner-evidence requirement) involved
at all -- a genuinely different, honestly-labeled kind of prediction
source (the live pipeline), not a forced fit into the research
pipeline's own shape.

Recording a prediction is a pure, non-mutating, side-effect-free-on-the-
trading-path OBSERVABILITY action: it never influences risk, sizing,
approval, or execution, and a recording failure must never be allowed to
break the actual trading loop -- every public function here is safe to
call with best-effort semantics (returns None and logs on failure,
never raises into the caller's own critical loop).
"""

import logging
from datetime import datetime, timezone

from decision_engine.models import DecisionLabel
from live.pipeline import LiveSimPipeline, PipelineStepResult
from paper.engine import PaperTradingEngine
from predictions.errors import DuplicatePredictionError
from predictions.models import PredictionRecord
from predictions.store import PredictionStore
from strategy.signal import Side

logger = logging.getLogger(__name__)


def record_prediction_for_signal(
    result: PipelineStepResult,
    *,
    pipeline: LiveSimPipeline,
    engine: PaperTradingEngine,
    prediction_store: PredictionStore,
    horizon_bars: int,
) -> PredictionRecord | None:
    """Best-effort: records an immutable PredictionRecord for the signal
    a live/paper-live process_next() call just generated, regardless of
    what happened to it next (PENDING_HUMAN_APPROVAL, CRITIC_REJECTED,
    KILL_SWITCH_ACTIVE, or auto-mode BAR_PROCESSED) -- the mission's own
    "record NO-TRADE decisions too" principle extended to its logical
    conclusion: a signal that was generated but then vetoed is exactly
    as valuable a research data point as one that executed, maybe more
    so (it is the raw signal-generation quality, independent of the
    approval/risk/kill-switch layers stacked on top of it).

    `decision_id` is set to `signal.stable_id()` -- the SAME deterministic
    identity this project's own idempotency already keys everything else
    on for this signal (paper order creation, approval-decision records)
    -- so a prediction record can always be correlated back to the exact
    trading decision it describes, without needing a decision_engine.
    Decision object (which this signal never went through; see this
    module's own docstring for why that reuse attempt was wrong).

    Returns None (never raises) when:
      - no signal was generated this call (result.signal is None);
      - the signal's side is not LONG (this project's PredictionRecord
        structurally requires stop_price < entry_price < target_price,
        a LONG-only invariant; TrendMomentumBaseline is LONG-only today,
        so this is a defensive guard against a future SHORT-capable
        strategy, not a currently-reachable branch);
      - the exact (symbol, entry_time) pair was already recorded --
        DuplicatePredictionError from the store's own DB-level
        UNIQUE(symbol, entry_time) constraint is caught and treated as
        "already recorded, nothing to do", not an error;
      - anything else in this best-effort recording path raises --
        logged, never propagated into the caller's own trading loop.
    """
    signal = result.signal
    if signal is None:
        return None
    if signal.side != Side.LONG:
        logger.info("prediction_recorder: skipping a non-LONG signal for %s -- PredictionRecord is LONG-only.", signal.symbol)
        return None

    try:
        # Read-only, side-effect-free: the SAME pure risk_engine.evaluate()
        # call live/pipeline.py's own _handle_signal already made (or will
        # make, for the human-approval path, at approve_pending() time) --
        # recomputing it here for OBSERVABILITY never touches the account,
        # never creates an order, and produces a result identical to what
        # was (or will be) used for the real decision, since RiskEngine is
        # a pure function of (signal, account) and account state has not
        # changed since process_next() returned this same result.
        risk_decision = pipeline.engine.risk_engine.evaluate(signal, pipeline.engine.account)

        prediction = PredictionRecord(
            prediction_id=PredictionRecord.new_id(),
            decision_id=signal.stable_id(),
            symbol=signal.symbol,
            created_at=pipeline._clock() or datetime.now(timezone.utc),
            label=DecisionLabel.BUY,  # only a BUY-shaped Signal (side=LONG, already checked) ever reaches this path
            entry_price=signal.reference_price,
            stop_price=signal.stop_price,
            target_price=signal.target_price,
            entry_time=signal.generated_at,
            horizon_bars=horizon_bars,
            interval=pipeline.interval,
            risk_decision=risk_decision,
            critic_assessment=result.critic_assessment,
        )
        prediction_store.save_prediction(prediction)
        return prediction
    except DuplicatePredictionError:
        # Deliberately a SEPARATE branch from the generic handler below,
        # even though both return None: an expected, already-recorded
        # duplicate is not a failure and must not be logged as one (see
        # this test file's own mutation-testing note -- removing this
        # branch does not change the RETURN value, since the generic
        # handler below would also catch it, but it WOULD start logging
        # a full traceback for every ordinary duplicate, which is exactly
        # the noisy-log outcome this branch exists to prevent).
        return None
    except Exception:  # noqa: BLE001 -- best-effort observability must never break the real trading loop
        logger.exception("prediction_recorder: failed to record a prediction for %s -- continuing the live session regardless.", signal.symbol)
        return None


def evaluate_pending_predictions(
    prediction_store: PredictionStore,
    *,
    provider,
    requested_period: str = "1y",
) -> int:
    """Real-time strategy validation mission, Phase C -- closes the second
    half of the gap this module's own docstring describes: recording a
    prediction was only half of "predictions accumulate real evidence
    without manual intervention" (mission Phase 13/Phase D §13 "resolve
    previous predictions"). Before this, a recorded live prediction sat at
    ACTIVE forever unless an operator remembered to separately run
    `python main.py evaluate` -- this is the SAME batch-resolution logic
    that command runs (predictions.tracker.evaluate_prediction, with
    predictions.tracker.resolution_period_for_interval correcting the
    fetch period for the live path's typically-intraday interval, see
    that function's own docstring for the real, empirically-confirmed
    Yahoo Finance limit it works around), called periodically from INSIDE
    the paper-live loop itself instead of requiring a separate command.

    Best-effort by construction, same posture as record_prediction_for_
    signal above: a listing or per-prediction evaluation failure is
    logged and isolated, never raised into the caller's real trading
    loop, and never partially applied (each prediction's own save_
    evaluation either fully succeeds or that one prediction is simply
    skipped this cycle -- it stays ACTIVE and is retried the next time
    this is called).

    Returns the count of predictions successfully evaluated and
    persisted this call (0 on a total listing failure), for the loop's
    own status-line reporting -- never meaningful as a health signal on
    its own (0 pending predictions is a completely normal steady state).
    """
    from predictions.tracker import evaluate_prediction, resolution_period_for_interval

    try:
        pending = prediction_store.list_predictions_needing_evaluation()
    except Exception:  # noqa: BLE001 -- see module docstring: never break the real trading loop
        logger.exception("prediction_recorder: failed to list pending predictions for periodic auto-evaluation -- skipping this cycle.")
        return 0

    evaluated = 0
    for prediction in pending:
        try:
            period = resolution_period_for_interval(prediction.interval, requested_period=requested_period)
            evaluation = evaluate_prediction(prediction, provider=provider, period=period)
            prediction_store.save_evaluation(evaluation)
            evaluated += 1
        except Exception:  # noqa: BLE001 -- one prediction's failure must never abort the rest of the batch or the trading loop
            logger.exception(
                "prediction_recorder: periodic auto-evaluation failed for prediction %s (%s) -- continuing with the rest of the batch.",
                prediction.prediction_id, prediction.symbol,
            )
            continue
    return evaluated
