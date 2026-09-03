"""Phase 33 -- market regime & breadth intelligence.

Every number here is either a pure aggregation over an EXISTING
market_intelligence.models.ScanReport (breadth, sector strength) or a
direct reuse of an already-tested indicator/classifier (benchmark trend
via learning.regime.classify_regime_at, benchmark volatility via
market.indicators.compute_indicator_series's own ATR14 column). No AI,
no opaque scoring -- matches the roadmap's own explicit rule for this
phase: "All calculations must be explainable. No opaque AI output
should silently control labels."

Breadth and sector strength cost NOTHING extra: they are aggregations
over data market_intelligence.scanner.run_scan already computed. Only
the benchmark's own volatility classification needs a fresh fetch
(the scanner computes trend/momentum/breakout per SYMBOL, never a
volatility series for the benchmark itself).
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

from learning.regime import MarketRegime, classify_regime_at
from market.data_provider import MarketDataError, MarketDataProvider
from market.indicators import compute_indicator_series
from market_intelligence.models import ScanReport


class VolatilityRegime(str, Enum):
    HIGH = "HIGH_VOLATILITY"
    LOW = "LOW_VOLATILITY"
    NORMAL = "NORMAL_VOLATILITY"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class MarketBreadth:
    """A pure aggregation over ScanReport.candidates' own trend_score
    (already +1/0/-1 from market_intelligence.scanner) -- symbols in
    `excluded` are NOT counted (their trend was never computed, since
    they failed an earlier gate; counting them as "flat" would fabricate
    a trend reading for data that was never observed)."""

    advancing: int
    declining: int
    flat: int
    total_scored: int
    advance_decline_ratio: float | None
    """advancing / declining; None when declining == 0 (undefined, not infinity)."""

    @property
    def advancing_pct(self) -> float | None:
        return (self.advancing / self.total_scored) if self.total_scored > 0 else None


@dataclass(frozen=True)
class BenchmarkContext:
    symbol: str | None
    trend_regime: str
    """learning.regime.MarketRegime.value -- UPTREND/DOWNTREND/UNKNOWN."""
    volatility_regime: str
    """VolatilityRegime.value."""
    last_close: float | None
    atr_pct_of_price: float | None
    atr_pct_vs_trailing_average: float | None
    """current ATR14%-of-price divided by its own trailing average --
    the explainable ratio `volatility_regime` is thresholded on. >1
    means more volatile than recent history, <1 less."""


@dataclass(frozen=True)
class SectorStrength:
    sector: str
    symbol_count: int
    average_composite_score: float


@dataclass(frozen=True)
class MarketRegimeReport:
    as_of: datetime
    scan_id: str
    breadth: MarketBreadth
    benchmark: BenchmarkContext
    sector_strength: tuple[SectorStrength, ...]
    """Sorted strongest-first by average_composite_score. Empty when no
    sector_map was supplied -- never fabricated."""


def compute_breadth(scan_report: ScanReport) -> MarketBreadth:
    advancing = sum(1 for c in scan_report.candidates if c.trend_score > 0)
    declining = sum(1 for c in scan_report.candidates if c.trend_score < 0)
    flat = sum(1 for c in scan_report.candidates if c.trend_score == 0)
    total = len(scan_report.candidates)
    ratio = (advancing / declining) if declining > 0 else None
    return MarketBreadth(advancing=advancing, declining=declining, flat=flat, total_scored=total, advance_decline_ratio=ratio)


def compute_benchmark_context(
    benchmark_symbol: str | None,
    *,
    provider: MarketDataProvider,
    now: datetime | None = None,
    period: str = "2y",
    interval: str = "1d",
    volatility_lookback: int = 60,
    high_volatility_multiplier: float = 1.5,
    low_volatility_multiplier: float = 0.67,
) -> BenchmarkContext:
    """`high_volatility_multiplier`/`low_volatility_multiplier` are
    explicit, named thresholds on current-ATR%-vs-its-own-trailing-
    average -- not tuned against historical performance (no such study
    exists yet), the same "equal weight / no fabricated threshold until
    proven otherwise" posture market_intelligence.config.ScannerConfig
    already documents for its own gates."""
    now = now or datetime.now(timezone.utc)
    unknown = VolatilityRegime.UNKNOWN.value

    if benchmark_symbol is None:
        return BenchmarkContext(symbol=None, trend_regime=MarketRegime.UNKNOWN.value, volatility_regime=unknown, last_close=None, atr_pct_of_price=None, atr_pct_vs_trailing_average=None)

    trend = classify_regime_at(benchmark_symbol, now, provider=provider, period=period, interval=interval)

    try:
        ohlcv = provider.fetch_ohlcv(benchmark_symbol, period=period, interval=interval)
        series = compute_indicator_series(ohlcv)
    except (MarketDataError, ValueError):
        return BenchmarkContext(symbol=benchmark_symbol, trend_regime=trend.value, volatility_regime=unknown, last_close=None, atr_pct_of_price=None, atr_pct_vs_trailing_average=None)

    last_close = float(series["close"].iloc[-1]) if len(series) else None

    valid = series.dropna(subset=["atr_14", "close"])
    if len(valid) < volatility_lookback + 1:
        return BenchmarkContext(symbol=benchmark_symbol, trend_regime=trend.value, volatility_regime=unknown, last_close=last_close, atr_pct_of_price=None, atr_pct_vs_trailing_average=None)

    atr_pct_series = valid["atr_14"] / valid["close"]
    current_atr_pct = float(atr_pct_series.iloc[-1])
    # Trailing average EXCLUDES the current bar from its own baseline --
    # otherwise a single volatile day partially averages itself away.
    trailing_avg = float(atr_pct_series.iloc[-(volatility_lookback + 1):-1].mean())

    if trailing_avg <= 0:
        return BenchmarkContext(symbol=benchmark_symbol, trend_regime=trend.value, volatility_regime=unknown, last_close=last_close, atr_pct_of_price=current_atr_pct, atr_pct_vs_trailing_average=None)

    ratio = current_atr_pct / trailing_avg
    if ratio >= high_volatility_multiplier:
        vol_regime = VolatilityRegime.HIGH
    elif ratio <= low_volatility_multiplier:
        vol_regime = VolatilityRegime.LOW
    else:
        vol_regime = VolatilityRegime.NORMAL

    return BenchmarkContext(
        symbol=benchmark_symbol, trend_regime=trend.value, volatility_regime=vol_regime.value,
        last_close=last_close, atr_pct_of_price=current_atr_pct, atr_pct_vs_trailing_average=ratio,
    )


def compute_sector_strength(scan_report: ScanReport, sector_map: Mapping[str, str] | None) -> tuple[SectorStrength, ...]:
    """`sector_map` (symbol -> sector name) is the SAME shape
    research.sector.build_sector_map already produces -- not a new
    taxonomy. Empty tuple, never fabricated groupings, when not supplied
    (matches market_intelligence.scanner.run_scan's own existing
    optional-sector_map posture)."""
    if not sector_map:
        return ()

    groups: dict[str, list[float]] = {}
    for candidate in scan_report.candidates:
        sector = sector_map.get(candidate.symbol)
        if sector is None:
            continue
        groups.setdefault(sector, []).append(candidate.composite_score)

    result = [
        SectorStrength(sector=sector, symbol_count=len(scores), average_composite_score=sum(scores) / len(scores))
        for sector, scores in groups.items()
    ]
    return tuple(sorted(result, key=lambda s: -s.average_composite_score))


USE_SCAN_REPORTS_OWN_BENCHMARK = object()
"""Sentinel distinguishing "caller didn't specify a benchmark override"
(use scan_report.benchmark_symbol) from an explicit `benchmark_symbol=None`
(disable benchmark classification entirely, regardless of what the scan
itself used) -- a real ambiguity bug found via a failing CLI test: an
earlier version of this function always read scan_report.benchmark_symbol
directly, silently ignoring any caller-supplied override."""


def build_market_regime_report(
    scan_report: ScanReport,
    *,
    provider: MarketDataProvider,
    benchmark_symbol: str | None = USE_SCAN_REPORTS_OWN_BENCHMARK,
    sector_map: Mapping[str, str] | None = None,
    period: str = "2y",
    interval: str = "1d",
    now: datetime | None = None,
) -> MarketRegimeReport:
    resolved_now = now or datetime.now(timezone.utc)
    breadth = compute_breadth(scan_report)
    resolved_benchmark = scan_report.benchmark_symbol if benchmark_symbol is USE_SCAN_REPORTS_OWN_BENCHMARK else benchmark_symbol
    benchmark = compute_benchmark_context(resolved_benchmark, provider=provider, now=resolved_now, period=period, interval=interval)
    sectors = compute_sector_strength(scan_report, sector_map)
    return MarketRegimeReport(as_of=resolved_now, scan_id=scan_report.scan_id, breadth=breadth, benchmark=benchmark, sector_strength=sectors)
