"""Phase 10 — alpha discovery: causal FEATURE computation only, no trading
rules. A deliberately research-only module — outside strategy/, risk/,
paper/, backtesting/, and never imported by any of them, the MCP server, or
main.py. Nothing here is reachable from live/paper execution.

Five features, one per economically-motivated family (spec: "maximum 5
families"), each with a hypothesis stated BEFORE any result was inspected —
see the Phase 10 report's "feature hypotheses" section for the full
rationale; summarized in each feature's docstring below.

Causality: every FEATURE is a pure function of rows <= T — a rolling
window, a trailing pct_change, or reuse of an already-causal existing
column (market.indicators.compute_volume_ratio_series). Target columns
(forward returns, add_forward_return_targets) are the ONLY place this
module intentionally looks ahead — they are LABELS, never fed back into
add_alpha_features or any signal-generating code, and named/documented as
such throughout.
"""

import pandas as pd

FEATURE_COLUMNS = (
    "trailing_return_20",  # momentum/trend
    "atr_pct_of_price",  # volatility
    "zscore_close_20",  # mean reversion
    "volume_ratio",  # volume/participation -- REUSED from market.indicators, not recomputed
    "relative_strength_20",  # cross-sectional / market-relative
)

FORWARD_HORIZONS = (1, 5, 20)


def add_alpha_features(indicator_series: pd.DataFrame, market_series: pd.DataFrame | None) -> pd.DataFrame:
    """Returns a COPY of indicator_series with 5 additional causal feature
    columns. `market_series` is the relevant broad index's own
    compute_indicator_series() output (^GSPC for US symbols, ^NSEI for
    Indian symbols) — pass None for the two index symbols themselves, for
    which "relative strength vs. the market" is degenerate (relative_
    strength_20 is left as NaN, reported as not-applicable, not zero).
    """
    out = indicator_series.copy()

    # 1. MOMENTUM/TREND: trailing 20-bar return.
    # Hypothesis: trailing momentum carries information about the SIGN of
    # forward returns — continuation OR reversal is an empirical question
    # this feature is designed to answer, not assumed in advance.
    out["trailing_return_20"] = out["close"].pct_change(20)

    # 2. VOLATILITY: ATR14 normalized by price, removing cross-symbol price-
    # level scale (a $50 stock and a 25,000-level index are not directly
    # comparable in raw ATR terms).
    # Hypothesis: elevated relative volatility is associated with a
    # different forward-return distribution (higher variance and/or a
    # different mean) than calm periods.
    out["atr_pct_of_price"] = out["atr_14"] / out["close"]

    # 3. MEAN REVERSION: causal z-score of close vs. its own rolling 20-bar
    # mean/std (rolling, not full-sample — the rolling window at row i uses
    # only rows <= i).
    # Hypothesis: a large positive z-score (short-term overbought) predicts
    # a lower/negative forward return; a large negative z-score predicts a
    # higher forward return.
    roll_mean = out["close"].rolling(window=20, min_periods=20).mean()
    roll_std = out["close"].rolling(window=20, min_periods=20).std()
    out["zscore_close_20"] = (out["close"] - roll_mean) / roll_std.where(roll_std != 0)

    # 4. VOLUME/PARTICIPATION: the "volume_ratio" column already present in
    # indicator_series (market.indicators.compute_volume_ratio_series) is
    # used AS-IS — already causal, not recomputed here.
    # Hypothesis: unusually high relative volume is associated with a
    # larger-magnitude (and possibly directionally informative) forward
    # move.

    # 5. CROSS-SECTIONAL: the symbol's trailing 20-bar return MINUS its
    # market index's trailing 20-bar return over the same window.
    # `market_series` is reindexed onto the symbol's own dates with a
    # forward-fill that only ever uses a PAST index value to fill a gap
    # (never a future one) — causal-safe alignment across two calendars
    # that are usually identical but occasionally differ by a holiday.
    # Hypothesis: stocks recently outperforming their market (positive
    # relative strength) continue to outperform — a documented
    # cross-sectional relative-strength effect.
    if market_series is not None:
        market_close_aligned = market_series["close"].reindex(out.index, method="ffill")
        market_trailing_return = market_close_aligned.pct_change(20)
        out["relative_strength_20"] = out["trailing_return_20"] - market_trailing_return
    else:
        out["relative_strength_20"] = float("nan")

    return out


def add_forward_return_targets(feature_series: pd.DataFrame, horizons=FORWARD_HORIZONS) -> pd.DataFrame:
    """LABELS, not features — deliberately looks ahead via shift(-h). A row
    at index i's fwd_return_h column is close[i+h]/close[i] - 1, i.e. it
    describes the future and must never be read by add_alpha_features, any
    Strategy, or any signal-generating code — only by the Phase 10 research
    scripts that evaluate a feature's predictive relationship to it."""
    out = feature_series.copy()
    for h in horizons:
        out[f"fwd_return_{h}"] = out["close"].shift(-h) / out["close"] - 1
    return out
