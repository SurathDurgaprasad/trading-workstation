"""ML Phase 1 leakage test suite -- PHASE_1_IMPLEMENTATION_SPEC.md Section
10, "must pass before any result is trusted". Extends tests/test_backtest_
lookahead.py's own established pattern (mutate a future row, confirm an
earlier value is unchanged) to ml_research/'s new feature engine, label
generator, join function, and walk-forward fold builder.
"""
from __future__ import annotations

import pandas as pd
import pytest

from market.data_provider import OHLCV, OHLCVBar
from ml_research.dataset import JoinSafetyError, join_features_and_labels
from ml_research.features import add_composite_score, add_features, build_symbol_bars
from ml_research.labels import HORIZON_BARS, LabelOutcome, build_labels_for_symbol, labels_to_frame
from ml_research.walk_forward import build_walk_forward_plan


def _make_ohlcv(symbol: str, n_bars_per_session: int, n_sessions: int, base_price: float = 100.0) -> OHLCV:
    """Synthetic 5-minute bars across `n_sessions` distinct trading days,
    `n_bars_per_session` bars each, a mild upward drift so ATR/RSI/SMA are
    all well-defined (non-degenerate) once enough bars have accumulated."""
    bars = []
    price = base_price
    for session in range(n_sessions):
        day = pd.Timestamp("2026-06-22") + pd.Timedelta(days=session)
        for bar_i in range(n_bars_per_session):
            ts = day + pd.Timedelta(hours=9, minutes=15) + pd.Timedelta(minutes=5 * bar_i)
            price = price * (1 + 0.0005 * (1 if bar_i % 3 else -0.5))
            bars.append(OHLCVBar(timestamp=ts, open=price, high=price * 1.003, low=price * 0.997, close=price, volume=10_000.0 + bar_i))
    return OHLCV(symbol=symbol, interval="5m", bars=bars)


def _build_feature_frame(symbol: str = "TEST.NS", n_bars_per_session: int = 30, n_sessions: int = 5) -> pd.DataFrame:
    ohlcv = _make_ohlcv(symbol, n_bars_per_session, n_sessions)
    bars = build_symbol_bars(symbol, ohlcv)
    frame = add_features(bars, benchmark_close=None)
    frame["sector_strength_score"] = 0.0  # bypass the cross-sectional pass for single-symbol tests
    frame = add_composite_score(frame)
    return frame


# --- feature no-look-ahead --------------------------------------------------


def test_vwap_distance_unaffected_by_future_bars():
    frame_a = _build_feature_frame()
    ohlcv = _make_ohlcv("TEST.NS", 30, 5)
    bars = build_symbol_bars("TEST.NS", ohlcv)
    # Mutate every bar strictly after index 10 to an extreme value.
    bars.frame.iloc[11:, bars.frame.columns.get_loc("close")] = 99999.0
    bars.frame.iloc[11:, bars.frame.columns.get_loc("high")] = 99999.0
    bars.frame.iloc[11:, bars.frame.columns.get_loc("low")] = 99999.0
    bars.frame.iloc[11:, bars.frame.columns.get_loc("volume")] = 1.0
    frame_b = add_features(bars, benchmark_close=None)

    assert frame_a["vwap_distance"].iloc[10] == pytest.approx(frame_b["vwap_distance"].iloc[10])


def test_opening_gap_unaffected_by_future_bars():
    frame_a = _build_feature_frame()
    ohlcv = _make_ohlcv("TEST.NS", 30, 5)
    bars = build_symbol_bars("TEST.NS", ohlcv)
    bars.frame.iloc[11:, bars.frame.columns.get_loc("close")] = 55555.0
    frame_b = add_features(bars, benchmark_close=None)

    assert frame_a["opening_gap"].iloc[10] == pytest.approx(frame_b["opening_gap"].iloc[10]) or (
        pd.isna(frame_a["opening_gap"].iloc[10]) and pd.isna(frame_b["opening_gap"].iloc[10])
    )


def test_intraday_range_normalized_unaffected_by_future_bars():
    frame_a = _build_feature_frame()
    ohlcv = _make_ohlcv("TEST.NS", 30, 5)
    bars = build_symbol_bars("TEST.NS", ohlcv)
    bars.frame.iloc[11:, bars.frame.columns.get_loc("high")] = 77777.0
    frame_b = add_features(bars, benchmark_close=None)

    assert frame_a["intraday_range_normalized"].iloc[10] == pytest.approx(frame_b["intraday_range_normalized"].iloc[10])


