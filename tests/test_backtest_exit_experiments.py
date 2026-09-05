from datetime import datetime

import pytest

from backtesting.costs import CostModel
from backtesting.engine import run_backtest
from backtesting.exit_experiments import run_breakeven_stop_backtest, run_partial_profit_backtest
from backtesting.trade import ExitReason
from strategy.signal import ReasonCode, Side, Signal
from tests.conftest import make_bar, make_indicator_series

_ZERO_COST = CostModel(brokerage_per_fill=0.0, fees_pct=0.0, taxes_pct=0.0, entry_slippage_bps=0.0, exit_slippage_bps=0.0)


class _OneShotStrategy:
    """Identical to test_backtest_execution.py's own helper -- emits
    exactly one fixed signal at a chosen bar index, nothing else."""

    name = "one_shot_test_strategy"

    def __init__(self, *, at_index: int, stop_price: float, target_price: float):
        self._at_index = at_index
        self._stop_price = stop_price
        self._target_price = target_price
        self._fired = False

    def generate_signal(self, indicator_series, index, symbol):
        if index != self._at_index or self._fired:
            return None
        self._fired = True
        row = indicator_series.iloc[index]
        return Signal(
            symbol=symbol, generated_at=indicator_series.index[index], side=Side.LONG,
            reference_price=float(row["close"]), stop_price=self._stop_price, target_price=self._target_price,
            risk_reward=2.0, strategy_name=self.name, reason_codes=[ReasonCode.TREND_CONFIRMED],
        )


def _fields(trades):
    return [(t.entry_time, t.entry_price, t.exit_time, t.exit_price, t.exit_reason.value, t.net_pnl, t.r_multiple) for t in trades]


# --- control case: identical to the standard engine when +1R is never reached --


def test_breakeven_experiment_matches_standard_engine_when_1r_never_reached():
    # Entry 100, stop 90 (risk=10) -- +1R would need a high of >=110.
    # This series never gets there (max high=106), so the breakeven logic
    # must never trigger, and results must be BYTE-IDENTICAL to the
    # standard, unmodified engine.
    bars = [
        make_bar(close=100.0),  # bar 0: signal fires here
        make_bar(open=100.0, high=105.0, low=98.0, close=102.0),   # bar 1: entry fill
        make_bar(open=102.0, high=106.0, low=88.0, close=90.0),    # bar 2: stops out at 90
    ]
    series = make_indicator_series(bars)

    standard_result = run_backtest(
        symbol="TEST", indicator_series=series, strategy=_OneShotStrategy(at_index=0, stop_price=90.0, target_price=100_000.0),
        cost_model=_ZERO_COST, initial_capital=100_000.0,
    )
    experimental_result = run_breakeven_stop_backtest(
        symbol="TEST", indicator_series=series, strategy=_OneShotStrategy(at_index=0, stop_price=90.0, target_price=100_000.0),
        cost_model=_ZERO_COST, initial_capital=100_000.0,
    )

    assert len(standard_result.trades) == len(experimental_result.trades) == 1
    assert _fields(standard_result.trades) == _fields(experimental_result.trades)
    assert standard_result.trades[0].exit_reason == ExitReason.STOP
    assert standard_result.trades[0].exit_price == pytest.approx(90.0)


# --- divergence case: +1R IS reached, breakeven move changes the outcome -------


