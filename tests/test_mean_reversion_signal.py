"""H_MEANREV_001: permanent causality/leakage tests for the mean-
reversion signal study, mirroring the style of test_volume_signal.py and
test_momentum_acceleration.py.
"""
import pandas as pd
import pytest

from market.data_provider import OHLCV
from market.indicators import compute_indicator_series
from quant_research.mean_reversion_signal import (
    CANDIDATES,
    REGIME_GATED_CANDIDATES,
    MeanReversionSignalStrategy,
    add_mean_reversion_columns,
    decide_completion_exit,
)
from backtesting.execution import OpenPosition
from backtesting.trade import ExitReason
from strategy.signal import ReasonCode, Side, Signal


def _ohlcv(n, seed_close=100.0, dip_at=None):
    """A mostly-flat/uptrending series with an optional sharp dip
    starting at `dip_at` (n bars of a real, multi-bar decline) so a real
    negative zscore_close_20 is reachable, not just theoretically."""
    bars = []
    close = seed_close
    for i in range(n):
        if dip_at is not None and dip_at <= i < dip_at + 8:
            close -= 3.0
        else:
            close += 0.15
        bars.append({"Open": close - 0.2, "High": close + 1.0, "Low": close - 1.0, "Close": close, "Volume": 1_000_000.0})
    frame = pd.DataFrame(bars, index=pd.date_range("2024-01-01", periods=n, freq="D"))
    return OHLCV.from_dataframe(symbol="TEST", interval="1d", frame=frame)


def _series(n=260, dip_at=None):
    return add_mean_reversion_columns(compute_indicator_series(_ohlcv(n, dip_at=dip_at)))


# --- column computation -------------------------------------------------------


def test_add_mean_reversion_columns_is_purely_additive():
    base = compute_indicator_series(_ohlcv(100))
    augmented = add_mean_reversion_columns(base)

    for column in base.columns:
        pd.testing.assert_series_equal(base[column], augmented[column])
    assert "zscore_close_20" in augmented.columns
    assert "sma_200" in augmented.columns


def test_a_real_dip_produces_a_negative_zscore():
    series = _series(n=100, dip_at=60)
    # A few bars into the dip, the close should read meaningfully below
    # its own trailing 20-bar mean.
    assert series["zscore_close_20"].iloc[67] < -1.0


# --- candidate directional logic -----------------------------------------------


@pytest.mark.parametrize(
    "name,zscore,close,sma_200,expected",
    [
        ("A_oversold_2std", -2.5, 100.0, 90.0, True),
        ("A_oversold_2std", -1.0, 100.0, 90.0, False),
        ("A_oversold_2std", -2.0, 100.0, 90.0, False),  # boundary is strict <
        ("B_oversold_1_5std", -1.6, 100.0, 90.0, True),
        ("B_oversold_1_5std", -1.0, 100.0, 90.0, False),
        ("B_oversold_1_5std", -1.5, 100.0, 90.0, False),  # boundary is strict <
        ("C_oversold_within_uptrend", -2.5, 100.0, 90.0, True),  # close > sma_200: uptrend
        ("C_oversold_within_uptrend", -2.5, 100.0, 110.0, False),  # close < sma_200: downtrend, excluded
        ("C_oversold_within_uptrend", -1.0, 100.0, 90.0, False),  # not oversold enough
    ],
)
def test_candidate_direction_matches_frozen_definition(name, zscore, close, sma_200, expected):
    row = pd.Series({"zscore_close_20": zscore, "close": close, "sma_200": sma_200})
    assert CANDIDATES[name](row) is expected


@pytest.mark.parametrize("candidate_name", list(CANDIDATES))
def test_candidate_fails_closed_on_missing_history(candidate_name):
    row = pd.Series({"zscore_close_20": float("nan"), "close": 100.0, "sma_200": float("nan")})
    assert CANDIDATES[candidate_name](row) is False


# --- MeanReversionSignalStrategy -----------------------------------------------


def test_strategy_uses_the_dedicated_reason_code():
    series = _series(n=100, dip_at=60)
    strategy = MeanReversionSignalStrategy("B_oversold_1_5std")  # the least strict candidate, most likely to fire

    fired = [strategy.generate_signal(series, i, "TEST") for i in range(len(series))]
    real_signals = [s for s in fired if s is not None]

    assert real_signals, "expected at least one signal from a real multi-bar dip against candidate B"
    assert all(s.reason_codes == [ReasonCode.MEAN_REVERSION_OVERSOLD] for s in real_signals)


