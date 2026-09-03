"""Phase 26 -- read-only facade over the Phase 18-25 intelligence
pipeline's persisted state, for dashboard/app.py's `/intelligence` view.
Same role live/workstation.py already plays for the paper-live
workstation: the ONE place that owns DB path resolution and read
access, so the route handler itself contains no business logic.

Every function here reads exactly what scan/research/decide/predict/
evaluate already persisted -- nothing here computes a new scan,
fetches market data, or calls an LLM. A dashboard GET must stay fast
and side-effect-free; recomputing intelligence on every page load would
be wrong (and, for scan/research/decide, would silently disagree with
the CLI's own idea of "the latest run"). Every getter returns None when
the relevant database doesn't exist yet or holds nothing usable --
never a fabricated empty-but-present result.

get_learning_snapshot() deliberately calls only the provider-free
learning.analysis functions (compare_by_config_version,
compute_confidence_calibration, compute_signal_quality) -- it skips
compute_regime_performance/build_learning_report's regime part, since
that needs a live/cached market-data provider a page render must not
trigger.

Phase 35 adds get_decision_history/get_research_history/
get_prediction_history for the new per-symbol decision-detail page --
same read-only, no-fetch discipline: these are all store lookups over
data ALREADY persisted by scan/research/decide/predict/evaluate, never
a fresh computation.
"""

import os
from pathlib import Path

from core.config import PROJECT_ROOT

SCANNER_DB_PATH = Path(os.environ["TRADING_SCANNER_DB_PATH"]) if "TRADING_SCANNER_DB_PATH" in os.environ else PROJECT_ROOT / "data" / "scanner.db"
RESEARCH_DB_PATH = Path(os.environ["TRADING_RESEARCH_DB_PATH"]) if "TRADING_RESEARCH_DB_PATH" in os.environ else PROJECT_ROOT / "data" / "research.db"
DECISIONS_DB_PATH = Path(os.environ["TRADING_DECISIONS_DB_PATH"]) if "TRADING_DECISIONS_DB_PATH" in os.environ else PROJECT_ROOT / "data" / "decisions.db"
PREDICTIONS_DB_PATH = Path(os.environ["TRADING_PREDICTIONS_DB_PATH"]) if "TRADING_PREDICTIONS_DB_PATH" in os.environ else PROJECT_ROOT / "data" / "predictions.db"


def get_latest_scan():
    from market_intelligence.store import ScanHistoryStore

    if not SCANNER_DB_PATH.exists():
        return None
    store = ScanHistoryStore(SCANNER_DB_PATH)
    report = store.latest_report()
    store.close()
    return report


def get_latest_decision(symbol: str):
    from decision_engine.store import DecisionStore

    if not DECISIONS_DB_PATH.exists():
        return None
    store = DecisionStore(DECISIONS_DB_PATH)
    decision = store.latest_decision_for_symbol(symbol)
    store.close()
    return decision


def get_latest_research(symbol: str):
    from research.store import ResearchStore

    if not RESEARCH_DB_PATH.exists():
        return None
    store = ResearchStore(RESEARCH_DB_PATH)
    report = store.latest_report_for_symbol(symbol)
    store.close()
    return report


def get_learning_snapshot() -> dict | None:
    from decision_engine.store import DecisionStore
    from learning.analysis import (
        EvaluatedPrediction,
        compare_by_config_version,
        compute_confidence_calibration,
        compute_real_confidence_calibration,
        compute_signal_quality,
    )
    from predictions.store import PredictionStore

    if not PREDICTIONS_DB_PATH.exists():
        return None

    prediction_store = PredictionStore(PREDICTIONS_DB_PATH)
    decision_store = DecisionStore(DECISIONS_DB_PATH) if DECISIONS_DB_PATH.exists() else None

    items: list[EvaluatedPrediction] = []
    for prediction in prediction_store.list_predictions():
        evaluation = prediction_store.latest_evaluation_for_prediction(prediction.prediction_id)
        if evaluation is None:
            continue
        decision = decision_store.get_decision(prediction.decision_id) if decision_store is not None else None
        items.append(EvaluatedPrediction(prediction=prediction, evaluation=evaluation, decision=decision))

    prediction_store.close()
    if decision_store is not None:
        decision_store.close()

    if not items:
        return None

    return {
        "total": len(items),
        "strategy_comparison": compare_by_config_version(items),
        "calibration": compute_confidence_calibration(items),
        "real_calibration": compute_real_confidence_calibration(items),
        "signal_quality": compute_signal_quality(items),
    }


def get_decision_history(symbol: str, limit: int = 10):
    from decision_engine.store import DecisionStore

    if not DECISIONS_DB_PATH.exists():
        return []
    store = DecisionStore(DECISIONS_DB_PATH)
    result = store.list_decisions_for_symbol(symbol, limit=limit)
    store.close()
    return result


def get_research_history(symbol: str, limit: int = 5):
    from research.store import ResearchStore

    if not RESEARCH_DB_PATH.exists():
        return []
    store = ResearchStore(RESEARCH_DB_PATH)
    result = store.list_reports_for_symbol(symbol, limit=limit)
    store.close()
    return result


def get_prediction_history(symbol: str, limit: int = 20):
    """Returns (PredictionRecord, PredictionEvaluation | None) pairs,
    most recent prediction first -- the evaluation is each prediction's
    OWN latest (never a stale superseded one, same rule
    predictions.store.PredictionStore.list_predictions_needing_evaluation
    already applies)."""
    from predictions.store import PredictionStore

    if not PREDICTIONS_DB_PATH.exists():
        return []
    store = PredictionStore(PREDICTIONS_DB_PATH)
    predictions = store.list_predictions_for_symbol(symbol, limit=limit)
    result = [(p, store.latest_evaluation_for_prediction(p.prediction_id)) for p in predictions]
    store.close()
    return result