def test_breakeven_move_turns_a_would_be_loss_into_a_wash():
    # Entry 100, stop 90 (risk=10), target far away (never reached).
    # Bar 1 (fill bar): high=112 -> unrealized R = (112-100)/10 = 1.2 >= 1,
    # breakeven triggers (current stop -> 100). Bar 1's own low=101 stays
    # ABOVE the new breakeven stop, so no same-bar exit. Bar 2: low=85
    # drops through the (now-breakeven) stop at 100.
    #
    # STANDARD engine: stop was NEVER moved -- bar 2's low=85 <= original
    # stop (90) -> exits at 90, a real -10/share loss.
    # EXPERIMENTAL engine: stop moved to 100 on bar 1 -> bar 2's low=85
    # <= 100 -> exits at 100 (breakeven), net_pnl ~= 0 (zero cost model),
    # not a loss.
    bars = [
        make_bar(close=100.0),
        make_bar(open=100.0, high=112.0, low=101.0, close=105.0),
        make_bar(open=105.0, high=106.0, low=85.0, close=90.0),
    ]
    series = make_indicator_series(bars)

    standard_result = run_backtest(
        symbol="TEST", indicator_series=series, strategy=_OneShotStrategy(at_index=0, stop_price=90.0, target_price=100_000.0),
        cost_model=_ZERO_COST, initial_capital=100_000.0,
    )
    experimental_result = run_breakeven_stop_backtest(
        symbol="TEST", indicator_series=series, strategy=_OneShotStrategy(at_index=0, stop_price=90.0, target_price=100_000.0),
        cost_model=_ZERO_COST, initial_capital=100_000.0,
    )

    assert len(standard_result.trades) == len(experimental_result.trades) == 1
    standard_trade = standard_result.trades[0]
    experimental_trade = experimental_result.trades[0]

    assert standard_trade.exit_price == pytest.approx(90.0)
    assert standard_trade.net_pnl < 0
    assert standard_trade.r_multiple == pytest.approx(-1.0)

    assert experimental_trade.exit_price == pytest.approx(100.0)
    assert experimental_trade.net_pnl == pytest.approx(0.0)
    assert experimental_trade.r_multiple == pytest.approx(0.0)
    # r_multiple must use the ORIGINAL risk distance (10), not the
    # near-zero distance the moved stop would imply -- confirms the
    # exact bug this module's own docstring says reusing
    # backtesting.execution.OpenPosition would silently cause.
    assert experimental_trade.stop_price == pytest.approx(90.0)  # Trade records the ORIGINAL stop for audit purposes


def test_breakeven_move_same_bar_as_reaching_1r_and_reversing_exits_at_breakeven_not_original_stop():
    # A single bar reaches +1R AND its own low is below the new breakeven
    # stop -- the breakeven move must be evaluated BEFORE the stop check
    # within that same bar, so the exit is at breakeven (100), never the
    # original stop (90).
    bars = [
        make_bar(close=100.0),
        make_bar(open=100.0, high=115.0, low=95.0, close=98.0),
    ]
    series = make_indicator_series(bars)

    result = run_breakeven_stop_backtest(
        symbol="TEST", indicator_series=series, strategy=_OneShotStrategy(at_index=0, stop_price=90.0, target_price=100_000.0),
        cost_model=_ZERO_COST, initial_capital=100_000.0,
    )

    assert len(result.trades) == 1
    assert result.trades[0].exit_price == pytest.approx(100.0)
    assert result.trades[0].exit_reason == ExitReason.STOP


def test_breakeven_experiment_still_supports_target_hits():
    bars = [
        make_bar(close=100.0),
        make_bar(open=100.0, high=101.0, low=99.0, close=100.5),  # entry fill, no +1R yet
        # high=125 also crosses +1R (risk=10, so +1R needs high>=110) --
        # breakeven moves to 100 this SAME bar, but low=105 stays clearly
        # ABOVE that new stop, so this is an unambiguous TARGET hit, not
        # a same-bar stop/target collision (covered by its own dedicated
        # test above).
        make_bar(open=100.5, high=125.0, low=105.0, close=120.0),
    ]
    series = make_indicator_series(bars)

    result = run_breakeven_stop_backtest(
        symbol="TEST", indicator_series=series, strategy=_OneShotStrategy(at_index=0, stop_price=90.0, target_price=120.0),
        cost_model=_ZERO_COST, initial_capital=100_000.0,
    )

    assert len(result.trades) == 1
    assert result.trades[0].exit_reason == ExitReason.TARGET
    assert result.trades[0].exit_price == pytest.approx(120.0)