def test_strategy_never_fires_without_valid_atr():
    series = _series(n=100, dip_at=60)
    mutated = series.copy()
    mutated["atr_14"] = 0.0  # degenerate ATR everywhere
    strategy = MeanReversionSignalStrategy("B_oversold_1_5std")

    for i in range(len(mutated)):
        assert strategy.generate_signal(mutated, i, "TEST") is None


def test_strategy_ignores_future_bars():
    series = _series(n=260, dip_at=100)
    target_index = 200
    strategy = MeanReversionSignalStrategy("A_oversold_2std")

    signal_before = strategy.generate_signal(series, target_index, "TEST")

    mutated = series.copy()
    future_rows = mutated.index[target_index + 1 :]
    mutated.loc[future_rows, "zscore_close_20"] = -999.0
    mutated.loc[future_rows, "close"] = 1.0

    signal_after = strategy.generate_signal(mutated, target_index, "TEST")

    if signal_before is None:
        assert signal_after is None
    else:
        assert signal_after is not None
        assert signal_before.model_dump() == signal_after.model_dump()


# --- run_universe_mean_reversion_experiment ------------------------------------


@pytest.fixture
def _fake_mean_reversion_universe_provider(monkeypatch):
    from market.data_provider import MarketDataError

    class _Provider:
        def __init__(self, good_symbols):
            self._good = good_symbols

        def fetch_ohlcv(self, symbol, *, period="5y", interval="1d"):
            if symbol not in self._good:
                raise MarketDataError(f"no data for {symbol}")
            return _ohlcv(260, dip_at=100)

    def _apply(good_symbols):
        import market.data_provider as market_data_provider_module

        monkeypatch.setattr(market_data_provider_module, "get_market_data_provider", lambda: _Provider(good_symbols))

        # Bypass the real on-disk cache entirely -- "AAA"/"BBB"/"BADSYMBOL"
        # are not real cached symbols, so a cache MISS would otherwise
        # WRITE a real file under data/market/ as a side effect (same
        # concern/fix established for every other universe-level
        # experiment test in this project).
        import backtesting.cache as cache_module

        monkeypatch.setattr(cache_module, "CachedMarketDataProvider", lambda inner: inner)

    return _apply


def test_run_universe_mean_reversion_experiment_pools_across_symbols_and_candidates(_fake_mean_reversion_universe_provider):
    _fake_mean_reversion_universe_provider({"AAA", "BBB"})

    from quant_research.mean_reversion_signal import (
        UniverseMeanReversionExperimentResult,
        run_universe_mean_reversion_experiment,
    )

    result = run_universe_mean_reversion_experiment(["AAA", "BBB"], initial_capital=100_000.0)

    assert isinstance(result, UniverseMeanReversionExperimentResult)
    assert result.failed_symbols == {}
    assert set(result.development_trades) == set(CANDIDATES)
    assert set(result.validation_trades) == set(CANDIDATES)
    assert set(result.out_of_sample_trades) == set(CANDIDATES)
    for candidate_name in CANDIDATES:
        assert isinstance(result.development_trades[candidate_name], list)
        assert isinstance(result.validation_trades[candidate_name], list)
        assert isinstance(result.out_of_sample_trades[candidate_name], list)


def test_run_universe_mean_reversion_experiment_isolates_a_failing_symbol(_fake_mean_reversion_universe_provider):
    _fake_mean_reversion_universe_provider({"AAA"})

    from quant_research.mean_reversion_signal import run_universe_mean_reversion_experiment

    result = run_universe_mean_reversion_experiment(["AAA", "BADSYMBOL"], initial_capital=100_000.0)

    assert "BADSYMBOL" in result.failed_symbols
    assert "AAA" not in result.failed_symbols


# --- H_MEANREV_004: regime-gated candidates -----------------------------------


