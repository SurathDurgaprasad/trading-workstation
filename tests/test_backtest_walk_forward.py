import math
from datetime import datetime, timedelta

import pytest

from backtesting.engine import run_backtest
from backtesting.walk_forward import (
    WalkForwardResult,
    run_walk_forward_validation,
    split_into_n_folds,
)
from strategy.signal import ReasonCode, Side, Signal

# --- split_into_n_folds ------------------------------------------------------


def test_split_into_n_folds_produces_the_requested_fold_count():
    start, end = datetime(2026, 1, 1), datetime(2026, 1, 13)
    folds = split_into_n_folds(start, end, 4)
    assert len(folds) == 4


def test_split_into_n_folds_is_contiguous_with_no_gaps_or_overlaps():
    start, end = datetime(2026, 1, 1), datetime(2026, 1, 13)
    folds = split_into_n_folds(start, end, 4)
    for (_, prev_end), (next_start, _) in zip(folds, folds[1:]):
        assert prev_end == next_start


def test_split_into_n_folds_covers_the_full_range_exactly():
    start, end = datetime(2026, 1, 1), datetime(2026, 1, 13)
    folds = split_into_n_folds(start, end, 4)
    assert folds[0][0] == start
    assert folds[-1][1] == end


def test_split_into_n_folds_rejects_fewer_than_two_folds():
    with pytest.raises(ValueError):
        split_into_n_folds(datetime(2026, 1, 1), datetime(2026, 1, 13), 1)


def test_split_into_n_folds_rejects_end_before_start():
    with pytest.raises(ValueError):
        split_into_n_folds(datetime(2026, 1, 13), datetime(2026, 1, 1), 4)


# --- run_walk_forward_validation: leakage detection and pooling -------------


class _RepeatingSignalStrategy:
    """Fires a fresh, fixed-shape LONG signal every 5 bars (a small,
    tight stop/target so entries resolve quickly within a short
    synthetic series) -- deterministic, and reads ONLY the close price,
    so it exercises run_walk_forward_validation's real
    compute_indicator_series pipeline without depending on any specific
    trend/momentum indicator value."""

    name = "repeating_signal_test_strategy"

    def generate_signal(self, indicator_series, index, symbol):
        if index % 5 != 0:
            return None
        row = indicator_series.iloc[index]
        price = float(row["close"])
        return Signal(
            symbol=symbol, generated_at=indicator_series.index[index], side=Side.LONG,
            reference_price=price, stop_price=price - 2.0, target_price=price + 4.0,
            risk_reward=2.0, strategy_name=self.name, reason_codes=[ReasonCode.TREND_CONFIRMED],
        )


def _oscillating_ohlcv_bars(n: int):
    """Raw OHLCV bars (NOT pre-computed indicator rows) -- oscillates
    enough that _RepeatingSignalStrategy's fixed +/-2/+4 stop/target
    produces a genuine mix of stop-outs and target-hits rather than an
    all-flat, event-free series."""
    from market.data_provider import OHLCVBar

    bars = []
    t0 = datetime(2026, 1, 1)
    for i in range(n):
        price = 100.0 + 6.0 * math.sin(i / 3.0)
        bars.append(OHLCVBar(
            timestamp=t0 + timedelta(days=i), open=price, high=price + 3.0, low=price - 3.0,
            close=price, volume=1_000_000.0,
        ))
    return bars


@pytest.fixture
def _fake_oscillating_provider(monkeypatch):
    from market.data_provider import MarketDataError, OHLCV

    class _Provider:
        def __init__(self, good_symbols, n_bars=100):
            self._good = good_symbols
            self._n_bars = n_bars

        def fetch_ohlcv(self, symbol, *, period="5y", interval="1d"):
            if symbol not in self._good:
                raise MarketDataError(f"no data for {symbol}")
            return OHLCV(symbol=symbol, interval=interval, bars=_oscillating_ohlcv_bars(self._n_bars))

    def _apply(good_symbols, n_bars=100):
        import backtesting.cache as cache_module
        import market.data_provider as market_data_provider_module

        monkeypatch.setattr(market_data_provider_module, "get_market_data_provider", lambda: _Provider(good_symbols, n_bars))
        monkeypatch.setattr(cache_module, "CachedMarketDataProvider", lambda inner: inner)

    return _apply