def test_breakeven_experiment_end_of_data_force_close_still_works():
    bars = [
        make_bar(close=100.0),
        make_bar(open=100.0, high=101.0, low=99.0, close=100.5),
        make_bar(open=100.5, high=103.0, low=100.0, close=102.0),  # never hits stop/target, data ends
    ]
    series = make_indicator_series(bars)

    result = run_breakeven_stop_backtest(
        symbol="TEST", indicator_series=series, strategy=_OneShotStrategy(at_index=0, stop_price=90.0, target_price=200.0),
        cost_model=_ZERO_COST, initial_capital=100_000.0,
    )

    assert len(result.trades) == 1
    assert result.trades[0].exit_reason == ExitReason.END_OF_DATA


def test_breakeven_experiment_raises_on_empty_series():
    import pandas as pd

    with pytest.raises(ValueError):
        run_breakeven_stop_backtest(symbol="TEST", indicator_series=pd.DataFrame(), strategy=_OneShotStrategy(at_index=0, stop_price=90.0, target_price=100.0))


# --- run_universe_breakeven_experiment (dev/val/oos pooling) --------------------


def _long_bars(n: int = 200, *, start: float = 100.0, step: float = 0.3):
    from datetime import timedelta

    from market.data_provider import OHLCVBar

    bars = []
    t0 = datetime(2026, 1, 1)
    for i in range(n):
        close = start + step * i
        bars.append(OHLCVBar(
            timestamp=t0 + timedelta(days=i), open=close, high=close + 1.0, low=close - 1.0,
            close=close, volume=1_000_000.0,
        ))
    return bars


class _LongOneShotStrategy:
    """Fires once, early, so run_breakeven_stop_backtest has real bars
    to process across the whole 200-bar series after entry."""

    name = "long_one_shot_test_strategy"

    def __init__(self):
        self._fired = False

    def generate_signal(self, indicator_series, index, symbol):
        if index != 5 or self._fired:
            return None
        self._fired = True
        row = indicator_series.iloc[index]
        return Signal(
            symbol=symbol, generated_at=indicator_series.index[index], side=Side.LONG,
            reference_price=float(row["close"]), stop_price=90.0, target_price=90_000.0,
            risk_reward=2.0, strategy_name=self.name, reason_codes=[ReasonCode.TREND_CONFIRMED],
        )


@pytest.fixture
def _fake_universe_provider(monkeypatch):
    from market.data_provider import MarketDataError, OHLCV

    class _Provider:
        def __init__(self, good_symbols):
            self._good = good_symbols

        def fetch_ohlcv(self, symbol, *, period="5y", interval="1d"):
            if symbol not in self._good:
                raise MarketDataError(f"no data for {symbol}")
            return OHLCV(symbol=symbol, interval=interval, bars=_long_bars())

    def _apply(good_symbols):
        import market.data_provider as market_data_provider_module

        monkeypatch.setattr(market_data_provider_module, "get_market_data_provider", lambda: _Provider(good_symbols))

        # run_universe_breakeven_experiment wraps the provider in
        # CachedMarketDataProvider -- "AAA"/"BBB"/"BADSYMBOL" are not
        # real cached symbols, so a cache MISS would otherwise WRITE a
        # real file under data/market/ as a side effect. Bypass caching
        # entirely (same `lambda inner: inner` pattern established
        # earlier this session for the identical concern in
        # test_backtest_universe.py).
        import backtesting.cache as cache_module

        monkeypatch.setattr(cache_module, "CachedMarketDataProvider", lambda inner: inner)

    return _apply


def test_run_universe_breakeven_experiment_pools_across_symbols(_fake_universe_provider):
    _fake_universe_provider({"AAA", "BBB"})

    from backtesting.exit_experiments import UniverseBreakevenExperimentResult, run_universe_breakeven_experiment

    result = run_universe_breakeven_experiment(["AAA", "BBB"], strategy=_LongOneShotStrategy(), initial_capital=1_000.0)

    assert isinstance(result, UniverseBreakevenExperimentResult)
    assert result.failed_symbols == {}
    assert isinstance(result.development_trades, list)
    assert isinstance(result.validation_trades, list)
    assert isinstance(result.out_of_sample_trades, list)