@pytest.mark.parametrize(
    "name,zscore,regime,expected",
    [
        ("A_oversold_2std_trending_up", -2.5, "TRENDING_UP", True),
        ("A_oversold_2std_trending_up", -2.5, "TRENDING_DOWN", False),  # oversold but wrong regime
        ("A_oversold_2std_trending_up", -2.5, "SIDEWAYS", False),
        ("A_oversold_2std_trending_up", -1.0, "TRENDING_UP", False),  # right regime, not oversold enough
        ("A_oversold_2std_trending_up", -2.0, "TRENDING_UP", False),  # boundary is strict <
        ("B_oversold_1_5std_trending_up", -1.6, "TRENDING_UP", True),
        ("B_oversold_1_5std_trending_up", -1.6, "TRENDING_DOWN", False),
        ("B_oversold_1_5std_trending_up", -1.5, "TRENDING_UP", False),  # boundary is strict <
    ],
)
def test_regime_gated_candidate_requires_both_conditions(name, zscore, regime, expected):
    row = pd.Series({"zscore_close_20": zscore, "market_trend_regime": regime})
    assert REGIME_GATED_CANDIDATES[name](row) is expected


@pytest.mark.parametrize("candidate_name", list(REGIME_GATED_CANDIDATES))
def test_regime_gated_candidate_fails_closed_on_missing_regime_column(candidate_name):
    """A row with no market_trend_regime attached at all (e.g. before
    the external overlay runs) must never fire -- NaN/missing must
    never be silently treated as a matching regime."""
    row = pd.Series({"zscore_close_20": -3.0})
    assert REGIME_GATED_CANDIDATES[candidate_name](row) is False


@pytest.mark.parametrize("candidate_name", list(REGIME_GATED_CANDIDATES))
def test_regime_gated_candidate_fails_closed_on_missing_zscore(candidate_name):
    row = pd.Series({"zscore_close_20": float("nan"), "market_trend_regime": "TRENDING_UP"})
    assert REGIME_GATED_CANDIDATES[candidate_name](row) is False


def test_strategy_accepts_regime_gated_candidates_dict():
    series = _series(n=100, dip_at=60)
    series["market_trend_regime"] = "TRENDING_UP"
    strategy = MeanReversionSignalStrategy("B_oversold_1_5std_trending_up", candidates=REGIME_GATED_CANDIDATES)

    fired = [strategy.generate_signal(series, i, "TEST") for i in range(len(series))]
    real_signals = [s for s in fired if s is not None]

    assert real_signals, "expected at least one signal from a real dip while TRENDING_UP holds throughout"
    assert all(s.reason_codes == [ReasonCode.MEAN_REVERSION_OVERSOLD] for s in real_signals)


def test_strategy_regime_gated_never_fires_when_regime_never_matches():
    series = _series(n=100, dip_at=60)
    series["market_trend_regime"] = "TRENDING_DOWN"  # never TRENDING_UP, despite a real dip
    strategy = MeanReversionSignalStrategy("B_oversold_1_5std_trending_up", candidates=REGIME_GATED_CANDIDATES)

    fired = [strategy.generate_signal(series, i, "TEST") for i in range(len(series))]
    assert all(s is None for s in fired)


def test_default_candidates_dict_is_still_the_original_when_unspecified():
    """Regression guard: not passing `candidates` at all must still use
    the original, frozen H_MEANREV_001 CANDIDATES dict unchanged."""
    strategy = MeanReversionSignalStrategy("A_oversold_2std")
    assert strategy._predicate is CANDIDATES["A_oversold_2std"]


# --- run_universe_regime_gated_mean_reversion_experiment -----------------------


def test_run_universe_regime_gated_mean_reversion_experiment_pools_across_symbols_and_candidates(_fake_mean_reversion_universe_provider):
    _fake_mean_reversion_universe_provider({"AAA", "BBB", "^NSEI"})

    from quant_research.mean_reversion_signal import (
        UniverseRegimeGatedMeanReversionExperimentResult,
        run_universe_regime_gated_mean_reversion_experiment,
    )

    result = run_universe_regime_gated_mean_reversion_experiment(["AAA", "BBB"], initial_capital=100_000.0)

    assert isinstance(result, UniverseRegimeGatedMeanReversionExperimentResult)
    assert result.failed_symbols == {}
    assert set(result.development_trades) == set(REGIME_GATED_CANDIDATES)
    assert set(result.validation_trades) == set(REGIME_GATED_CANDIDATES)
    assert set(result.out_of_sample_trades) == set(REGIME_GATED_CANDIDATES)
    for candidate_name in REGIME_GATED_CANDIDATES:
        assert isinstance(result.development_trades[candidate_name], list)


