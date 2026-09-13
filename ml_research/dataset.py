"""ml_research/dataset.py -- joins the feature and label datasets into one
training-ready table (docs/research/ML_PHASE1_TRIPLE_BARRIER_BASELINE_
PREREGISTRATION.md Section 4; PHASE_1_IMPLEMENTATION_SPEC.md Section 1's
own architectural boundary).

Features and labels are built and persisted as PHYSICALLY SEPARATE
datasets (features.py / labels.py, each with its own Parquet output) --
this module is the ONLY place they are ever joined, and the join itself
is the structural enforcement of "the label generator, future bars, or
realized outcomes must never reach the feature-generation path": joining
here (after both are independently built) cannot retroactively change
what a feature value already was, whereas a single shared dataset built
by one function could accidentally do so.

join_features_and_labels is the "tested_join(features, labels)" function
named in the user's own Phase 1 mission message.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

FEATURE_COLUMNS = (
    "sma_20", "sma_50", "rsi_14", "macd", "macd_signal", "macd_histogram", "atr_14",
    "volume_ratio", "volume_trend_score", "trend_score", "momentum_score", "breakout_score",
    "relative_strength_score", "sector_strength_score", "composite_score",
    "vwap_distance", "opening_gap", "intraday_range_normalized",
)


class JoinSafetyError(ValueError):
    """Raised when the feature/label join would violate the temporal
    boundary this experiment exists to protect -- never caught and
    silently worked around, only ever a hard failure."""


def join_features_and_labels(features: pd.DataFrame, labels: pd.DataFrame) -> pd.DataFrame:
    """`features` must carry (symbol, timestamp, feature_version,
    data_version) plus FEATURE_COLUMNS. `labels` must carry (symbol,
    timestamp, label_generator_version, horizon_bars, outcome,
    realized_return, bars_to_resolution, resolved_at, label_target_first).
    Joins on (symbol, timestamp) -- an inner join, so a feature row with
    no corresponding label row (e.g. the very last bar of a symbol's
    history, which cannot be labeled) is silently dropped, never
    fabricated.

    Structural join-safety assertion (the reason this function exists
    rather than a bare pd.merge call at the call site): for every joined
    row, the feature's own `timestamp` must be STRICTLY EARLIER than the
    label's own `resolved_at` -- i.e. the outcome this row's label
    describes was not yet known at the timestamp the features were
    computed for. A violation raises JoinSafetyError rather than
    returning a subtly-corrupted dataset.
    """
    required_feature_cols = {"symbol", "timestamp", "feature_version", "data_version", *FEATURE_COLUMNS}
    missing = required_feature_cols - set(features.columns)
    if missing:
        raise JoinSafetyError(f"features frame is missing required columns: {sorted(missing)}")

    required_label_cols = {"symbol", "timestamp", "label_generator_version", "outcome", "resolved_at", "label_target_first"}
    missing = required_label_cols - set(labels.columns)
    if missing:
        raise JoinSafetyError(f"labels frame is missing required columns: {sorted(missing)}")

    raw_overlap = features.merge(labels[["symbol", "timestamp"]], on=["symbol", "timestamp"], how="inner")
    if raw_overlap.empty:
        raise JoinSafetyError(
            "join produced zero rows even before quality filtering -- features and labels were not built "
            "from the same symbol set / timestamp index (a genuine construction error, not merely every "
            "label being INSUFFICIENT_DATA)."
        )

    labeled = labels[labels["outcome"] != "INSUFFICIENT_DATA"].copy()

    merged = features.merge(
        labeled, on=["symbol", "timestamp"], how="inner", suffixes=("", "_label"), validate="one_to_one",
    )
    # merged MAY legitimately be empty here (every overlapping row's own
    # label was INSUFFICIENT_DATA) -- that is not itself a join-safety
    # error, only the raw_overlap check above guards against genuine
    # construction mistakes.

    resolved_before_feature = merged["resolved_at"] <= merged["timestamp"]
    if resolved_before_feature.any():
        offenders = merged.loc[resolved_before_feature, ["symbol", "timestamp", "resolved_at"]]
        raise JoinSafetyError(
            f"join safety violated -- {len(offenders)} row(s) have a label resolved_at <= the feature's own "
            f"timestamp (a resolved outcome would be smuggled back into the past). First offender: "
            f"{offenders.iloc[0].to_dict()}"
        )

    return merged


def dataset_metadata(merged: pd.DataFrame, *, experiment_version: str, feature_version: str, label_version: str, universe_version: str) -> dict:
    return {
        "experiment_version": experiment_version,
        "feature_version": feature_version,
        "label_version": label_version,
        "universe_version": universe_version,
        "created_at": pd.Timestamp.utcnow().isoformat(),
        "row_count": int(len(merged)),
        "symbol_count": int(merged["symbol"].nunique()),
        "min_timestamp": str(merged["timestamp"].min()),
        "max_timestamp": str(merged["timestamp"].max()),
        "label_target_first_rate": float(merged["label_target_first"].mean()),
    }
