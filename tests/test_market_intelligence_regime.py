"""Phase 33 -- market regime & breadth. No real network: a fake
MarketDataProvider serves synthetic OHLCV series for the benchmark
context tests."""

from datetime import datetime, timedelta, timezone

import pytest

from market.data_provider import OHLCV, MarketDataError, OHLCVBar
from market_intelligence.models import CandidateScore, ExcludedCandidate, ScanReport
from market_intelligence.regime import (
    VolatilityRegime,
    build_market_regime_report,
    compute_benchmark_context,
    compute_breadth,
    compute_sector_strength,
)

_START = datetime(2023, 1, 2)


def _candidate(symbol: str, *, trend_score: float, composite_score: float = 0.0) -> CandidateScore:
    return CandidateScore(
        symbol=symbol, as_of=datetime(2024, 6, 1), last_close=100.0, avg_daily_value=1_000_000.0,
        volume_ratio=1.0, trend_score=trend_score, momentum_score=0.0, breakout_score=0.0,
        relative_strength_score=None, sector_strength_score=None, composite_score=composite_score,
        explanation=["fake"],
    )


def _scan_report(candidates: list[CandidateScore], *, benchmark_symbol: str | None = "^NSEI", excluded: list[ExcludedCandidate] | None = None) -> ScanReport:
    return ScanReport(
        scan_id="scan-1", as_of=datetime(2024, 6, 1, tzinfo=timezone.utc), universe_mode="watchlist",
        universe_size=len(candidates) + len(excluded or []), benchmark_symbol=benchmark_symbol,
        benchmark_unavailable_reason=None, config_version="cfg1", candidates=candidates, excluded=excluded or [],
    )


# --- breadth -----------------------------------------------------------------


def test_compute_breadth_counts_advancing_declining_flat():
    report = _scan_report([
        _candidate("A", trend_score=1.0), _candidate("B", trend_score=1.0),
        _candidate("C", trend_score=-1.0), _candidate("D", trend_score=0.0),
    ])
    breadth = compute_breadth(report)
    assert breadth.advancing == 2
    assert breadth.declining == 1
    assert breadth.flat == 1
    assert breadth.total_scored == 4
    assert breadth.advance_decline_ratio == pytest.approx(2.0)


def test_compute_breadth_ratio_is_none_when_nothing_declining():
    report = _scan_report([_candidate("A", trend_score=1.0)])
    breadth = compute_breadth(report)
    assert breadth.advance_decline_ratio is None


def test_compute_breadth_ignores_excluded_symbols():
    """Excluded symbols never got a trend_score computed -- counting them
    as flat would fabricate a trend reading for unobserved data."""
    report = _scan_report(
        [_candidate("A", trend_score=1.0)],
        excluded=[ExcludedCandidate(symbol="ZZZZ", as_of=None, reason="insufficient history")],
    )
    breadth = compute_breadth(report)
    assert breadth.total_scored == 1  # not 2


def test_breadth_advancing_pct():
    report = _scan_report([_candidate("A", trend_score=1.0), _candidate("B", trend_score=-1.0), _candidate("C", trend_score=-1.0)])
    breadth = compute_breadth(report)
    assert breadth.advancing_pct == pytest.approx(1 / 3)


def test_breadth_empty_universe_has_no_ratio_or_pct():
    report = _scan_report([])
    breadth = compute_breadth(report)
    assert breadth.total_scored == 0
    assert breadth.advance_decline_ratio is None
    assert breadth.advancing_pct is None


# --- sector strength ---------------------------------------------------------


def test_compute_sector_strength_groups_and_ranks():
    report = _scan_report([
        _candidate("A", trend_score=1.0, composite_score=2.0),
        _candidate("B", trend_score=1.0, composite_score=1.0),
        _candidate("C", trend_score=1.0, composite_score=0.5),
    ])
    sector_map = {"A": "IT", "B": "IT", "C": "BANKING"}

    result = compute_sector_strength(report, sector_map)

    assert [s.sector for s in result] == ["IT", "BANKING"]  # IT avg=1.5 > BANKING avg=0.5
    assert result[0].symbol_count == 2
    assert result[0].average_composite_score == pytest.approx(1.5)


def test_compute_sector_strength_returns_empty_without_a_map():
    report = _scan_report([_candidate("A", trend_score=1.0)])
    assert compute_sector_strength(report, None) == ()
    assert compute_sector_strength(report, {}) == ()


def test_compute_sector_strength_skips_symbols_missing_from_the_map():
    report = _scan_report([_candidate("A", trend_score=1.0, composite_score=1.0), _candidate("B", trend_score=1.0, composite_score=99.0)])
    result = compute_sector_strength(report, {"A": "IT"})  # B deliberately absent
    assert len(result) == 1
    assert result[0].sector == "IT"


# --- benchmark context ---------------------------------------------------------


def _uptrend_bars(n: int = 300, start: float = 100.0, step: float = 0.5, high_mult: float = 1.01, low_mult: float = 0.99) -> list[OHLCVBar]:
    bars = []
    for i in range(n):
        close = start + step * i
        bars.append(OHLCVBar(timestamp=_START + timedelta(days=i), open=close, high=close * high_mult, low=close * low_mult, close=close, volume=1_000_000.0))
    return bars


