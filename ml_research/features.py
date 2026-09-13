"""ml_research/features.py -- Phase 1 feature snapshot construction
(docs/research/ML_PHASE1_TRIPLE_BARRIER_BASELINE_PREREGISTRATION.md
Section 4a/5).

Reuses market.indicators.compute_indicator_series UNMODIFIED for every
reused indicator (sma_20/sma_50/rsi_14/macd*/atr_14/volume_ratio/
volume_trend) -- that function's own no-look-ahead guarantee (each row
uses only that bar and earlier ones) is inherited directly.

trend_score / momentum_score / breakout_score / relative_strength_score /
sector_strength_score / composite_score are vectorized re-implementations
of market_intelligence/scanner.py's own exact per-latest-bar formulas
(scanner.py _screen_symbol/_finalize_candidate/_compute_sector_strength,
read in full during the audit that produced TRADING_INTELLIGENCE_GAP_
ANALYSIS.md) -- NOT literal calls into that module, since scanner.py's
own functions operate only on a series' own LATEST bar for one live scan,
not across full history for batch training-row generation. The formulas
themselves are identical, applied at every historical bar instead of
only the last one, and are cited by scanner.py line number at each
implementation below so a formula drift between the two can be caught by
inspection.

vwap_distance / opening_gap / intraday_range_normalized are new for
Phase 1 (TRADING_FEATURE_CATALOG.json), each computed here for the first
time in this project.

Every feature at row t uses only information at or before t -- see
tests/test_ml_research_leakage.py for the structural proof this claim is
tested, not merely asserted.
"""
from __future__ import annotations

import hashlib
import inspect
import sys
from dataclasses import dataclass

import numpy as np
import pandas as pd

from market.indicators import compute_indicator_series
from market.data_provider import OHLCV, OHLCVBar

BREAKOUT_LOOKBACK = 20  # scanner.py ScannerConfig.breakout_lookback default
RELATIVE_STRENGTH_LOOKBACK = 20  # scanner.py ScannerConfig.relative_strength_lookback default
SECTOR_STRENGTH_LOOKBACK = 20  # scanner.py reuses the same 20-bar trailing-return window for sector strength

# Equal weights of 1.0 each, matching market_intelligence.config.ScannerConfig's
# own defaults ("not tuned", per that module's own docstring) -- reused here
# unchanged, not re-derived.
COMPOSITE_SCORE_COLUMNS = (
    "trend_score", "momentum_score", "breakout_score",
    "relative_strength_score", "sector_strength_score",
)