def test_run_universe_regime_gated_mean_reversion_experiment_isolates_a_failing_symbol(_fake_mean_reversion_universe_provider):
    _fake_mean_reversion_universe_provider({"AAA", "^NSEI"})

    from quant_research.mean_reversion_signal import run_universe_regime_gated_mean_reversion_experiment

    result = run_universe_regime_gated_mean_reversion_experiment(["AAA", "BADSYMBOL"], initial_capital=100_000.0)

    assert "BADSYMBOL" in result.failed_symbols
    assert "AAA" not in result.failed_symbols


def test_run_universe_regime_gated_mean_reversion_experiment_raises_if_benchmark_unavailable(_fake_mean_reversion_universe_provider):
    """The benchmark's own regime series is fetched ONCE, shared across
    every symbol -- if it cannot be built at all, this must fail loudly
    (no candidate can ever be gated correctly) rather than silently
    running with an unset/fabricated regime."""
    _fake_mean_reversion_universe_provider({"AAA"})  # ^NSEI deliberately NOT in the good set

    from quant_research.mean_reversion_signal import run_universe_regime_gated_mean_reversion_experiment

    with pytest.raises(ValueError, match="benchmark"):
        run_universe_regime_gated_mean_reversion_experiment(["AAA"], initial_capital=100_000.0)


# --- H_EXIT_005: mean-reversion-completion exit ---------------------------------


def _open_position(stop_price=1.0, target_price=100_000.0):
    """A deliberately wide stop/target (matching H_EXIT_005's own
    frozen design) -- structurally valid for RiskEngine, but not meant
    to be the thing that actually decides an exit in these tests."""
    signal = Signal(
        symbol="TEST", generated_at=pd.Timestamp("2024-01-01"), side=Side.LONG,
        reference_price=100.0, stop_price=stop_price, target_price=target_price,
        risk_reward=2.0, strategy_name="test", reason_codes=[ReasonCode.MEAN_REVERSION_OVERSOLD],
    )
    return OpenPosition(signal=signal, entry_time=pd.Timestamp("2024-01-02"), entry_price=100.0, quantity=10, stop_price=stop_price, target_price=target_price)


def _bar(close, zscore=None, high=None, low=None):
    high = high if high is not None else close + 1.0
    low = low if low is not None else close - 1.0
    row = {"close": close, "high": high, "low": low}
    if zscore is not None:
        row["zscore_close_20"] = zscore
    return pd.Series(row)


def test_decide_completion_exit_fires_on_reversion_complete():
    position = _open_position()
    bar = _bar(close=100.0, zscore=0.0)
    outcome = decide_completion_exit(position, bar, bars_held=3, max_holding_bars=20)
    assert outcome == (100.0, ExitReason.MEAN_REVERSION_COMPLETE)


def test_decide_completion_exit_fires_on_zscore_above_zero_too():
    position = _open_position()
    bar = _bar(close=105.0, zscore=0.42)
    outcome = decide_completion_exit(position, bar, bars_held=3, max_holding_bars=20)
    assert outcome == (105.0, ExitReason.MEAN_REVERSION_COMPLETE)


def test_decide_completion_exit_does_not_fire_while_still_oversold():
    position = _open_position()
    bar = _bar(close=95.0, zscore=-1.2)
    outcome = decide_completion_exit(position, bar, bars_held=3, max_holding_bars=20)
    assert outcome is None


def test_decide_completion_exit_never_fires_on_missing_zscore():
    """A row with no zscore_close_20 at all (e.g. still in warm-up) must
    never satisfy the completion condition -- NaN/missing must never be
    silently treated as 'reverted.'"""
    position = _open_position()
    bar = _bar(close=95.0, zscore=None)
    outcome = decide_completion_exit(position, bar, bars_held=3, max_holding_bars=20)
    assert outcome is None


def test_decide_completion_exit_falls_back_to_time_cap():
    position = _open_position()
    bar = _bar(close=95.0, zscore=-1.2)  # still oversold, no completion
    outcome = decide_completion_exit(position, bar, bars_held=20, max_holding_bars=20)
    assert outcome == (95.0, ExitReason.EXPIRED)