class _FakeProvider:
    def __init__(self, bars: list[OHLCVBar]):
        self._bars = bars

    def fetch_ohlcv(self, symbol, *, period="2y", interval="1d"):
        return OHLCV(symbol=symbol, interval=interval, bars=self._bars)


class _FailingProvider:
    def fetch_ohlcv(self, symbol, *, period="2y", interval="1d"):
        raise MarketDataError("simulated outage")


def test_compute_benchmark_context_with_no_symbol_returns_unknown():
    context = compute_benchmark_context(None, provider=_FakeProvider(_uptrend_bars()))
    assert context.symbol is None
    assert context.trend_regime == "UNKNOWN"
    assert context.volatility_regime == "UNKNOWN"


def test_compute_benchmark_context_detects_uptrend_and_normal_volatility():
    # Constant daily range (1% high/low band every day) -> stable ATR -> NORMAL.
    provider = _FakeProvider(_uptrend_bars())
    context = compute_benchmark_context("^NSEI", provider=provider, now=_START + timedelta(days=299))

    assert context.symbol == "^NSEI"
    assert context.trend_regime == "UPTREND"
    assert context.volatility_regime == "NORMAL_VOLATILITY"
    assert context.last_close is not None
    assert context.atr_pct_vs_trailing_average == pytest.approx(1.0, abs=0.1)


def test_compute_benchmark_context_detects_high_volatility_spike():
    bars = _uptrend_bars(n=300)
    # Widen the daily range sharply for the last 5 bars only -> ATR spikes relative to its own trailing average.
    spiked = list(bars)
    for i in range(len(spiked) - 5, len(spiked)):
        b = spiked[i]
        spiked[i] = OHLCVBar(timestamp=b.timestamp, open=b.open, high=b.close * 1.15, low=b.close * 0.85, close=b.close, volume=b.volume)

    context = compute_benchmark_context("^NSEI", provider=_FakeProvider(spiked))
    assert context.volatility_regime == "HIGH_VOLATILITY"
    assert context.atr_pct_vs_trailing_average > 1.5


def test_compute_benchmark_context_handles_a_provider_failure_gracefully():
    context = compute_benchmark_context("^NSEI", provider=_FailingProvider())
    assert context.trend_regime == "UNKNOWN"
    assert context.volatility_regime == "UNKNOWN"
    assert context.last_close is None


def test_compute_benchmark_context_unknown_volatility_with_insufficient_history():
    context = compute_benchmark_context("^NSEI", provider=_FakeProvider(_uptrend_bars(n=250)), volatility_lookback=60)
    # 250 bars is enough for the 200-bar trend SMA but let's use a lookback that clearly won't fit for a short series.
    context2 = compute_benchmark_context("^NSEI", provider=_FakeProvider(_uptrend_bars(n=250)), volatility_lookback=245)
    assert context2.volatility_regime == "UNKNOWN"
    assert context2.atr_pct_vs_trailing_average is None


# --- full report ---------------------------------------------------------------


def test_build_market_regime_report_combines_everything():
    scan_report = _scan_report([
        _candidate("A", trend_score=1.0, composite_score=1.0),
        _candidate("B", trend_score=-1.0, composite_score=-0.5),
    ], benchmark_symbol="^NSEI")

    report = build_market_regime_report(scan_report, provider=_FakeProvider(_uptrend_bars()), sector_map={"A": "IT", "B": "BANKING"})

    assert report.scan_id == "scan-1"
    assert report.breadth.advancing == 1
    assert report.breadth.declining == 1
    assert report.benchmark.symbol == "^NSEI"
    assert report.benchmark.trend_regime == "UPTREND"
    assert len(report.sector_strength) == 2


def test_build_market_regime_report_without_a_sector_map_has_empty_sector_strength():
    scan_report = _scan_report([_candidate("A", trend_score=1.0)], benchmark_symbol=None)
    report = build_market_regime_report(scan_report, provider=_FakeProvider(_uptrend_bars()))
    assert report.sector_strength == ()
    assert report.benchmark.symbol is None


def test_build_market_regime_report_benchmark_override_wins_over_the_scans_own():
    """Regression: an earlier version always read scan_report.benchmark_symbol
    directly, silently ignoring any caller-supplied override -- found via a
    failing `regime --benchmark ...` CLI test."""
    scan_report = _scan_report([_candidate("A", trend_score=1.0)], benchmark_symbol="^NSEI")
    report = build_market_regime_report(scan_report, provider=_FakeProvider(_uptrend_bars()), benchmark_symbol="^GSPC")
    assert report.benchmark.symbol == "^GSPC"


def test_build_market_regime_report_benchmark_explicitly_disabled():
    scan_report = _scan_report([_candidate("A", trend_score=1.0)], benchmark_symbol="^NSEI")
    report = build_market_regime_report(scan_report, provider=_FakeProvider(_uptrend_bars()), benchmark_symbol=None)
    assert report.benchmark.symbol is None


def test_build_market_regime_report_default_inherits_the_scans_own_benchmark():
    scan_report = _scan_report([_candidate("A", trend_score=1.0)], benchmark_symbol="^NSEI")
    report = build_market_regime_report(scan_report, provider=_FakeProvider(_uptrend_bars()))  # no benchmark_symbol passed
    assert report.benchmark.symbol == "^NSEI"
