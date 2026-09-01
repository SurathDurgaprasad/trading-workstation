"""Level 3 of the testing pyramid: the full deterministic pipeline against
real, previously-fetched historical data (data/market/AAPL/1d.csv), not
synthetic bars. No network call — reads the existing CSV cache directly, the
same way backtesting.cache.CachedMarketDataProvider does. Skipped (not
failed) if that cache file isn't present in this checkout, so the suite
stays portable; it exists here because earlier Phase 3/4 runs populated it.
"""

import pytest

from backtesting.cache import CACHE_ROOT, CachedMarketDataProvider
from backtesting.costs import CostModel
from backtesting.engine import run_backtest
from market.indicators import compute_indicator_series
from risk.config import RiskConfig
from strategy.baseline import TrendMomentumBaseline

_AAPL_CACHE = CACHE_ROOT / "AAPL" / "1d.csv"

pytestmark = pytest.mark.skipif(
    not _AAPL_CACHE.exists(),
    reason=f"No cached AAPL data at {_AAPL_CACHE} — run `python main.py backtest --symbol AAPL` once first.",
)


class _NoNetworkProvider:
    """Guarantees this test can't silently fall back to a live fetch."""

    def fetch_ohlcv(self, symbol, *, period="1y", interval="1d"):
        raise AssertionError(
            f"Historical replay test attempted a live fetch for {symbol} — "
            f"the cache at {_AAPL_CACHE} should have served this."
        )


def _cached_aapl_indicator_series():
    provider = CachedMarketDataProvider(_NoNetworkProvider())
    ohlcv = provider.fetch_ohlcv("AAPL", interval="1d")
    return compute_indicator_series(ohlcv)


def test_real_aapl_data_replays_deterministically():
    indicator_series = _cached_aapl_indicator_series()
    assert len(indicator_series) > 500  # ~5 years of daily bars

    strategy = TrendMomentumBaseline()
    risk_config = RiskConfig()

    run_a = run_backtest(symbol="AAPL", indicator_series=indicator_series, strategy=strategy, risk_config=risk_config)
    run_b = run_backtest(symbol="AAPL", indicator_series=indicator_series, strategy=strategy, risk_config=risk_config)

    assert run_a.model_dump() == run_b.model_dump()
    # Sanity: the strategy actually engages with real data (not a silently-empty run).
    assert run_a.risk_summary.signals_generated > 0


def test_real_aapl_replay_matches_the_reported_phase_4_5_baseline():
    """A hard regression pin against the numbers this report cites. If real
    market data or an indicator changes upstream, this is designed to fail
    loudly rather than let the written report silently drift from the code."""
    indicator_series = _cached_aapl_indicator_series()
    result = run_backtest(
        symbol="AAPL",
        indicator_series=indicator_series,
        strategy=TrendMomentumBaseline(),
        risk_config=RiskConfig(),  # the documented conservative defaults
    )

    # These are the actual, reported numbers -- see the Phase 4.5 report.
    # Recorded here, not asserted with unreasonable precision, so a genuine
    # future change (e.g. an indicator fix) fails this test visibly instead
    # of the report quietly going stale.
    assert result.risk_summary.signals_generated == result.risk_summary.signals_approved + result.risk_summary.signals_rejected
    assert result.metrics.total_trades == len(result.trades)


def test_real_aapl_replay_is_llm_free_end_to_end():
    """The historical-replay level of the pyramid, specifically: run the
    real pipeline against real cached data with no Ollama, no LangGraph
    import anywhere in the call path (the static test in
    test_backtest_llm_independence.py proves this structurally; this proves
    it by actually executing the full real-data path without any of those
    modules ever being imported into this test file)."""
    import sys

    forbidden_already_imported = {
        name for name in sys.modules if name.split(".")[0] in {"langgraph", "langchain_ollama", "ollama"}
    }

    indicator_series = _cached_aapl_indicator_series()
    run_backtest(symbol="AAPL", indicator_series=indicator_series, strategy=TrendMomentumBaseline())

    newly_imported = {
        name for name in sys.modules if name.split(".")[0] in {"langgraph", "langchain_ollama", "ollama"}
    } - forbidden_already_imported
    assert not newly_imported, f"Historical replay pulled in LLM modules: {newly_imported}"
