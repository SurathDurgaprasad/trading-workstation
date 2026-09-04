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
PAPER_DB_PATH = Path(os.environ["TRADING_PAPER_DB_PATH"]) if "TRADING_PAPER_DB_PATH" in os.environ else PROJECT_ROOT / "data" / "paper_trading.db"


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
    from learning.profitability import compute_profitability_report
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
        "profitability": compute_profitability_report(items),
    }


def get_paper_execution_snapshot() -> dict | None:
    """Real, persisted paper.engine.PaperTradingEngine state (the
    shadow-run/`schedule --paper-execute` and paper/advance.py world --
    a DIFFERENT store than live/workstation.py's LiveSimPipeline the
    root `/` page already shows) -- account, PENDING orders, OPEN
    positions, and the most recent journal entries, exactly as
    persisted. Never fabricates a value: an account with zero activity
    still returns a snapshot (so its real, currently-idle numbers show),
    but None is returned only when the database itself doesn't exist
    yet -- the same "don't fabricate a page for data that was never
    written" rule every other get_*() in this module already follows."""
    from paper.engine import _naive
    from paper.models import PositionStatus
    from paper.store import PaperStore

    if not PAPER_DB_PATH.exists():
        return None

    store = PaperStore(PAPER_DB_PATH)
    account = store.get_account()
    pending_orders = store.list_pending_orders()
    positions = store.list_positions()
    open_positions = [p for p in positions if p.status == PositionStatus.OPEN]
    closed_positions = [p for p in positions if p.status == PositionStatus.CLOSED]
    journal_entries = sorted(store.list_journal_entries(), key=lambda e: _naive(e.created_at), reverse=True)[:20]
    store.close()

    if account is None:
        return None

    return {
        "account": account,
        "pending_orders": pending_orders,
        "open_positions": open_positions,
        "closed_positions": sorted(closed_positions, key=lambda p: _naive(p.exit_time or p.entry_time), reverse=True)[:20],
        "journal_entries": journal_entries,
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