def test_decide_completion_exit_does_not_expire_one_bar_early():
    position = _open_position()
    bar = _bar(close=95.0, zscore=-1.2)
    outcome = decide_completion_exit(position, bar, bars_held=19, max_holding_bars=20)
    assert outcome is None


def test_decide_completion_exit_price_stop_still_takes_priority():
    """The deliberately wide stop is practically unreachable in real
    data, but if the caller passes a genuinely reachable one, check_exit
    must still take priority over the new completion condition -- never
    silently absorbed into MEAN_REVERSION_COMPLETE."""
    position = _open_position(stop_price=94.0)
    bar = _bar(close=95.0, zscore=0.5, low=93.0)  # low breaches the stop AND zscore says "reverted"
    outcome = decide_completion_exit(position, bar, bars_held=3, max_holding_bars=20)
    assert outcome == (94.0, ExitReason.STOP)


def test_decide_completion_exit_price_target_still_takes_priority():
    position = _open_position(target_price=106.0)
    bar = _bar(close=95.0, zscore=0.5, high=107.0)  # high breaches the target AND zscore says "reverted"
    outcome = decide_completion_exit(position, bar, bars_held=3, max_holding_bars=20)
    assert outcome == (106.0, ExitReason.TARGET)


def test_run_universe_mean_reversion_completion_exit_experiment_pools_across_symbols_and_candidates(_fake_mean_reversion_universe_provider):
    _fake_mean_reversion_universe_provider({"AAA", "BBB", "^NSEI"})

    from quant_research.mean_reversion_signal import (
        UniverseMeanReversionCompletionExitExperimentResult,
        run_universe_mean_reversion_completion_exit_experiment,
    )

    result = run_universe_mean_reversion_completion_exit_experiment(["AAA", "BBB"], initial_capital=100_000.0)

    assert isinstance(result, UniverseMeanReversionCompletionExitExperimentResult)
    assert result.failed_symbols == {}
    assert set(result.development_trades) == set(REGIME_GATED_CANDIDATES)
    assert set(result.validation_trades) == set(REGIME_GATED_CANDIDATES)
    assert set(result.out_of_sample_trades) == set(REGIME_GATED_CANDIDATES)


def test_run_universe_mean_reversion_completion_exit_experiment_isolates_a_failing_symbol(_fake_mean_reversion_universe_provider):
    _fake_mean_reversion_universe_provider({"AAA", "^NSEI"})

    from quant_research.mean_reversion_signal import run_universe_mean_reversion_completion_exit_experiment

    result = run_universe_mean_reversion_completion_exit_experiment(["AAA", "BADSYMBOL"], initial_capital=100_000.0)

    assert "BADSYMBOL" in result.failed_symbols
    assert "AAA" not in result.failed_symbols


def test_run_universe_mean_reversion_completion_exit_experiment_exit_reasons_are_never_stop_or_target(_fake_mean_reversion_universe_provider):
    """With the deliberately wide stop/target this hypothesis freezes,
    no real trade should ever exit via STOP or TARGET in practice --
    only MEAN_REVERSION_COMPLETE or EXPIRED (or END_OF_DATA at the very
    end of a slice). A STOP/TARGET exit appearing here would mean the
    wide-multiplier override isn't actually being applied."""
    _fake_mean_reversion_universe_provider({"AAA", "^NSEI"})

    from quant_research.mean_reversion_signal import run_universe_mean_reversion_completion_exit_experiment

    result = run_universe_mean_reversion_completion_exit_experiment(["AAA"], initial_capital=100_000.0)

    all_trades = [
        t
        for bucket in (result.development_trades, result.validation_trades, result.out_of_sample_trades)
        for trades in bucket.values()
        for t in trades
    ]
    reasons = {t.exit_reason for t in all_trades}
    assert reasons <= {ExitReason.MEAN_REVERSION_COMPLETE, ExitReason.EXPIRED, ExitReason.END_OF_DATA}


# --- H_MEANREV_009: relative-weakness-gated candidate + executable design -------


