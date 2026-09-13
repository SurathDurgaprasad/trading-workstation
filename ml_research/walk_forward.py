"""ml_research/walk_forward.py -- expanding-window, session-level
walk-forward fold construction with purge/embargo (docs/research/
ML_PHASE1_TRIPLE_BARRIER_BASELINE_PREREGISTRATION.md Section 6;
PHASE_1_IMPLEMENTATION_SPEC.md Section 8).

Distinct from, and NOT a modification of, backtesting/walk_forward.py --
that module explicitly has no retraining mechanism (correct for
TrendMomentumBaseline's own parameter-free frozen rule, insufficient for
a fitted model). This is new, additive code for a genuinely different
purpose: producing TRAIN/VALIDATE session-date boundaries a caller then
uses to slice the joined feature+label dataset and refit a model at each
fold.

Fold boundaries are computed programmatically from the ACTUAL list of
session dates present in the data, never hand-picked -- see the
pre-registration's own explicit requirement.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Fold:
    fold_index: int
    train_sessions: tuple[date, ...]
    embargo_sessions: tuple[date, ...]
    validate_sessions: tuple[date, ...]


@dataclass(frozen=True)
class WalkForwardPlan:
    walk_forward_pool_sessions: tuple[date, ...]
    test_sessions: tuple[date, ...]
    folds: tuple[Fold, ...]


def build_walk_forward_plan(
    all_sessions: list[date], *, n_test_sessions: int, n_folds: int, validation_sessions_per_fold: int, embargo_sessions: int,
) -> WalkForwardPlan:
    """`all_sessions` must be sorted ascending, one entry per distinct
    trading session actually present in the joined dataset. Reserves the
    LAST `n_test_sessions` as the untouched final test window (evaluated
    exactly once, only after every fold below is complete). The remaining
    sessions form the walk-forward pool, split into `n_folds` expanding-
    window folds, each with `validation_sessions_per_fold` validation
    sessions immediately following an `embargo_sessions`-session gap after
    training ends.
    """
    if len(all_sessions) != len(set(all_sessions)):
        raise ValueError("all_sessions must contain no duplicate dates.")
    if all_sessions != sorted(all_sessions):
        raise ValueError("all_sessions must be sorted ascending.")

    if len(all_sessions) <= n_test_sessions:
        raise ValueError(f"Not enough sessions ({len(all_sessions)}) to reserve {n_test_sessions} as a test window.")

    pool = tuple(all_sessions[: len(all_sessions) - n_test_sessions])
    test_sessions = tuple(all_sessions[len(all_sessions) - n_test_sessions :])

    per_fold_advance = validation_sessions_per_fold
    min_pool_needed = n_folds * per_fold_advance + embargo_sessions + 1
    if len(pool) < min_pool_needed:
        raise ValueError(
            f"Walk-forward pool has {len(pool)} sessions, needs at least {min_pool_needed} for "
            f"{n_folds} folds of {validation_sessions_per_fold}-session validation with a "
            f"{embargo_sessions}-session embargo."
        )

    folds: list[Fold] = []
    for fold_index in range(1, n_folds + 1):
        validate_end_offset = len(pool) - (n_folds - fold_index) * per_fold_advance
        validate_start_offset = validate_end_offset - per_fold_advance
        embargo_start_offset = validate_start_offset - embargo_sessions

        if embargo_start_offset <= 0:
            raise ValueError(f"Fold {fold_index}: not enough leading sessions for a non-empty training window.")

        train_sessions = pool[:embargo_start_offset]
        embargo = pool[embargo_start_offset:validate_start_offset]
        validate_sessions = pool[validate_start_offset:validate_end_offset]

        folds.append(Fold(
            fold_index=fold_index, train_sessions=train_sessions,
            embargo_sessions=embargo, validate_sessions=validate_sessions,
        ))

    return WalkForwardPlan(walk_forward_pool_sessions=pool, test_sessions=test_sessions, folds=tuple(folds))
