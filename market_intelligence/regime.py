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
from dataclasses import dataclass, field
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


NIFTY_SECTOR_INDICES: dict[str, str] = {
    "NIFTY_BANK": "^NSEBANK",
    "NIFTY_FINANCIAL_SERVICES": "NIFTY_FIN_SERVICE.NS",
    "NIFTY_IT": "^CNXIT",
    "NIFTY_AUTO": "^CNXAUTO",
    "NIFTY_PHARMA": "^CNXPHARMA",
    "NIFTY_FMCG": "^CNXFMCG",
    "NIFTY_METAL": "^CNXMETAL",
    "NIFTY_REALTY": "^CNXREALTY",
    "NIFTY_ENERGY": "^CNXENERGY",
}
"""INDIAN MARKET TRADING BRAIN mission, Phase 1 -- every ticker here was
REAL-VERIFIED via a live yfinance call on 2026-09-08, TWICE: once for a
current quote, and separately for genuine 2-YEAR historical depth (the
window this module's own trend/volatility classification actually
needs) -- a real, live end-to-end `regime --with-nifty-sectors` run
caught one ticker that passed the first check but failed the second
(see below), so both checks are load-bearing, not redundant. This is
the OFFICIAL NIFTY sectoral index for each sector, not research/
sector.py's own generic Yahoo GICS sector/industry classification (a
DIFFERENT, already-existing, coarser mechanism -- "Technology"/
"Financial Services" style buckets built by hand-classifying individual
symbols). Both are real and neither replaces the other: this dict
answers "how is the OFFICIAL NIFTY IT index doing," research.sector.
build_sector_map answers "what GICS sector is THIS symbol in."

NIFTY FINANCIAL SERVICES specifically: `^CNXFIN` (which would have
matched every other ticker's own `^CNX*` naming convention) LOOKED
correct in an initial 5-day check but turned out to have essentially
ZERO historical depth via Yahoo -- `period="2y"` returns 0 rows, and
`period="max"` errors with "must be one of: 1d, 5d". Confirmed via a
real, live `regime --with-nifty-sectors` run: NIFTY_FINANCIAL_SERVICES
came back UNKNOWN/UNKNOWN while all 8 other sectors resolved real
trend/volatility regimes. `NIFTY_FIN_SERVICE.NS` was checked as the
replacement and has genuine, real 2-year depth (457 daily rows,
2024-09-09 through 2026-09-08) -- used here instead. The two tickers
report slightly different index LEVELS (27879.50 vs 25764.30 on the
same day), so they are not simply duplicates of the same feed; only
NIFTY_FIN_SERVICE.NS was proven usable for this module's own purpose.

GIFT Nifty was investigated and found NOT reliably available via Yahoo
(every plausible ticker guessed returned empty) -- a genuine, disclosed
gap, not attempted here."""


class VixRegime(str, Enum):
    ELEVATED = "ELEVATED"
    DEPRESSED = "DEPRESSED"
    NORMAL = "NORMAL"
    UNKNOWN = "UNKNOWN"


DEFAULT_VIX_LOOKBACK = 60
DEFAULT_VIX_ELEVATED_MULTIPLIER = 1.3
DEFAULT_VIX_DEPRESSED_MULTIPLIER = 0.75
"""Explicit, named thresholds on current India VIX LEVEL vs. its own
trailing average -- NOT tuned against historical performance (no such
study exists), the same "no fabricated threshold until proven
otherwise" posture this module's own volatility-regime thresholds
already use. Deliberately NOT the same computation compute_benchmark_
context performs (that measures the ATR of whatever symbol it's given
-- calling it on ^INDIAVIX would answer "is India VIX's own volatility
elevated," a confusing second-order question); this measures the VIX
LEVEL itself relative to its own recent history, the more directly
useful "is fear elevated right now" question."""


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
class IndiaVixContext:
    symbol: str
    last_value: float | None
    trailing_average: float | None
    ratio_vs_trailing_average: float | None
    """current India VIX level divided by its own trailing average --
    the explainable ratio `regime` is thresholded on, same style as
    BenchmarkContext.atr_pct_vs_trailing_average."""
    regime: str
    """VixRegime.value."""


