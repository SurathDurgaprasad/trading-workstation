"""Unit tests for quant_research/iv_surface.py."""
from datetime import datetime, timedelta

from quant_research.iv_surface import (
    MIN_PLAUSIBLE_IV_PCT,
    OptionRollingBar,
    compute_atm_iv_level,
    compute_put_call_iv_skew,
    flag_volume_artifacts,
    is_plausible_iv,
)


def _bar(ts, iv=10.0, strike=24500.0, option_type="CE", oi=100000, volume=200000, spot=24500.0, close=100.0):
    return OptionRollingBar(timestamp=ts, strike=strike, option_type=option_type, iv=iv, oi=oi, volume=volume, spot=spot, close=close)


def _ts(i, base=datetime(2025, 9, 1, 9, 15)):
    return base + timedelta(hours=i)


class TestIvPlausibility:
    def test_below_floor_is_implausible(self):
        assert is_plausible_iv(MIN_PLAUSIBLE_IV_PCT - 0.01) is False

    def test_at_floor_is_plausible(self):
        assert is_plausible_iv(MIN_PLAUSIBLE_IV_PCT) is True

    def test_normal_iv_is_plausible(self):
        assert is_plausible_iv(12.5) is True

    def test_degenerate_near_zero_iv_from_real_phase1_finding_is_implausible(self):
        # Phase 1's own real observation: 0.0 and 0.4 near expiry.
        assert is_plausible_iv(0.0) is False
        assert is_plausible_iv(0.4) is False


class TestVolumeArtifactFlagging:
    def test_first_window_bars_are_never_flagged(self):
        bars = [_bar(_ts(i), volume=100) for i in range(5)]
        flags = flag_volume_artifacts(bars)
        assert flags == [False] * 5  # fewer than VOLUME_MEDIAN_WINDOW=10

    def test_normal_bar_after_window_is_not_flagged(self):
        bars = [_bar(_ts(i), volume=200000) for i in range(15)]
        flags = flag_volume_artifacts(bars)
        assert flags[10:] == [False] * 5

    def test_implausible_spike_is_flagged(self):
        bars = [_bar(_ts(i), volume=200000) for i in range(10)] + [_bar(_ts(10), volume=786_000_000)]
        flags = flag_volume_artifacts(bars)
        assert flags[-1] is True  # matches Phase 1's own real ~1000x-normal observation

    def test_flag_only_uses_prior_bars_never_future_ones(self):
        # A bar's own flag must not change depending on what comes AFTER it.
        bars_a = [_bar(_ts(i), volume=200000) for i in range(10)] + [_bar(_ts(10), volume=200000)]
        bars_b = bars_a + [_bar(_ts(11), volume=999_000_000)]  # append a future artifact bar
        flags_a = flag_volume_artifacts(bars_a)
        flags_b = flag_volume_artifacts(bars_b)
        assert flags_a[10] == flags_b[10]  # bar at index 10's own flag is unchanged by what's appended after it

    def test_zero_median_never_divides_or_crashes(self):
        bars = [_bar(_ts(i), volume=0) for i in range(11)]
        flags = flag_volume_artifacts(bars)
        assert flags[10] is False  # median=0 -> never flagged as "exceeds 20x zero"


class TestAtmIvLevel:
    def test_clean_series_passes_through_unchanged(self):
        bars = [_bar(_ts(i), iv=10.0 + i * 0.1, volume=200000) for i in range(15)]
        series = compute_atm_iv_level(bars)
        assert len(series) == 15
        assert series.iloc[0] == 10.0

    def test_degenerate_iv_is_dropped_not_interpolated(self):
        bars = [_bar(_ts(i), iv=10.0, volume=200000) for i in range(12)] + [_bar(_ts(12), iv=0.4, volume=200000)]
        series = compute_atm_iv_level(bars)
        assert len(series) == 12  # the degenerate bar is dropped entirely
        assert _ts(12) not in series.index

    def test_volume_artifact_is_dropped(self):
        bars = [_bar(_ts(i), iv=10.0, volume=200000) for i in range(10)] + [_bar(_ts(10), iv=10.0, volume=900_000_000)]
        series = compute_atm_iv_level(bars)
        assert _ts(10) not in series.index

    def test_empty_input_returns_empty_series_never_fabricated(self):
        series = compute_atm_iv_level([])
        assert len(series) == 0

    def test_all_bars_degenerate_returns_empty_not_a_crash(self):
        bars = [_bar(_ts(i), iv=0.0, volume=200000) for i in range(5)]
        series = compute_atm_iv_level(bars)
        assert len(series) == 0

    def test_series_is_sorted_by_timestamp(self):
        bars = [_bar(_ts(i), iv=10.0, volume=200000) for i in reversed(range(15))]
        series = compute_atm_iv_level(bars)
        assert list(series.index) == sorted(series.index)

    def test_units_are_percent_not_rescaled(self):
        bars = [_bar(_ts(i), iv=25.5, volume=200000) for i in range(11)]
        series = compute_atm_iv_level(bars)
        assert series.iloc[-1] == 25.5  # not divided by 100 or otherwise rescaled


class TestPutCallIvSkew:
    def test_matching_timestamps_produce_skew(self):
        calls = [_bar(_ts(i), iv=9.3, option_type="CE", volume=200000) for i in range(12)]
        puts = [_bar(_ts(i), iv=11.6, option_type="PE", volume=200000) for i in range(12)]
        series = compute_put_call_iv_skew(calls, puts)
        assert len(series) == 12
        assert abs(series.iloc[0] - 2.3) < 1e-9

    def test_timestamp_present_only_in_one_leg_is_excluded(self):
        calls = [_bar(_ts(i), iv=9.3, option_type="CE", volume=200000) for i in range(12)]
        puts = [_bar(_ts(i), iv=11.6, option_type="PE", volume=200000) for i in range(11)]  # missing last timestamp
        series = compute_put_call_iv_skew(calls, puts)
        assert len(series) == 11
        assert _ts(11) not in series.index

    def test_degenerate_leg_excludes_the_whole_pair_not_just_that_leg(self):
        calls = [_bar(_ts(i), iv=9.3, option_type="CE", volume=200000) for i in range(12)]
        puts = [_bar(_ts(i), iv=11.6, option_type="PE", volume=200000) for i in range(11)] + [_bar(_ts(11), iv=0.4, option_type="PE", volume=200000)]
        series = compute_put_call_iv_skew(calls, puts)
        assert _ts(11) not in series.index  # the call leg at ts(11) is fine, but the put leg is degenerate -- whole pair dropped

    def test_no_common_timestamps_returns_empty(self):
        calls = [_bar(_ts(i), option_type="CE", volume=200000) for i in range(5)]
        puts = [_bar(_ts(i + 100), option_type="PE", volume=200000) for i in range(5)]
        series = compute_put_call_iv_skew(calls, puts)
        assert len(series) == 0

    def test_empty_inputs_return_empty_not_fabricated(self):
        assert len(compute_put_call_iv_skew([], [])) == 0

    def test_real_observed_skew_direction_matches_phase1_finding(self):
        # Phase 1's own real observation: puts trade at materially higher IV than calls
        # at the same strike (a real, economically expected pattern, not an artifact).
        calls = [_bar(_ts(i), iv=9.36, option_type="CE", volume=200000) for i in range(11)]
        puts = [_bar(_ts(i), iv=11.75, option_type="PE", volume=200000) for i in range(11)]
        series = compute_put_call_iv_skew(calls, puts)
        assert (series > 0).all()  # put IV consistently exceeds call IV in this fixture