def test_run_universe_breakeven_experiment_isolates_a_failing_symbol(_fake_universe_provider):
    _fake_universe_provider({"AAA"})

    from backtesting.exit_experiments import run_universe_breakeven_experiment

    result = run_universe_breakeven_experiment(["AAA", "BADSYMBOL"], strategy=_LongOneShotStrategy(), initial_capital=1_000.0)

    assert "BADSYMBOL" in result.failed_symbols


# =================================================================
# H_EXIT_002: partial profit-take at +1R, remainder runs unmodified
# =================================================================


def test_partial_experiment_matches_standard_engine_when_1r_never_reached():
    # Identical to the H_EXIT_001 control case -- partial level (entry+risk
    # = 110) is never crossed (max high = 106), so the partial-take logic
    # must never fire and the single resulting trade must be BYTE-IDENTICAL
    # to the standard, unmodified engine.
    bars = [
        make_bar(close=100.0),
        make_bar(open=100.0, high=105.0, low=98.0, close=102.0),
        make_bar(open=102.0, high=106.0, low=88.0, close=90.0),
    ]
    series = make_indicator_series(bars)

    standard_result = run_backtest(
        symbol="TEST", indicator_series=series, strategy=_OneShotStrategy(at_index=0, stop_price=90.0, target_price=100_000.0),
        cost_model=_ZERO_COST, initial_capital=100_000.0,
    )
    experimental_result = run_partial_profit_backtest(
        symbol="TEST", indicator_series=series, strategy=_OneShotStrategy(at_index=0, stop_price=90.0, target_price=100_000.0),
        cost_model=_ZERO_COST, initial_capital=100_000.0,
    )

    assert len(standard_result.trades) == len(experimental_result.trades) == 1
    assert _fields(standard_result.trades) == _fields(experimental_result.trades)


def test_partial_experiment_takes_half_off_at_1r_then_remainder_hits_target():
    # Entry 100, stop 90 (risk=10) -> partial level = 110. Target = 130.
    # Bar 1 (the fill bar itself) reaches high=112 >= 110 -> partial
    # triggers THIS SAME bar (low=99 stays above the original stop, no
    # ambiguity). Bar 2's high=135 >= target(130) -> remainder closes at
    # the exact target price.
    bars = [
        make_bar(close=100.0),
        make_bar(open=100.0, high=112.0, low=99.0, close=105.0),
        make_bar(open=105.0, high=135.0, low=100.0, close=130.0),
    ]
    series = make_indicator_series(bars)

    result = run_partial_profit_backtest(
        symbol="TEST", indicator_series=series, strategy=_OneShotStrategy(at_index=0, stop_price=90.0, target_price=130.0),
        cost_model=_ZERO_COST, initial_capital=100_000.0,
    )

    assert len(result.trades) == 2
    partial, remainder = result.trades

    assert partial.exit_reason == ExitReason.PARTIAL_TARGET
    assert partial.exit_price == pytest.approx(110.0)  # entry(100) + 1R(10), not the bar's high
    assert partial.net_pnl > 0

    assert remainder.exit_reason == ExitReason.TARGET
    assert remainder.exit_price == pytest.approx(130.0)
    assert remainder.net_pnl > 0

    # quantity partition invariant: partial = original // 2, remainder =
    # original - original // 2 -- so remainder is either equal to partial
    # (even original quantity) or exactly one share more (odd original).
    assert remainder.quantity in (partial.quantity, partial.quantity + 1)
    assert partial.quantity >= 1