def feature_version() -> str:
    """sha256 of this module's own source -- mirrors DecisionConfig.
    version_id()'s existing convention (strategy/config-style version
    hashing). Any formula change below produces a new version; old
    generated datasets stay attributable to the exact code that made
    them."""
    return hashlib.sha256(inspect.getsource(sys.modules[__name__]).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class SymbolBars:
    """One symbol's raw 5-minute OHLCV, with a session_date column derived
    purely from each bar's own timestamp -- never from future information."""

    symbol: str
    frame: pd.DataFrame  # index: naive datetime (IST wall-clock), columns: open/high/low/close/volume


def build_symbol_bars(symbol: str, ohlcv: OHLCV) -> SymbolBars:
    frame = ohlcv.to_dataframe().rename(
        columns={"Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"}
    )
    return SymbolBars(symbol=symbol, frame=frame)


def _session_date(index: pd.DatetimeIndex) -> pd.Series:
    return pd.Series(index.date, index=index)


def _session_vwap(frame: pd.DataFrame, session_date: pd.Series) -> pd.Series:
    """Volume-weighted average price, reset at each session's own open --
    never rolling across days. Uses only the current bar and earlier bars
    of the SAME session (a cumulative sum grouped by session_date, which
    by construction only accumulates forward in time within a group)."""
    typical_price = (frame["high"] + frame["low"] + frame["close"]) / 3.0
    pv = typical_price * frame["volume"]
    cum_pv = pv.groupby(session_date).cumsum()
    cum_vol = frame["volume"].groupby(session_date).cumsum()
    return cum_pv / cum_vol.replace(0.0, np.nan)


def _opening_gap(frame: pd.DataFrame, session_date: pd.Series) -> pd.Series:
    """(session_open - prior_session_close) / prior_session_close, computed
    once per session from that session's own first bar and the PRIOR
    session's own last bar, then forward-filled within the session. NaN
    for a symbol's first observed session (no prior close exists)."""
    session_close = frame["close"].groupby(session_date).transform("last")
    per_session_close = session_close.groupby(session_date).first()
    first_open_by_session = frame["open"].groupby(session_date).transform("first")
    session_dates_sorted = sorted(per_session_close.index)
    prior_close_by_session = {d: np.nan for d in session_dates_sorted}
    for i in range(1, len(session_dates_sorted)):
        prior_close_by_session[session_dates_sorted[i]] = per_session_close[session_dates_sorted[i - 1]]
    prior_close_series = session_date.map(prior_close_by_session)
    return (first_open_by_session - prior_close_series) / prior_close_series


def add_features(bars: SymbolBars, *, benchmark_close: pd.Series | None) -> pd.DataFrame:
    """Returns a DataFrame indexed identically to bars.frame with every
    reused indicator plus every Phase-1-scope new/derived feature. Does
    NOT include sector_strength_score or composite_score -- those require
    the whole universe (add_sector_strength_score, add_composite_score
    below) and are added in a second pass over the already-built
    per-symbol frames."""
    frame = bars.frame
    ohlcv = OHLCV(
        symbol=bars.symbol, interval="5m",
        bars=[
            OHLCVBar(
                timestamp=ts, open=float(row["open"]), high=float(row["high"]),
                low=float(row["low"]), close=float(row["close"]), volume=float(row["volume"]),
            )
            for ts, row in frame.iterrows()
        ],
    )
    indicators = compute_indicator_series(ohlcv)  # reused, unmodified -- no-look-ahead inherited

    out = indicators.copy()
    out["symbol"] = bars.symbol
    session_date = _session_date(out.index)
    out["session_date"] = session_date.values

    # volume_trend (from compute_indicator_series) is the categorical
    # string "increasing"/"decreasing"/"neutral" -- not consumable by
    # StandardScaler/LogisticRegression directly. volume_trend_score is a
    # numeric encoding of the SAME already-computed value, mirroring
    # trend_score's own {-1,0,+1} convention -- not a new feature, just a
    # numeric representation of an existing one for model consumption.
    # The raw string is kept (as volume_trend) for audit/display.
    out["volume_trend_score"] = out["volume_trend"].map({"increasing": 1.0, "decreasing": -1.0, "neutral": 0.0})

    close, high, low = out["close"], out["high"], out["low"]
    sma_20, sma_50, rsi_14 = out["sma_20"], out["sma_50"], out["rsi_14"]

    # trend_score -- scanner.py:201-208, ternary {-1,0,+1}
    out["trend_score"] = np.where(
        (close > sma_20) & (sma_20 > sma_50), 1.0,
        np.where((close < sma_20) & (sma_20 < sma_50), -1.0, 0.0),
    )

    # momentum_score -- scanner.py:210-211
    out["momentum_score"] = (rsi_14 - 50.0) / 50.0

    # breakout_score -- scanner.py:213-216. prior_high excludes the current
    # bar: shift(1) then a 20-bar rolling max, i.e. bars [t-20 .. t-1].
    prior_high = high.shift(1).rolling(window=BREAKOUT_LOOKBACK, min_periods=BREAKOUT_LOOKBACK).max()
    out["breakout_score"] = np.where(prior_high > 0, (close - prior_high) / prior_high, 0.0)
    out.loc[prior_high.isna(), "breakout_score"] = np.nan

    # relative_strength_score -- scanner.py:218-229. reference_close = close
    # RELATIVE_STRENGTH_LOOKBACK bars ago (close.shift(20)).
    reference_close = close.shift(RELATIVE_STRENGTH_LOOKBACK)
    trailing_return = close / reference_close - 1.0
    out["_trailing_return"] = trailing_return  # kept for sector_strength_score's own second pass
    if benchmark_close is not None:
        bench_aligned = benchmark_close.reindex(out.index)
        bench_reference = bench_aligned.shift(RELATIVE_STRENGTH_LOOKBACK)
        benchmark_trailing_return = bench_aligned / bench_reference - 1.0
        out["relative_strength_score"] = trailing_return - benchmark_trailing_return
    else:
        out["relative_strength_score"] = np.nan

    # vwap_distance -- new for Phase 1, TRADING_FEATURE_CATALOG.json
    vwap = _session_vwap(frame, session_date)
    out["vwap_distance"] = (close - vwap) / vwap

    # opening_gap -- new for Phase 1
    out["opening_gap"] = _opening_gap(frame, session_date)

    # intraday_range_normalized -- new for Phase 1
    out["intraday_range_normalized"] = (high - low) / close

    # entry_reference_price -- the next bar's own open, stored on THIS row
    # so the label generator (labels.py) and this feature row always agree
    # on entry price without a second, potentially-diverging computation
    # (PHASE_1_IMPLEMENTATION_SPEC.md Section 5 item 2).
    out["entry_reference_price"] = frame["open"].shift(-1)
    out["entry_reference_session_date"] = pd.Series(session_date.values, index=out.index).shift(-1)

    return out


def add_sector_strength_score(
    symbol_frames: dict[str, pd.DataFrame], sector_map: dict[str, str],
) -> dict[str, pd.DataFrame]:
    """Cross-sectional pass: sector_strength_score = sector-average trailing
    return minus universe-average trailing return, computed over the SAME
    universe these frames belong to (scanner.py:239-270's own convention --
    an internal, universe-relative measure, not an external sector index).
    Requires every symbol's own add_features() output (for `_trailing_
    return` and a shared timestamp index) to already exist -- this is a
    second pass, not folded into add_features() itself, because it needs
    the whole universe simultaneously. NaN for any symbol with no sector
    tag in `sector_map`, matching scanner.py's own None-when-untagged
    behavior exactly.
    """
    trailing_returns = pd.DataFrame({sym: f["_trailing_return"] for sym, f in symbol_frames.items()})
    universe_avg = trailing_returns.mean(axis=1, skipna=True)

    sectors: dict[str, list[str]] = {}
    for sym in symbol_frames:
        sector = sector_map.get(sym)
        if sector is not None:
            sectors.setdefault(sector, []).append(sym)

    sector_avg_by_sector = {
        sector: trailing_returns[members].mean(axis=1, skipna=True) for sector, members in sectors.items()
    }

    out: dict[str, pd.DataFrame] = {}
    for sym, f in symbol_frames.items():
        f = f.copy()
        sector = sector_map.get(sym)
        if sector is None:
            f["sector_strength_score"] = np.nan
        else:
            f["sector_strength_score"] = sector_avg_by_sector[sector] - universe_avg
        out[sym] = f
    return out


def add_composite_score(frame: pd.DataFrame) -> pd.DataFrame:
    """composite_score -- scanner.py:274-280, equal-weighted (1.0 each) sum
    of the 5 COMPOSITE_SCORE_COLUMNS, treating a missing (NaN) sub-score as
    0.0 in the sum -- matching scanner.py's own `(relative_strength_score
    or 0.0)` / `(sector_strength_score or 0.0)` None-coalescing convention
    for the two sub-scores that can be unavailable."""
    frame = frame.copy()
    contributions = [frame[col].fillna(0.0) for col in COMPOSITE_SCORE_COLUMNS]
    frame["composite_score"] = sum(contributions)
    return frame
