"""ml_research/baseline_model.py -- the ONLY model in scope for Phase 1
(docs/research/ML_PHASE1_TRIPLE_BARRIER_BASELINE_PREREGISTRATION.md;
PHASE_1_IMPLEMENTATION_SPEC.md Section 9's MODEL LAYER). Logistic
regression only -- no random forest, gradient boosting, or neural
network is in scope for this phase (PHASE_1_IMPLEMENTATION_SPEC.md
Section 2, "Out of scope").

Any scaler is fit ONLY on the training fold, never on validation/test --
sklearn.pipeline.Pipeline enforces this structurally (a fitted Pipeline's
.predict_proba on new data re-uses the SAME already-fit scaler, it never
refits).

Calibration (Platt scaling via sklearn's CalibratedClassifierCV,
method="sigmoid") is fit using an internal cross-validation split of the
TRAINING fold only -- never the validation/test fold's own outcomes
(PHASE_1_IMPLEMENTATION_SPEC.md Section 15).
"""
from __future__ import annotations

import hashlib
import inspect
import sys
from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

MODEL_TYPE = "logistic_regression"
RANDOM_SEED = 20260913  # fixed for reproducibility -- PHASE_1_IMPLEMENTATION_SPEC.md Section 23


def model_version() -> str:
    return hashlib.sha256(inspect.getsource(sys.modules[__name__]).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class FittedFold:
    fold_index: int
    feature_columns: tuple[str, ...]
    pipeline: Pipeline
    coefficients: dict[str, float]
    intercept: float
    n_train_rows: int
    n_train_rows_complete_case: int


def fit_fold(train_frame: pd.DataFrame, feature_columns: tuple[str, ...], *, fold_index: int) -> FittedFold:
    """Fits ONLY on `train_frame` (the caller is responsible for making
    sure this is the fold's own training rows, never validation/test --
    see ml_research/walk_forward.py). Missing feature values (NaN, e.g.
    sector_strength_score for an untagged symbol, or relative_strength_
    score before the lookback warms up) are complete-case dropped for
    this Phase 1 baseline -- no imputation, so a dropped row's own
    (unknown) value can never leak information about how it was filled."""
    complete = train_frame.dropna(subset=[*feature_columns, "label_target_first"])
    X = complete[list(feature_columns)].to_numpy()
    y = complete["label_target_first"].to_numpy()

    if len(np.unique(y)) < 2:
        raise ValueError(f"Fold {fold_index}: training data has only one class present ({np.unique(y)}) -- cannot fit logistic regression.")

    base = LogisticRegression(max_iter=1000, random_state=RANDOM_SEED)
    pipeline = Pipeline([("scaler", StandardScaler()), ("model", base)])

    # Calibrate via an internal CV split of the training fold only.
    calibrated = CalibratedClassifierCV(pipeline, method="sigmoid", cv=3)
    calibrated.fit(X, y)

    # Also fit an uncalibrated pipeline for coefficient inspection/reporting
    # (CalibratedClassifierCV wraps several internal clones; coefficients
    # are reported from a plain fit on the same data for interpretability
    # only -- predictions always come from `calibrated`, never this one).
    plain = Pipeline([("scaler", StandardScaler()), ("model", LogisticRegression(max_iter=1000, random_state=RANDOM_SEED))])
    plain.fit(X, y)
    coefficients = dict(zip(feature_columns, plain.named_steps["model"].coef_[0].tolist()))
    intercept = float(plain.named_steps["model"].intercept_[0])

    return FittedFold(
        fold_index=fold_index, feature_columns=feature_columns, pipeline=calibrated,
        coefficients=coefficients, intercept=intercept,
        n_train_rows=len(train_frame), n_train_rows_complete_case=len(complete),
    )


def predict_proba(fitted: FittedFold, frame: pd.DataFrame) -> pd.Series:
    """Returns P(target_first) for every row of `frame` that has complete
    feature data; NaN for rows with any missing feature (never imputed,
    never dropped silently from the caller's own index -- the caller
    decides how to handle a NaN prediction)."""
    complete_mask = frame[list(fitted.feature_columns)].notna().all(axis=1)
    proba = pd.Series(np.nan, index=frame.index, dtype=float)
    if complete_mask.any():
        X = frame.loc[complete_mask, list(fitted.feature_columns)].to_numpy()
        proba.loc[complete_mask] = fitted.pipeline.predict_proba(X)[:, 1]
    return proba
