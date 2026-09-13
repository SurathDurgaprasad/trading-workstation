"""ml_research/labels.py -- Phase 1 triple-barrier label generation
(docs/research/ML_PHASE1_TRIPLE_BARRIER_BASELINE_PREREGISTRATION.md
Section 5).

Reuses backtesting.execution.check_exit UNMODIFIED (the exact same
conservative same-bar-ambiguity "stop wins" rule the deterministic
benchmark itself uses -- this is deliberate: the new model's own label
generator must share every mechanical assumption with the benchmark it
will be compared against, so a result difference can only be attributed
to the ranking/selection logic, never to a more favorable execution
assumption smuggled into one side).

Reuses the EXACT dummy-Signal/OpenPosition construction pattern
predictions/tracker.py::_open_position already established (predictions/
tracker.py:242-256) to call check_exit, rather than re-implementing the
stop/target comparison -- the label generator and the live prediction
tracker share the identical resolution mechanics by construction, not by
coincidence.

Reuses predictions/tracker.py's own ANOMALOUS_BAR_GAP_THRESHOLD=0.5
unmodified for the corporate-action/data-anomaly guard.

One addition beyond what either reused module does: an intraday session-
boundary square-off (see build_labels_for_symbol's own docstring) --
frozen in the pre-registration BEFORE this file was written, not decided
here.
"""
from __future__ import annotations

import hashlib
import inspect
import sys
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

import numpy as np
import pandas as pd

from backtesting.execution import OpenPosition, check_exit
from backtesting.trade import ExitReason
from predictions.tracker import ANOMALOUS_BAR_GAP_THRESHOLD
from strategy.signal import ReasonCode, Side, Signal

STOP_ATR_MULTIPLIER = 1.5   # strategy/baseline.py:8, reused unchanged, verified against current source
TARGET_RISK_REWARD = 2.0    # strategy/baseline.py:9, reused unchanged, verified against current source
HORIZON_BARS = 8            # frozen, docs/research/ML_PHASE1_..._PREREGISTRATION.md Section 3 -- do not change based on results


class LabelOutcome(str, Enum):
    TARGET_FIRST = "TARGET_FIRST"
    STOP_FIRST = "STOP_FIRST"
    TIMEOUT = "TIMEOUT"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