def test_reused_indicators_still_no_lookahead_through_this_wrapper():
    """market/indicators.py already has its own no-look-ahead test coverage
    (cited, not re-tested here) -- this confirms build_symbol_bars/
    add_features' own OHLCV round-trip doesn't accidentally reintroduce a
    leak by, e.g., misaligning the index."""
    frame_a = _build_feature_frame(n_bars_per_session=30, n_sessions=5)
    ohlcv = _make_ohlcv("TEST.NS", 30, 5)
    bars = build_symbol_bars("TEST.NS", ohlcv)
    # Mutate strictly AFTER the comparison indices below (25), never at or
    # before them -- otherwise the comparison index's own OWN value would
    # legitimately change too, which is not a leakage question.
    bars.frame.iloc[26:, bars.frame.columns.get_loc("close")] = 1234.0
    frame_b = add_features(bars, benchmark_close=None)

    # rsi_14 (14-bar warmup) and sma_20 (20-bar warmup) are both defined by
    # index 25 -- both sides must agree either way, NaN included.
    for col, idx in (("rsi_14", 25), ("sma_20", 25)):
        a, b = frame_a[col].iloc[idx], frame_b[col].iloc[idx]
        if pd.isna(a):
            assert pd.isna(b), f"{col} at {idx}: baseline NaN but mutated-future value is {b}"
        else:
            assert a == pytest.approx(b)


# --- label uses only t+1..t+H, never crosses a session boundary ------------


def test_label_generator_ignores_bars_beyond_its_own_session():
    """Two sessions, each 12 bars (fewer than HORIZON_BARS+session length
    would allow full resolution for late-session signals) -- mutate every
    bar of session 2 to an extreme, barrier-triggering value and confirm
    a signal near the END of session 1 is unaffected (it must square off
    at session 1's own last bar, never read session 2's bars)."""
    frame_baseline = _build_feature_frame(n_bars_per_session=12, n_sessions=2)
    ohlcv = _make_ohlcv("TEST.NS", 12, 2)
    bars = build_symbol_bars("TEST.NS", ohlcv)
    session_2_start = 12
    bars.frame.iloc[session_2_start:, bars.frame.columns.get_loc("low")] = 0.01  # would trip STOP_FIRST if read
    frame_mutated = add_features(bars, benchmark_close=None)
    frame_mutated["sector_strength_score"] = 0.0
    frame_mutated = add_composite_score(frame_mutated)

    labels_baseline = labels_to_frame(build_labels_for_symbol("TEST.NS", frame_baseline))
    labels_mutated = labels_to_frame(build_labels_for_symbol("TEST.NS", frame_mutated))

    # A signal near the end of session 1 (e.g. index 8, 3 bars before session end)
    # must resolve identically whether or not session 2 was mutated.
    row_baseline = labels_baseline.iloc[8]
    row_mutated = labels_mutated.iloc[8]
    assert row_baseline["outcome"] == row_mutated["outcome"]
    if pd.notna(row_baseline["realized_return"]):
        assert row_baseline["realized_return"] == pytest.approx(row_mutated["realized_return"])


def test_label_never_produces_resolved_at_before_or_equal_to_its_own_timestamp():
    frame = _build_feature_frame(n_bars_per_session=40, n_sessions=3)
    rows = build_labels_for_symbol("TEST.NS", frame)
    for row in rows:
        if row.resolved_at is not None:
            assert row.resolved_at > row.timestamp


def test_label_horizon_is_respected():
    frame = _build_feature_frame(n_bars_per_session=40, n_sessions=3)
    rows = build_labels_for_symbol("TEST.NS", frame)
    for row in rows:
        if row.outcome == LabelOutcome.TIMEOUT and row.bars_to_resolution is not None:
            assert row.bars_to_resolution <= HORIZON_BARS


# --- join safety -------------------------------------------------------------


def _minimal_feature_row(symbol: str, ts: pd.Timestamp) -> dict:
    row = {"symbol": symbol, "timestamp": ts, "feature_version": "v1", "data_version": "d1"}
    for col in ("sma_20", "sma_50", "rsi_14", "macd", "macd_signal", "macd_histogram", "atr_14",
                "volume_ratio", "volume_trend_score", "trend_score", "momentum_score", "breakout_score",
                "relative_strength_score", "sector_strength_score", "composite_score",
                "vwap_distance", "opening_gap", "intraday_range_normalized"):
        row[col] = 0.0
    return row


def test_join_accepts_a_valid_feature_label_pair():
    ts = pd.Timestamp("2026-06-22 09:15:00")
    features = pd.DataFrame([_minimal_feature_row("TEST.NS", ts)])
    labels = pd.DataFrame([{
        "symbol": "TEST.NS", "timestamp": ts, "label_generator_version": "v1",
        "outcome": "TARGET_FIRST", "resolved_at": ts + pd.Timedelta(minutes=15),
        "realized_return": 0.01, "label_target_first": 1,
    }])
    merged = join_features_and_labels(features, labels)
    assert len(merged) == 1


