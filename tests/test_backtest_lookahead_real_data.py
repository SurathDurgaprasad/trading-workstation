"""Phase 8 sec7: the existing look-ahead protections (test_backtest_lookahead.py)
are proven on synthetic fixtures. This adds the same control on REAL market
data: truncating history at bar N must not change any trade whose entry
happened before bar N in the full run -- except the truncated run's own
final position, which is legitimately force-closed early (END_OF_DATA)
purely because its data ran out there, not because of a look-ahead leak.
"""
import pytest

from backtesting.cache import CACHE_ROOT, CachedMarketDataProvider
from backtesting.engine import run_backtest
from market.indicators import compute_indicator_series
from strategy.baseline import TrendMomentumBaseline

_AAPL_CACHE = CACHE_ROOT / "AAPL" / "1d.csv"


class _NoNetworkProvider:
    def fetch_ohlcv(self, symbol, *, period="1y", interval="1d"):
        raise AssertionError(f"Real-data lookahead test attempted a live fetch for {symbol} — cache should have served this.")


@pytest.mark.skipif(not _AAPL_CACHE.exists(), reason=f"No cached AAPL data at {_AAPL_CACHE}")
def test_truncating_real_aapl_history_does_not_change_earlier_trades():
    provider = CachedMarketDataProvider(_NoNetworkProvider())
    ohlcv = provider.fetch_ohlcv("AAPL", interval="1d")
    series = compute_indicator_series(ohlcv)
    strategy = TrendMomentumBaseline()

    full_result = run_backtest(symbol="AAPL", indicator_series=series, strategy=strategy, initial_capital=100_000.0)

    cutoff = 800
    cutoff_ts = series.index[cutoff]
    truncated_result = run_backtest(symbol="AAPL", indicator_series=series.iloc[:cutoff], strategy=strategy, initial_capital=100_000.0)

    full_before_cutoff = [t for t in full_result.trades if t.entry_time < cutoff_ts]
    truncated_before_cutoff = [t for t in truncated_result.trades if t.entry_time < cutoff_ts]

    # The truncated run's own last trade may be legitimately forced closed
    # early purely because its data ran out at the truncation boundary --
    # exclude only that one, expected difference from the comparison.
    if truncated_before_cutoff and truncated_before_cutoff[-1].exit_reason.value == "END_OF_DATA":
        truncated_comparable = truncated_before_cutoff[:-1]
    else:
        truncated_comparable = truncated_before_cutoff
    full_comparable = full_before_cutoff[: len(truncated_comparable)]

    assert len(truncated_comparable) > 5  # sanity: the control actually exercises multiple real trades

    def fields(t):
        return (t.entry_time.isoformat(), t.entry_price, t.exit_time.isoformat(), t.exit_price, t.quantity, t.net_pnl, t.exit_reason.value)

    assert [fields(a) for a in full_comparable] == [fields(b) for b in truncated_comparable]