def label_version() -> str:
    """sha256 of this module's own source -- mirrors features.feature_
    version()'s convention."""
    return hashlib.sha256(inspect.getsource(sys.modules[__name__]).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class LabelRow:
    symbol: str
    timestamp: datetime  # the SIGNAL bar's own timestamp (t) -- joins to the feature dataset
    entry_reference_price: float
    stop_price: float
    target_price: float
    outcome: LabelOutcome
    realized_return: float | None
    bars_to_resolution: int | None
    resolved_at: datetime | None
    bars_observed: int


def _make_open_position(symbol: str, entry_time: datetime, entry_price: float, stop_price: float, target_price: float) -> OpenPosition:
    """Identical construction pattern to predictions/tracker.py::_open_
    position (tracker.py:242-256) -- a placeholder Signal/quantity=1 exist
    only because check_exit's own signature requires an OpenPosition; none
    of the placeholder fields (risk_reward, strategy_name, quantity)
    affect check_exit's own logic, which reads only stop_price/target_price."""
    risk_per_unit = entry_price - stop_price
    reward_per_unit = target_price - entry_price
    risk_reward = (reward_per_unit / risk_per_unit) if risk_per_unit > 0 else 0.0001
    dummy_signal = Signal(
        symbol=symbol, generated_at=entry_time, side=Side.LONG,
        reference_price=entry_price, stop_price=stop_price, target_price=target_price,
        risk_reward=max(risk_reward, 0.0001), strategy_name="ml_research_phase1_labeler",
        reason_codes=[ReasonCode.DECISION_ENGINE_SCORED],
    )
    return OpenPosition(
        signal=dummy_signal, entry_time=entry_time, entry_price=entry_price,
        quantity=1, stop_price=stop_price, target_price=target_price,
    )


def build_labels_for_symbol(symbol: str, feature_frame: pd.DataFrame) -> list[LabelRow]:
    """`feature_frame` must be the output of ml_research.features.add_
    features (it needs open/high/low/close, atr_14, session_date,
    entry_reference_price, entry_reference_session_date). Iterates every
    row with a valid entry_reference_price (i.e., every row except the
    very last bar of the data, which has no t+1) and resolves a triple-
    barrier label using ONLY bars strictly after t (t+1 .. t+HORIZON_BARS
    or the entry session's own last bar, whichever comes first).

    Session-boundary square-off (frozen in the pre-registration, Section
    5): if the label would need a bar from a LATER session than the entry
    bar's own session to resolve, it resolves as TIMEOUT at the entry
    session's own last available bar instead -- this label generator
    never reads a bar from a different session than the one entry_time
    itself falls in. This makes cross-session leakage structurally
    impossible for this dataset by construction, not by discipline."""
    idx = feature_frame.index
    n = len(feature_frame)
    close = feature_frame["close"].to_numpy()
    high = feature_frame["high"].to_numpy()
    low = feature_frame["low"].to_numpy()
    atr_14 = feature_frame["atr_14"].to_numpy()
    entry_price_col = feature_frame["entry_reference_price"].to_numpy()
    entry_session_col = feature_frame["entry_reference_session_date"].to_numpy()
    session_date_col = feature_frame["session_date"].to_numpy()

    rows: list[LabelRow] = []
    for i in range(n - 1):  # the last row has no t+1, cannot be labeled
        t = idx[i]
        entry_price = entry_price_col[i]
        entry_session = entry_session_col[i]
        atr = atr_14[i]

        if pd.isna(entry_price) or pd.isna(entry_session) or pd.isna(atr):
            rows.append(LabelRow(symbol, t, np.nan, np.nan, np.nan, LabelOutcome.INSUFFICIENT_DATA, None, None, None, 0))
            continue

        stop_price = entry_price - STOP_ATR_MULTIPLIER * atr
        target_price = entry_price + TARGET_RISK_REWARD * (entry_price - stop_price)
        position = _make_open_position(symbol, t, entry_price, stop_price, target_price)

        previous_close = entry_price
        outcome: LabelOutcome | None = None
        realized_return: float | None = None
        resolved_at: datetime | None = None
        bars_to_resolution: int | None = None
        bars_observed = 0
        last_bar_in_session_idx = i + 1

        for j in range(i + 1, n):
            if session_date_col[j] != entry_session:
                break  # would need a bar from a different session -- square off instead, below
            last_bar_in_session_idx = j
            bars_observed += 1
            bar_high, bar_low = float(high[j]), float(low[j])

            # Corporate-action / data-anomaly guard -- predictions/tracker.py's
            # own ANOMALOUS_BAR_GAP_THRESHOLD, unchanged.
            if bar_low < previous_close * (1 - ANOMALOUS_BAR_GAP_THRESHOLD) or bar_high > previous_close * (1 + ANOMALOUS_BAR_GAP_THRESHOLD):
                outcome = LabelOutcome.INSUFFICIENT_DATA
                break
            previous_close = float(close[j])

            result = check_exit(position, pd.Series({"high": bar_high, "low": bar_low}))
            if result is not None:
                exit_price, reason = result
                outcome = LabelOutcome.TARGET_FIRST if reason == ExitReason.TARGET else LabelOutcome.STOP_FIRST
                realized_return = exit_price / entry_price - 1.0
                resolved_at = idx[j]
                bars_to_resolution = bars_observed
                break

            if bars_observed >= HORIZON_BARS:
                outcome = LabelOutcome.TIMEOUT
                realized_return = float(close[j]) / entry_price - 1.0
                resolved_at = idx[j]
                bars_to_resolution = bars_observed
                break

        if outcome is None:
            # Ran out of same-session bars before HORIZON_BARS or a barrier hit
            # -- square off at the entry session's own last available bar.
            outcome = LabelOutcome.TIMEOUT
            realized_return = float(close[last_bar_in_session_idx]) / entry_price - 1.0
            resolved_at = idx[last_bar_in_session_idx]
            bars_to_resolution = bars_observed

        rows.append(LabelRow(
            symbol=symbol, timestamp=t, entry_reference_price=float(entry_price),
            stop_price=float(stop_price), target_price=float(target_price), outcome=outcome,
            realized_return=realized_return, bars_to_resolution=bars_to_resolution,
            resolved_at=resolved_at, bars_observed=bars_observed,
        ))

    return rows


def labels_to_frame(rows: list[LabelRow]) -> pd.DataFrame:
    frame = pd.DataFrame([
        {
            "symbol": r.symbol, "timestamp": r.timestamp, "label_generator_version": label_version(),
            "horizon_bars": HORIZON_BARS, "stop_price": r.stop_price, "target_price": r.target_price,
            "outcome": r.outcome.value, "realized_return": r.realized_return,
            "bars_to_resolution": r.bars_to_resolution, "resolved_at": r.resolved_at,
            "bars_observed": r.bars_observed,
            "label_target_first": 1 if r.outcome == LabelOutcome.TARGET_FIRST else (0 if r.outcome != LabelOutcome.INSUFFICIENT_DATA else np.nan),
        }
        for r in rows
    ])
    return frame