def test_partial_experiment_same_bar_ambiguity_stop_wins_no_partial_credit():
    # A single bar's high (115) would cross the partial level (110) AND
    # its low (85) crosses the original stop (90) -- same conservative
    # same-bar rule as everywhere else in this codebase: assume the stop
    # was hit first, so NO partial credit is given; the FULL original
    # quantity closes at the original stop as a single trade.
    bars = [
        make_bar(close=100.0),
        make_bar(open=100.0, high=115.0, low=85.0, close=90.0),
    ]
    series = make_indicator_series(bars)

    result = run_partial_profit_backtest(
        symbol="TEST", indicator_series=series, strategy=_OneShotStrategy(at_index=0, stop_price=90.0, target_price=100_000.0),
        cost_model=_ZERO_COST, initial_capital=100_000.0,
    )

    assert len(result.trades) == 1
    assert result.trades[0].exit_reason == ExitReason.STOP
    assert result.trades[0].exit_price == pytest.approx(90.0)


def test_partial_experiment_skips_partial_when_quantity_is_too_small_to_split():
    # A single-share position (forced via a small enough initial_capital
    # that RiskEngine's own 0.5%-of-equity sizing floors to exactly 1
    # share: risk_budget=2500*0.005=12.5, risk_per_unit=10 -> quantity=1)
    # cannot be split in half -- the partial-take logic must never fire,
    # and the position must run exactly like the standard engine all the
    # way to its real exit, ignoring that the partial level (110) was
    # crossed on bar 1.
    bars = [
        make_bar(close=100.0),
        make_bar(open=100.0, high=112.0, low=99.0, close=105.0),
        make_bar(open=105.0, high=135.0, low=100.0, close=130.0),
    ]
    series = make_indicator_series(bars)

    result = run_partial_profit_backtest(
        symbol="TEST", indicator_series=series, strategy=_OneShotStrategy(at_index=0, stop_price=90.0, target_price=130.0),
        cost_model=_ZERO_COST, initial_capital=2500.0,
    )

    assert len(result.trades) == 1
    assert result.trades[0].quantity == 1
    assert result.trades[0].exit_reason == ExitReason.TARGET
    assert result.trades[0].exit_price == pytest.approx(130.0)


def test_partial_experiment_remainder_can_still_stop_out_after_a_locked_in_partial_gain():
    # The core mechanic under test: a partial-take locks in some profit
    # even when the remainder later reverses into a real loss.
    bars = [
        make_bar(close=100.0),
        make_bar(open=100.0, high=112.0, low=99.0, close=105.0),   # partial triggers this bar
        make_bar(open=105.0, high=106.0, low=85.0, close=90.0),    # remainder stops out
    ]
    series = make_indicator_series(bars)

    result = run_partial_profit_backtest(
        symbol="TEST", indicator_series=series, strategy=_OneShotStrategy(at_index=0, stop_price=90.0, target_price=100_000.0),
        cost_model=_ZERO_COST, initial_capital=100_000.0,
    )

    assert len(result.trades) == 2
    partial, remainder = result.trades
    assert partial.exit_reason == ExitReason.PARTIAL_TARGET
    assert partial.net_pnl > 0
    assert remainder.exit_reason == ExitReason.STOP
    assert remainder.exit_price == pytest.approx(90.0)
    assert remainder.net_pnl < 0


def test_partial_experiment_end_of_data_force_closes_the_remainder():
    bars = [
        make_bar(close=100.0),
        make_bar(open=100.0, high=112.0, low=99.0, close=105.0),   # partial triggers this bar
        make_bar(open=105.0, high=108.0, low=100.0, close=106.0),  # remainder open, data ends
    ]
    series = make_indicator_series(bars)

    result = run_partial_profit_backtest(
        symbol="TEST", indicator_series=series, strategy=_OneShotStrategy(at_index=0, stop_price=90.0, target_price=500.0),
        cost_model=_ZERO_COST, initial_capital=100_000.0,
    )

    assert len(result.trades) == 2
    partial, remainder = result.trades
    assert partial.exit_reason == ExitReason.PARTIAL_TARGET
    assert remainder.exit_reason == ExitReason.END_OF_DATA


