"""Weekend hardening, Phase 7 (strategy edge validation) -- a single
symbol's backtest produces 16-29 trades over 5 years, far too small a
sample to say anything statistically meaningful about whether a strategy
has a real edge (learning.profitability's own established rule-of-thumb
floor is 30 resolved observations before any verdict is attempted at
all). This module pools EVERY trade's per-trade return across an entire
universe of symbols into ONE combined sample, reusing learning.
profitability.compute_profitability_report_from_returns -- the SAME
Wilson-CI/mean-CI statistical machinery already used for prediction
evidence, so this project states one statistical standard for "is there
an edge," not two competing ones in two different places.

Deliberately runs each symbol's FULL period only (not the per-symbol
train/development/validation/out-of-sample split backtesting.runner
already provides) -- that split answers a different question ("is this
specific symbol's forward performance still holding up"), tested and
available via `backtest --symbol X`. This module answers "does this
strategy show ANY edge anywhere, pooled across the whole available
universe" -- a one-shot scientific question, not a per-symbol
development-process check.

One bad/missing symbol (a cache miss, an unparseable series) must never
abort scoring the rest of the universe -- same per-symbol isolation
posture market_intelligence.scanner and shadow-run's own per-symbol loop
already use.
"""

from dataclasses import dataclass, field

from backtesting.cache import CachedMarketDataProvider
from backtesting.costs import CostModel
from backtesting.engine import BacktestResult, run_backtest
from backtesting.trade import Trade
from market.data_provider import MarketDataError, get_market_data_provider
from market.indicators import compute_indicator_series
from risk.config import RiskConfig
from strategy.contracts import Strategy


@dataclass
class UniverseBacktestResult:
    per_symbol: dict[str, BacktestResult] = field(default_factory=dict)
    failed_symbols: dict[str, str] = field(default_factory=dict)
    """symbol -> human-readable reason it could not be backtested at all
    (data fetch failure, no usable bars) -- never silently dropped."""

    @property
    def pooled_trades(self) -> list[Trade]:
        trades: list[Trade] = []
        for result in self.per_symbol.values():
            trades.extend(result.trades)
        return trades


def per_trade_returns(trades: list[Trade]) -> list[float]:
    """Fractional return per trade (net_pnl / capital actually committed
    to that trade) -- the same "mean per-trade return" semantics
    learning.profitability.ProfitabilityReport already documents, so a
    pooled backtest verdict and a pooled prediction-evidence verdict mean
    the exact same thing when compared side by side. Skips a trade whose
    entry_price or quantity is non-positive (cannot compute a return
    fraction) rather than dividing by zero or fabricating one -- not
    expected to occur given PaperTradingEngine/backtesting.engine's own
    invariants, but this function makes no assumption about its caller."""
    return [
        trade.net_pnl / (trade.entry_price * trade.quantity)
        for trade in trades
        if trade.entry_price > 0 and trade.quantity > 0
    ]


def run_universe_backtest(
    symbols: list[str],
    *,
    strategy: Strategy,
    period: str = "5y",
    interval: str = "1d",
    initial_capital: float = 100_000.0,
    cost_model: CostModel | None = None,
    risk_config: RiskConfig | None = None,
    use_cache: bool = True,
) -> UniverseBacktestResult:
    provider = CachedMarketDataProvider(get_market_data_provider()) if use_cache else get_market_data_provider()
    result = UniverseBacktestResult()

    for symbol in symbols:
        try:
            ohlcv = provider.fetch_ohlcv(symbol, period=period, interval=interval)
            indicator_series = compute_indicator_series(ohlcv)
        except (MarketDataError, ValueError) as exc:
            result.failed_symbols[symbol] = str(exc)
            continue

        result.per_symbol[symbol] = run_backtest(
            symbol=symbol,
            indicator_series=indicator_series,
            strategy=strategy,
            cost_model=cost_model,
            initial_capital=initial_capital,
            risk_config=risk_config,
        )

    return result