def compute_india_vix_context(
    *,
    provider: MarketDataProvider,
    symbol: str = "^INDIAVIX",
    period: str = "2y",
    interval: str = "1d",
    lookback: int = DEFAULT_VIX_LOOKBACK,
    elevated_multiplier: float = DEFAULT_VIX_ELEVATED_MULTIPLIER,
    depressed_multiplier: float = DEFAULT_VIX_DEPRESSED_MULTIPLIER,
) -> IndiaVixContext:
    """Never fabricates a regime when data is missing/insufficient --
    returns UNKNOWN, matching every other regime classification in this
    module. India VIX is fetched through the SAME MarketDataProvider
    every other symbol in this module uses (Yahoo by default) -- no new
    data source, just a new symbol."""
    unknown = VixRegime.UNKNOWN.value
    try:
        ohlcv = provider.fetch_ohlcv(symbol, period=period, interval=interval)
    except (MarketDataError, ValueError):
        return IndiaVixContext(symbol=symbol, last_value=None, trailing_average=None, ratio_vs_trailing_average=None, regime=unknown)

    closes = [bar.close for bar in ohlcv.bars]
    if len(closes) < lookback + 1:
        last_value = closes[-1] if closes else None
        return IndiaVixContext(symbol=symbol, last_value=last_value, trailing_average=None, ratio_vs_trailing_average=None, regime=unknown)

    last_value = float(closes[-1])
    # Trailing average EXCLUDES the current bar from its own baseline --
    # same "a single volatile day must not partially average itself
    # away" reasoning compute_benchmark_context already applies.
    trailing_window = closes[-(lookback + 1):-1]
    trailing_average = sum(trailing_window) / len(trailing_window)

    if trailing_average <= 0:
        return IndiaVixContext(symbol=symbol, last_value=last_value, trailing_average=trailing_average, ratio_vs_trailing_average=None, regime=unknown)

    ratio = last_value / trailing_average
    if ratio >= elevated_multiplier:
        regime = VixRegime.ELEVATED
    elif ratio <= depressed_multiplier:
        regime = VixRegime.DEPRESSED
    else:
        regime = VixRegime.NORMAL

    return IndiaVixContext(symbol=symbol, last_value=last_value, trailing_average=trailing_average, ratio_vs_trailing_average=ratio, regime=regime.value)


def compute_sector_index_regimes(
    sector_indices: Mapping[str, str] | None = None,
    *,
    provider: MarketDataProvider,
    now: datetime | None = None,
    period: str = "2y",
    interval: str = "1d",
) -> dict[str, "BenchmarkContext"]:
    """sector name -> BenchmarkContext, one call to compute_benchmark_
    context per real NIFTY sectoral index (NIFTY_SECTOR_INDICES by
    default) -- REUSES that function completely unchanged, this is pure
    aggregation, no new regime-computation logic. One bad/unreachable
    index must never abort the rest -- compute_benchmark_context already
    degrades to UNKNOWN internally on a fetch failure rather than
    raising, so no per-index try/except is needed here either."""
    indices = sector_indices if sector_indices is not None else NIFTY_SECTOR_INDICES
    return {
        sector: compute_benchmark_context(ticker, provider=provider, now=now, period=period, interval=interval)
        for sector, ticker in indices.items()
    }


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
    sector_index_regimes: Mapping[str, BenchmarkContext] = field(default_factory=dict)
    """INDIAN MARKET TRADING BRAIN mission: sector name -> real OFFICIAL
    NIFTY sectoral index regime (NIFTY_SECTOR_INDICES), DISTINCT from
    sector_strength above (which is this SCAN's own symbols grouped by
    generic Yahoo GICS sector -- a property of what was scanned, not of
    the real NIFTY sectoral indices themselves). Empty dict (never
    fabricated) unless build_market_regime_report's own
    include_nifty_sector_indices=True was passed -- opt-in, since this
    costs 9 extra fetches per report and every EXISTING caller of this
    function must see byte-for-byte unchanged behavior by default."""
    india_vix: IndiaVixContext | None = None
    """None (never fabricated) unless build_market_regime_report's own
    include_india_vix=True was passed -- opt-in, same reasoning as
    sector_index_regimes above."""


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
    include_nifty_sector_indices: bool = False,
    include_india_vix: bool = False,
) -> MarketRegimeReport:
    """`include_nifty_sector_indices`/`include_india_vix` are opt-in and
    default OFF -- every existing caller of this function sees
    byte-for-byte unchanged behavior (same fields populated, same
    number of network fetches) unless it explicitly asks for the new
    INDIAN MARKET TRADING BRAIN mission fields."""
    resolved_now = now or datetime.now(timezone.utc)
    breadth = compute_breadth(scan_report)
    resolved_benchmark = scan_report.benchmark_symbol if benchmark_symbol is USE_SCAN_REPORTS_OWN_BENCHMARK else benchmark_symbol
    benchmark = compute_benchmark_context(resolved_benchmark, provider=provider, now=resolved_now, period=period, interval=interval)
    sectors = compute_sector_strength(scan_report, sector_map)
    sector_index_regimes = compute_sector_index_regimes(provider=provider, now=resolved_now, period=period, interval=interval) if include_nifty_sector_indices else {}
    india_vix = compute_india_vix_context(provider=provider, period=period, interval=interval) if include_india_vix else None
    return MarketRegimeReport(
        as_of=resolved_now, scan_id=scan_report.scan_id, breadth=breadth, benchmark=benchmark, sector_strength=sectors,
        sector_index_regimes=sector_index_regimes, india_vix=india_vix,
    )