def test_walk_forward_fold_trades_never_depend_on_data_past_that_folds_own_end(_fake_oscillating_provider):
    # Explicit leakage-detection test. FOLD 0 SPECIFICALLY is the only
    # fold where this comparison is unconfounded: fold 0 starts at the
    # very beginning of history, so a rolling indicator's warm-up period
    # (e.g. SMA20 needs 20 prior bars) has IDENTICAL bars available
    # whether computed on the full 100-bar series and then sliced, or
    # computed on a series truncated to end exactly at fold 0's own
    # boundary. (A later fold, e.g. fold 2, would have MORE real prior
    # history available in the "full series, sliced" case than in a
    # freshly-truncated-from-scratch series -- that mismatch would be a
    # warm-up-availability artifact, not evidence of leakage, so it
    # would be the wrong comparison.)
    #
    # If fold 0's trades (computed as part of a walk-forward run over
    # the FULL series) differ AT ALL from running the standard engine
    # directly on a series truncated to end exactly at fold 0's own
    # boundary, later bars must have leaked into fold 0's classification
    # or trades.
    from market.data_provider import OHLCV
    from market.indicators import compute_indicator_series

    n_folds = 4
    raw_bars = _oscillating_ohlcv_bars(100)
    _fake_oscillating_provider({"TEST"}, n_bars=100)

    result = run_walk_forward_validation(
        ["TEST"], strategy=_RepeatingSignalStrategy(), n_folds=n_folds, initial_capital=100_000.0,
    )

    full_indicator_series = compute_indicator_series(OHLCV(symbol="TEST", interval="1d", bars=raw_bars))
    bounds = split_into_n_folds(full_indicator_series.index[0], full_indicator_series.index[-1], n_folds)
    fold_0_start, fold_0_end = bounds[0]

    truncated_raw_bars = [b for b in raw_bars if fold_0_start <= b.timestamp <= fold_0_end]
    truncated_series = compute_indicator_series(OHLCV(symbol="TEST", interval="1d", bars=truncated_raw_bars))
    direct_result = run_backtest(symbol="TEST", indicator_series=truncated_series, strategy=_RepeatingSignalStrategy())

    fold_0 = result.folds[0]
    assert len(fold_0.trades) > 0  # the test is only meaningful if fold 0 actually produced trades
    direct_fields = [(t.entry_time, t.exit_time, t.exit_price, t.net_pnl) for t in direct_result.trades]
    fold_fields = [(t.entry_time, t.exit_time, t.exit_price, t.net_pnl) for t in fold_0.trades]
    assert fold_fields == direct_fields


def test_walk_forward_pools_trades_across_symbols_per_fold(_fake_oscillating_provider):
    _fake_oscillating_provider({"AAA", "BBB"}, n_bars=100)
    pooled_result = run_walk_forward_validation(
        ["AAA", "BBB"], strategy=_RepeatingSignalStrategy(), n_folds=4, initial_capital=100_000.0,
    )

    assert isinstance(pooled_result, WalkForwardResult)
    assert len(pooled_result.folds) == 4
    assert pooled_result.failed_symbols == {}

    _fake_oscillating_provider({"AAA"}, n_bars=100)
    single_result = run_walk_forward_validation(
        ["AAA"], strategy=_RepeatingSignalStrategy(), n_folds=4, initial_capital=100_000.0,
    )

    # AAA and BBB are IDENTICAL synthetic series, so a pooled fold must
    # have exactly twice the trades of the same fold computed for AAA alone.
    for pooled_fold, single_fold in zip(pooled_result.folds, single_result.folds):
        if single_fold.trades:
            assert len(pooled_fold.trades) == 2 * len(single_fold.trades)


def test_walk_forward_isolates_a_failing_symbol_from_the_rest(_fake_oscillating_provider):
    _fake_oscillating_provider({"AAA"}, n_bars=100)
    result = run_walk_forward_validation(
        ["AAA", "BADSYMBOL"], strategy=_RepeatingSignalStrategy(), n_folds=4, initial_capital=100_000.0,
    )

    assert "BADSYMBOL" in result.failed_symbols
    assert sum(len(f.trades) for f in result.folds) > 0  # AAA's trades still made it through