def test_join_rejects_a_label_resolved_before_its_own_feature_timestamp():
    """Structural proof of the join-safety invariant: a label whose
    resolved_at is NOT strictly after the feature's own timestamp must be
    rejected, not silently joined."""
    ts = pd.Timestamp("2026-06-22 09:15:00")
    features = pd.DataFrame([_minimal_feature_row("TEST.NS", ts)])
    labels = pd.DataFrame([{
        "symbol": "TEST.NS", "timestamp": ts, "label_generator_version": "v1",
        "outcome": "TARGET_FIRST", "resolved_at": ts - pd.Timedelta(minutes=5),  # BEFORE the feature's own timestamp
        "realized_return": 0.01, "label_target_first": 1,
    }])
    with pytest.raises(JoinSafetyError):
        join_features_and_labels(features, labels)


def test_join_excludes_insufficient_data_labels():
    ts = pd.Timestamp("2026-06-22 09:15:00")
    features = pd.DataFrame([_minimal_feature_row("TEST.NS", ts)])
    labels = pd.DataFrame([{
        "symbol": "TEST.NS", "timestamp": ts, "label_generator_version": "v1",
        "outcome": "INSUFFICIENT_DATA", "resolved_at": pd.NaT,
        "realized_return": None, "label_target_first": None,
    }])
    merged = join_features_and_labels(features, labels)
    assert merged.empty


# --- purge/embargo correctness ------------------------------------------------


def test_walk_forward_folds_never_let_train_and_validate_sessions_overlap():
    sessions = [pd.Timestamp("2026-06-22").date() + pd.Timedelta(days=i) for i in range(60)]
    plan = build_walk_forward_plan(sessions, n_test_sessions=12, n_folds=4, validation_sessions_per_fold=7, embargo_sessions=1)

    for fold in plan.folds:
        assert set(fold.train_sessions).isdisjoint(fold.validate_sessions)
        assert set(fold.train_sessions).isdisjoint(fold.embargo_sessions)
        assert set(fold.embargo_sessions).isdisjoint(fold.validate_sessions)
        # every train session strictly precedes every validate session
        if fold.train_sessions and fold.validate_sessions:
            assert max(fold.train_sessions) < min(fold.validate_sessions)

    # test window strictly after every fold's own validation window
    for fold in plan.folds:
        if fold.validate_sessions:
            assert max(fold.validate_sessions) < min(plan.test_sessions)


def test_walk_forward_folds_expand():
    sessions = [pd.Timestamp("2026-06-22").date() + pd.Timedelta(days=i) for i in range(60)]
    plan = build_walk_forward_plan(sessions, n_test_sessions=12, n_folds=4, validation_sessions_per_fold=7, embargo_sessions=1)
    sizes = [len(f.train_sessions) for f in plan.folds]
    assert sizes == sorted(sizes)
    assert len(set(sizes)) == len(sizes)  # strictly increasing, not just non-decreasing


def test_walk_forward_raises_on_duplicate_sessions():
    sessions = [pd.Timestamp("2026-06-22").date()] * 5
    with pytest.raises(ValueError):
        build_walk_forward_plan(sessions, n_test_sessions=1, n_folds=1, validation_sessions_per_fold=1, embargo_sessions=1)


# --- reproducibility -----------------------------------------------------------


def test_feature_and_label_generation_is_deterministic():
    frame_1 = _build_feature_frame()
    frame_2 = _build_feature_frame()
    pd.testing.assert_frame_equal(frame_1.drop(columns=["symbol", "session_date"]), frame_2.drop(columns=["symbol", "session_date"]))

    labels_1 = labels_to_frame(build_labels_for_symbol("TEST.NS", frame_1))
    labels_2 = labels_to_frame(build_labels_for_symbol("TEST.NS", frame_2))
    pd.testing.assert_frame_equal(labels_1.drop(columns=["label_generator_version"]), labels_2.drop(columns=["label_generator_version"]))


# --- anomaly guard passthrough -----------------------------------------------


def test_anomalous_gap_produces_insufficient_data_not_a_fabricated_outcome():
    frame = _build_feature_frame(n_bars_per_session=20, n_sessions=2)
    ohlcv = _make_ohlcv("TEST.NS", 20, 2)
    bars = build_symbol_bars("TEST.NS", ohlcv)
    # Inject an implausible >50% gap two bars after a mid-session signal.
    bars.frame.iloc[7, bars.frame.columns.get_loc("low")] = bars.frame.iloc[6]["close"] * 0.2
    bars.frame.iloc[7, bars.frame.columns.get_loc("high")] = bars.frame.iloc[6]["close"] * 0.3
    frame2 = add_features(bars, benchmark_close=None)
    frame2["sector_strength_score"] = 0.0
    frame2 = add_composite_score(frame2)

    rows = build_labels_for_symbol("TEST.NS", frame2)
    row_at_5 = rows[5]  # signal bar whose resolution window includes the anomalous bar at index 7
    assert row_at_5.outcome == LabelOutcome.INSUFFICIENT_DATA
