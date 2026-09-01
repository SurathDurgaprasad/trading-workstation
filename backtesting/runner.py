from dataclasses import dataclass

import pandas as pd

from backtesting.cache import CachedMarketDataProvider
from backtesting.costs import CostModel
from backtesting.engine import BacktestResult, run_backtest
from backtesting.splits import PeriodSplit, split_periods
from market.data_provider import get_market_data_provider
from market.indicators import compute_indicator_series
from risk.config import RiskConfig
from strategy.contracts import Strategy


@dataclass
class FullBacktestRun:
    full: BacktestResult
    development: BacktestResult
    validation: BacktestResult
    out_of_sample: BacktestResult
    split: PeriodSplit


def run_full_backtest(
    *,
    symbol: str,
    strategy: Strategy,
    period: str = "5y",
    interval: str = "1d",
    initial_capital: float = 100_000.0,
    cost_model: CostModel | None = None,
    risk_config: RiskConfig | None = None,
    use_cache: bool = True,
) -> FullBacktestRun:
    """Fetch (cached) history, compute indicators once, then run the full
    period plus the three chronological sub-periods with identical, fixed
    strategy AND risk parameters — no refitting per period (spec §16)."""
    provider = CachedMarketDataProvider(get_market_data_provider()) if use_cache else get_market_data_provider()
    ohlcv = provider.fetch_ohlcv(symbol, period=period, interval=interval)
    indicator_series = compute_indicator_series(ohlcv)

    split = split_periods(indicator_series.index[0], indicator_series.index[-1])

    full = run_backtest(
        symbol=symbol,
        indicator_series=indicator_series,
        strategy=strategy,
        cost_model=cost_model,
        initial_capital=initial_capital,
        risk_config=risk_config,
        period_label="full",
    )
    development = run_backtest(
        symbol=symbol,
        indicator_series=_slice_period(indicator_series, split.development_start, split.development_end),
        strategy=strategy,
        cost_model=cost_model,
        initial_capital=initial_capital,
        risk_config=risk_config,
        period_label="development",
    )
    validation = run_backtest(
        symbol=symbol,
        indicator_series=_slice_period(indicator_series, split.validation_start, split.validation_end),
        strategy=strategy,
        cost_model=cost_model,
        initial_capital=initial_capital,
        risk_config=risk_config,
        period_label="validation",
    )
    out_of_sample = run_backtest(
        symbol=symbol,
        indicator_series=_slice_period(indicator_series, split.out_of_sample_start, split.out_of_sample_end),
        strategy=strategy,
        cost_model=cost_model,
        initial_capital=initial_capital,
        risk_config=risk_config,
        period_label="out_of_sample",
    )

    return FullBacktestRun(
        full=full,
        development=development,
        validation=validation,
        out_of_sample=out_of_sample,
        split=split,
    )


def _slice_period(indicator_series: pd.DataFrame, start, end) -> pd.DataFrame:
    return indicator_series.loc[(indicator_series.index >= start) & (indicator_series.index <= end)]
