"""ml_research/evaluation.py -- statistical and economic metrics
(PHASE_1_IMPLEMENTATION_SPEC.md Section 11; user's Phase 1 mission
message Sections 15/18).

Statistical (discrimination/calibration) metrics use scikit-learn's own
standard implementations directly -- no reason to reimplement ROC-AUC/
PR-AUC/log-loss/Brier score by hand.

Economic significance reuses strategy.promotion_gate.evaluate_promotion
and learning.profitability.compute_profitability_report_from_returns
UNMODIFIED -- the same Wilson-score/normal-approximation-CI machinery
already exercised across 55 hypotheses in strategy/hypothesis_registry.py
this project's own research history, applied here to a model's own
expected-net-return series for the first time.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, brier_score_loss, log_loss, roc_auc_score

from learning.profitability import compute_profitability_report_from_returns
from strategy.promotion_gate import evaluate_promotion


@dataclass(frozen=True)
class DiscriminationMetrics:
    roc_auc: float | None
    pr_auc: float | None
    log_loss: float | None
    brier_score: float
    n: int
    positive_rate: float


def compute_discrimination_metrics(y_true: pd.Series, y_proba: pd.Series) -> DiscriminationMetrics:
    mask = y_true.notna() & y_proba.notna()
    y = y_true[mask].to_numpy()
    p = y_proba[mask].to_numpy()
    n = len(y)
    if n == 0:
        return DiscriminationMetrics(None, None, None, float("nan"), 0, float("nan"))

    positive_rate = float(y.mean())
    brier = float(brier_score_loss(y, p))

    if len(np.unique(y)) < 2:
        # Cannot compute rank-based metrics with only one class present --
        # reported honestly as None, never fabricated as 0.5/1.0.
        return DiscriminationMetrics(None, None, None, brier, n, positive_rate)

    roc_auc = float(roc_auc_score(y, p))
    pr_auc = float(average_precision_score(y, p))
    ll = float(log_loss(y, p, labels=[0, 1]))
    return DiscriminationMetrics(roc_auc, pr_auc, ll, brier, n, positive_rate)


def calibration_table(y_true: pd.Series, y_proba: pd.Series, *, n_buckets: int = 10) -> pd.DataFrame:
    """Reliability table: predicted-probability decile vs. realized
    outcome frequency, per PHASE_1_IMPLEMENTATION_SPEC.md Section 11 --
    reported, never treated as automatically acceptable."""
    mask = y_true.notna() & y_proba.notna()
    df = pd.DataFrame({"y": y_true[mask].to_numpy(), "p": y_proba[mask].to_numpy()})
    if df.empty:
        return pd.DataFrame(columns=["bucket", "n", "mean_predicted", "realized_rate"])
    df["bucket"] = pd.qcut(df["p"], q=min(n_buckets, df["p"].nunique()), duplicates="drop")
    grouped = df.groupby("bucket", observed=True).agg(n=("y", "size"), mean_predicted=("p", "mean"), realized_rate=("y", "mean")).reset_index()
    return grouped


@dataclass(frozen=True)
class EconomicSplitResult:
    verdict: object  # strategy.promotion_gate.PromotionEvaluation
    n_development: int
    n_validation: int
    n_out_of_sample: int


def evaluate_economic_significance(candidate_name: str, *, development_returns: list[float], validation_returns: list[float], out_of_sample_returns: list[float]):
    """Thin, direct pass-through to the existing, unmodified promotion
    gate -- no new statistical machinery. The only new thing here is
    calling it with an ML model's own expected-net-return series instead
    of a deterministic strategy's per-trade returns.

    DISCLOSED LIMITATION, repeated here per this project's own
    established caveat-repetition convention: the underlying returns are
    computed from OVERLAPPING intraday windows for the same symbol (a
    signal at bar t and a signal at bar t+1 for the same symbol can have
    resolution windows that overlap in time), so the Wilson/normal-
    approximation confidence intervals this function reports assume more
    statistical independence than the raw row count actually provides --
    the effective sample size is smaller than n. This is named explicitly
    in the Phase 1 report's own Limitations section, not silently
    accepted.
    """
    return evaluate_promotion(
        candidate_name,
        development_returns=development_returns,
        validation_returns=validation_returns,
        out_of_sample_returns=out_of_sample_returns,
    )