@pytest.mark.parametrize(
    "zscore,relstrength,expected",
    [
        (-2.5, -0.10, True),  # oversold AND relatively weak
        (-2.5, -0.01, False),  # oversold but NOT relatively weak (above the frozen median)
        (-1.0, -0.10, False),  # relatively weak but not oversold enough
        (-2.0, -0.10, False),  # boundary is strict <
    ],
)
def test_relative_weak_candidate_requires_both_conditions(zscore, relstrength, expected):
    from quant_research.mean_reversion_signal import RELATIVE_WEAKNESS_GATED_CANDIDATES

    row = pd.Series({"zscore_close_20": zscore, "relative_strength_20": relstrength})
    assert RELATIVE_WEAKNESS_GATED_CANDIDATES["A_oversold_2std_relative_weak"](row) is expected


def test_relative_weak_candidate_fails_closed_on_missing_relative_strength_column():
    from quant_research.mean_reversion_signal import RELATIVE_WEAKNESS_GATED_CANDIDATES

    row = pd.Series({"zscore_close_20": -3.0})
    assert RELATIVE_WEAKNESS_GATED_CANDIDATES["A_oversold_2std_relative_weak"](row) is False


def test_relative_weak_candidate_fails_closed_on_missing_zscore():
    from quant_research.mean_reversion_signal import RELATIVE_WEAKNESS_GATED_CANDIDATES

    row = pd.Series({"zscore_close_20": float("nan"), "relative_strength_20": -0.10})
    assert RELATIVE_WEAKNESS_GATED_CANDIDATES["A_oversold_2std_relative_weak"](row) is False


def test_run_universe_relative_weakness_time_exit_experiment_pools_across_symbols_and_candidates(_fake_mean_reversion_universe_provider):
    _fake_mean_reversion_universe_provider({"AAA", "BBB", "^NSEI"})

    from quant_research.mean_reversion_signal import (
        RELATIVE_WEAKNESS_GATED_CANDIDATES,
        UniverseRelativeWeaknessTimeExitExperimentResult,
        run_universe_relative_weakness_time_exit_experiment,
    )

    result = run_universe_relative_weakness_time_exit_experiment(["AAA", "BBB"], initial_capital=100_000.0)

    assert isinstance(result, UniverseRelativeWeaknessTimeExitExperimentResult)
    assert result.failed_symbols == {}
    assert set(result.development_trades) == set(RELATIVE_WEAKNESS_GATED_CANDIDATES)
    assert set(result.validation_trades) == set(RELATIVE_WEAKNESS_GATED_CANDIDATES)
    assert set(result.out_of_sample_trades) == set(RELATIVE_WEAKNESS_GATED_CANDIDATES)
    for candidate_name in RELATIVE_WEAKNESS_GATED_CANDIDATES:
        assert isinstance(result.development_trades[candidate_name], list)


def test_run_universe_relative_weakness_time_exit_experiment_isolates_a_failing_symbol(_fake_mean_reversion_universe_provider):
    _fake_mean_reversion_universe_provider({"AAA", "^NSEI"})

    from quant_research.mean_reversion_signal import run_universe_relative_weakness_time_exit_experiment

    result = run_universe_relative_weakness_time_exit_experiment(["AAA", "BADSYMBOL"], initial_capital=100_000.0)

    assert "BADSYMBOL" in result.failed_symbols
    assert "AAA" not in result.failed_symbols


def test_run_universe_relative_weakness_time_exit_experiment_exit_reasons_are_never_stop_or_target(_fake_mean_reversion_universe_provider):
    """With the deliberately wide stop/target this hypothesis reuses
    from H_EXIT_005, no real trade should ever exit via STOP or TARGET
    in practice -- only EXPIRED (the time cap) or END_OF_DATA."""
    _fake_mean_reversion_universe_provider({"AAA", "^NSEI"})

    from quant_research.mean_reversion_signal import run_universe_relative_weakness_time_exit_experiment

    result = run_universe_relative_weakness_time_exit_experiment(["AAA"], initial_capital=100_000.0)

    all_trades = [
        t
        for bucket in (result.development_trades, result.validation_trades, result.out_of_sample_trades)
        for trades in bucket.values()
        for t in trades
    ]
    reasons = {t.exit_reason for t in all_trades}
    assert reasons <= {ExitReason.EXPIRED, ExitReason.END_OF_DATA}