def test_partial_experiment_raises_on_empty_series():
    import pandas as pd

    with pytest.raises(ValueError):
        run_partial_profit_backtest(symbol="TEST", indicator_series=pd.DataFrame(), strategy=_OneShotStrategy(at_index=0, stop_price=90.0, target_price=100.0))


def test_partial_experiment_does_not_double_count_the_single_entry_fee_across_both_legs():
    # There was exactly ONE real entry fill (the whole original quantity,
    # bought in one order) and TWO real exit fills (the partial-take order
    # and the remainder's own final order). Each leg's reported `costs`
    # must carry only a pro-rata SHARE of the one entry fee plus its own
    # full exit fee -- never the full entry fee twice. Using the default
    # CostModel (flat brokerage_per_fill=20.0, fees_pct=taxes_pct=0.0, so
    # cost_for_fill is a CONSTANT 20.0 regardless of notional) makes this
    # unambiguous: summed costs across both legs must equal exactly
    # 3 fills worth (60.0), never 4 fills worth (80.0, the double-count bug).
    bars = [
        make_bar(close=100.0),
        make_bar(open=100.0, high=118.0, low=99.0, close=105.0),
        make_bar(open=105.0, high=135.0, low=100.0, close=130.0),
    ]
    series = make_indicator_series(bars)

    result = run_partial_profit_backtest(
        symbol="TEST", indicator_series=series, strategy=_OneShotStrategy(at_index=0, stop_price=90.0, target_price=130.0),
        cost_model=CostModel(), initial_capital=100_000.0,
    )

    assert len(result.trades) == 2
    total_costs = sum(t.costs for t in result.trades)
    assert total_costs == pytest.approx(60.0)


@pytest.fixture
def _fake_partial_universe_provider(monkeypatch):
    """Same fixture as _fake_universe_provider (H_EXIT_001) -- duplicated
    rather than parametrized/shared because pytest fixtures returning a
    closure are simplest to read this way, and this file already
    duplicates the analogous H_EXIT_001 fixture's own docstring rationale
    verbatim below."""
    from market.data_provider import MarketDataError, OHLCV

    class _Provider:
        def __init__(self, good_symbols):
            self._good = good_symbols

        def fetch_ohlcv(self, symbol, *, period="5y", interval="1d"):
            if symbol not in self._good:
                raise MarketDataError(f"no data for {symbol}")
            return OHLCV(symbol=symbol, interval=interval, bars=_long_bars())

    def _apply(good_symbols):
        import market.data_provider as market_data_provider_module

        monkeypatch.setattr(market_data_provider_module, "get_market_data_provider", lambda: _Provider(good_symbols))

        import backtesting.cache as cache_module

        monkeypatch.setattr(cache_module, "CachedMarketDataProvider", lambda inner: inner)

    return _apply


def test_run_universe_partial_profit_experiment_pools_across_symbols(_fake_partial_universe_provider):
    _fake_partial_universe_provider({"AAA", "BBB"})

    from backtesting.exit_experiments import UniversePartialProfitExperimentResult, run_universe_partial_profit_experiment

    result = run_universe_partial_profit_experiment(["AAA", "BBB"], strategy=_LongOneShotStrategy(), initial_capital=1_000.0)

    assert isinstance(result, UniversePartialProfitExperimentResult)
    assert result.failed_symbols == {}
    assert isinstance(result.development_trades, list)
    assert isinstance(result.validation_trades, list)
    assert isinstance(result.out_of_sample_trades, list)


def test_run_universe_partial_profit_experiment_isolates_a_failing_symbol(_fake_partial_universe_provider):
    _fake_partial_universe_provider({"AAA"})

    from backtesting.exit_experiments import run_universe_partial_profit_experiment

    result = run_universe_partial_profit_experiment(["AAA", "BADSYMBOL"], strategy=_LongOneShotStrategy(), initial_capital=1_000.0)

    assert "BADSYMBOL" in result.failed_symbols
