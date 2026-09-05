"""Strategy science, Phase 7 (walk-forward validation). Extends Phase 2's
temporal robustness (a single 60/20/20 development/validation/out-of-
sample split) into MANY sequential, non-overlapping folds across each
symbol's own available history -- the question here is not "does this
one particular split look consistent" but "is whatever edge (or lack of
one) exists stable across MANY independent rolling windows, or does it
only ever appear in one cherry-picked slice."

TrendMomentumBaseline has no fitted/trainable parameters -- there is no
"training" step to walk forward through. What IS meaningful here is
running the SAME frozen, deterministic rule independently on each of N
sequential time windows and pooling by fold index, exactly mirroring
backtesting.universe.run_universe_backtest_by_period's own established
convention: each symbol is split PROPORTIONALLY across ITS OWN
available history (symbols have different cache start/end dates), then
pooled by fold index/label across the universe -- NOT by one shared
calendar window. A "fold 1" trade from AAPL and a "fold 1" trade from
RELIANCE.NS are pooled together despite covering different actual
calendar dates, the same way development/validation/out-of-sample
trades already are elsewhere in this project.

Drives backtesting.engine.run_backtest UNMODIFIED on each windowed
slice -- no new execution logic, no new stop/target/entry mechanic; the
only new code here is the N-way proportional date splitter and the
per-fold pooling. See tests/test_backtest_walk_forward.py's own
leakage-detection test for the explicit proof that a given fold's
trades never depend on data past that fold's own end boundary.
"""

from dataclasses import dataclass, field
from datetime import datetime

from backtesting.costs import CostModel
from backtesting.trade import Trade
from learning.profitability import ProfitabilityReport, compute_profitability_report_from_returns
from risk.config import RiskConfig
from strategy.contracts import Strategy


def split_into_n_folds(start: datetime, end: datetime, n_folds: int) -> list[tuple[datetime, datetime]]:
    """N equal-length, sequential, non-overlapping, contiguous windows
    covering [start, end] -- a direct generalization of backtesting.
    splits.split_periods's own 3-way proportional split to an arbitrary
    fold count. Deliberately a SEPARATE function rather than a change to
    split_periods itself: that module's own 60/20/20 development/
    validation/out-of-sample split is already relied upon, tested, and
    referenced by name throughout this project -- this is new,
    additional infrastructure, not a replacement."""
    if n_folds < 2:
        raise ValueError("n_folds must be at least 2 (a single fold is not a walk-forward validation).")
    if end <= start:
        raise ValueError("end must be after start.")

    total = end - start
    fold_length = total / n_folds
    folds = []
    for i in range(n_folds):
        fold_start = start + fold_length * i
        fold_end = end if i == n_folds - 1 else start + fold_length * (i + 1)
        folds.append((fold_start, fold_end))
    return folds


@dataclass
class WalkForwardFoldResult:
    fold_index: int
    trades: list[Trade]
    report: ProfitabilityReport


@dataclass
class WalkForwardResult:
    folds: list[WalkForwardFoldResult]
    failed_symbols: dict[str, str] = field(default_factory=dict)


def run_walk_forward_validation(
    symbols: list[str],
    *,
    strategy: Strategy,
    n_folds: int = 6,
    period: str = "5y",
    interval: str = "1d",
    initial_capital: float = 100_000.0,
    cost_model: CostModel | None = None,
    risk_config: RiskConfig | None = None,
    use_cache: bool = True,
) -> WalkForwardResult:
    """Fetches each symbol's own indicator series once, splits it into
    n_folds proportional windows via split_into_n_folds, runs the
    standard (unmodified) backtesting.engine.run_backtest independently
    on each windowed slice, and pools trades by fold index across the
    whole universe -- one symbol's own indicator warm-up/rolling-window
    calculation is computed ONCE over its full fetched series and then
    SLICED per fold (never recomputed per fold), which is safe precisely
    because a rolling indicator's value at any bar depends only on prior
    bars, never later ones (see this module's own leakage-detection
    test)."""
    from backtesting.cache import CachedMarketDataProvider
    from backtesting.engine import run_backtest
    from backtesting.universe import per_trade_returns
    from market.data_provider import MarketDataError, get_market_data_provider
    from market.indicators import compute_indicator_series

    provider = CachedMarketDataProvider(get_market_data_provider()) if use_cache else get_market_data_provider()
    failed_symbols: dict[str, str] = {}
    fold_trades: list[list[Trade]] = [[] for _ in range(n_folds)]

    for symbol in symbols:
        try:
            ohlcv = provider.fetch_ohlcv(symbol, period=period, interval=interval)
            indicator_series = compute_indicator_series(ohlcv)
        except (MarketDataError, ValueError) as exc:
            failed_symbols[symbol] = str(exc)
            continue

        if indicator_series.empty:
            failed_symbols[symbol] = "No indicator data (empty series)."
            continue

        bounds = split_into_n_folds(indicator_series.index[0], indicator_series.index[-1], n_folds)
        for i, (fold_start, fold_end) in enumerate(bounds):
            sliced = indicator_series.loc[(indicator_series.index >= fold_start) & (indicator_series.index <= fold_end)]
            if sliced.empty:
                continue
            result = run_backtest(
                symbol=symbol, indicator_series=sliced, strategy=strategy, cost_model=cost_model,
                initial_capital=initial_capital, risk_config=risk_config,
            )
            fold_trades[i].extend(result.trades)

    folds = [
        WalkForwardFoldResult(
            fold_index=i, trades=fold_trades[i],
            report=compute_profitability_report_from_returns(per_trade_returns(fold_trades[i])),
        )
        for i in range(n_folds)
    ]
    return WalkForwardResult(folds=folds, failed_symbols=failed_symbols)
