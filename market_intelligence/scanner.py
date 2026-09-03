"""Phase 19 -- market scanner: MarketUniverse -> ranked, explainable
ScanReport. No AI, no recommendation, no buy/sell/quantity/price level --
see market_intelligence/models.py's module docstring.

Reuses, never duplicates:
  - market.data_provider.MarketDataProvider for historical OHLCV (the
    caller decides live/cached/fake -- this module takes no default so a
    test can never accidentally hit the network).
  - market.indicators.compute_indicator_series for every technical
    primitive (SMA20/50, RSI14, MACD, ATR14, volume ratio/trend).
  - market_data.universe.MarketUniverse for the instrument list.

Every symbol's fetch/scoring is independent and wrapped so one bad symbol
(fetch failure, insufficient history, bad data) cannot abort the scan for
the rest of the universe -- it is recorded in `excluded` instead.
"""

import uuid
from collections.abc import Mapping
from datetime import datetime, timezone

import pandas as pd

from market.data_provider import MarketDataError, MarketDataProvider
from market.indicators import compute_indicator_series
from market_data.universe import MarketUniverse
from market_intelligence.config import ScannerConfig
from market_intelligence.models import CandidateScore, ExcludedCandidate, ScanReport


class _Passed:
    """Internal, pre-sector-aggregation record for one symbol that cleared
    every screening gate. Not exported -- callers only ever see the final
    CandidateScore/ExcludedCandidate models."""

    def __init__(
        self,
        *,
        symbol: str,
        as_of: datetime,
        last_close: float,
        avg_daily_value: float,
        volume_ratio: float | None,
        trend_score: float,
        trend_note: str,
        momentum_score: float,
        rsi: float,
        breakout_score: float,
        prior_high: float,
        trailing_return: float | None,
        relative_strength_score: float | None,
    ):
        self.symbol = symbol
        self.as_of = as_of
        self.last_close = last_close
        self.avg_daily_value = avg_daily_value
        self.volume_ratio = volume_ratio
        self.trend_score = trend_score
        self.trend_note = trend_note
        self.momentum_score = momentum_score
        self.rsi = rsi
        self.breakout_score = breakout_score
        self.prior_high = prior_high
        self.trailing_return = trailing_return
        self.relative_strength_score = relative_strength_score


def run_scan(
    universe: MarketUniverse,
    *,
    provider: MarketDataProvider,
    benchmark_symbol: str | None = "^NSEI",
    sector_map: Mapping[str, str] | None = None,
    config: ScannerConfig | None = None,
    period: str = "1y",
    interval: str = "1d",
    now: datetime | None = None,
) -> ScanReport:
    config = config or ScannerConfig()
    scan_time = now or datetime.now(timezone.utc)

    benchmark_series, benchmark_unavailable_reason = _fetch_benchmark(
        provider, benchmark_symbol, period=period, interval=interval
    )

    passed: list[_Passed] = []
    excluded: list[ExcludedCandidate] = []

    for symbol in universe.symbols:
        result = _screen_symbol(
            symbol,
            provider=provider,
            benchmark_series=benchmark_series,
            config=config,
            period=period,
            interval=interval,
        )
        if isinstance(result, ExcludedCandidate):
            excluded.append(result)
        else:
            passed.append(result)

    sector_strength_by_symbol = _compute_sector_strength(passed, sector_map)

    candidates = [
        _finalize_candidate(item, sector_strength_by_symbol.get(item.symbol), config)
        for item in passed
    ]
    candidates.sort(key=lambda c: (-c.composite_score, c.symbol))

    return ScanReport(
        scan_id=uuid.uuid4().hex,
        as_of=scan_time,
        universe_mode=universe.mode,
        universe_size=len(universe),
        benchmark_symbol=benchmark_symbol,
        benchmark_unavailable_reason=benchmark_unavailable_reason,
        config_version=config.version_id(),
        candidates=candidates,
        excluded=excluded,
    )


def _fetch_benchmark(
    provider: MarketDataProvider, benchmark_symbol: str | None, *, period: str, interval: str
) -> tuple[pd.DataFrame | None, str | None]:
    if benchmark_symbol is None:
        return None, None
    try:
        ohlcv = provider.fetch_ohlcv(benchmark_symbol, period=period, interval=interval)
        series = compute_indicator_series(ohlcv)
    except (MarketDataError, ValueError) as exc:
        return None, f"Failed to fetch/compute benchmark {benchmark_symbol!r}: {exc}"
    return series, None


def _screen_symbol(
    symbol: str,
    *,
    provider: MarketDataProvider,
    benchmark_series: pd.DataFrame | None,
    config: ScannerConfig,
    period: str,
    interval: str,
) -> "_Passed | ExcludedCandidate":
    normalized = symbol.strip().upper()

    try:
        ohlcv = provider.fetch_ohlcv(normalized, period=period, interval=interval)
    except MarketDataError as exc:
        return ExcludedCandidate(symbol=normalized, as_of=None, reason=f"Data fetch failed: {exc}")

    try:
        series = compute_indicator_series(ohlcv)
    except ValueError as exc:
        return ExcludedCandidate(symbol=normalized, as_of=None, reason=f"No usable bars: {exc}")

    if len(series) < config.min_bars:
        return ExcludedCandidate(
            symbol=normalized, as_of=_as_of(series), reason=f"Insufficient history: {len(series)} bars, need >= {config.min_bars}."
        )

    last = series.iloc[-1]
    as_of = _as_of(series)

    if pd.isna(last[["sma_20", "sma_50", "rsi_14", "atr_14"]]).any():
        return ExcludedCandidate(symbol=normalized, as_of=as_of, reason="Indicator values not yet available for the latest bar (insufficient warm-up history).")

    atr = float(last["atr_14"])
    if atr <= 0:
        return ExcludedCandidate(symbol=normalized, as_of=as_of, reason=f"Non-positive ATR14 ({atr}) -- cannot evaluate volatility.")

    last_close = float(last["close"])
    if last_close < config.min_price:
        return ExcludedCandidate(symbol=normalized, as_of=as_of, reason=f"Price {last_close:.2f} below minimum {config.min_price:.2f}.")
    if config.max_price is not None and last_close > config.max_price:
        return ExcludedCandidate(symbol=normalized, as_of=as_of, reason=f"Price {last_close:.2f} above maximum {config.max_price:.2f}.")

    lookback = min(config.liquidity_lookback, len(series))
    recent = series.iloc[-lookback:]
    avg_daily_value = float((recent["close"] * recent["volume"]).mean())
    if avg_daily_value < config.min_avg_daily_value:
        return ExcludedCandidate(
            symbol=normalized, as_of=as_of,
            reason=f"Avg daily value {avg_daily_value:,.2f} below minimum {config.min_avg_daily_value:,.2f}.",
        )

    volume_ratio = None if pd.isna(last["volume_ratio"]) else float(last["volume_ratio"])
    if volume_ratio is not None and volume_ratio < config.min_volume_ratio:
        return ExcludedCandidate(
            symbol=normalized, as_of=as_of,
            reason=f"Volume ratio {volume_ratio:.2f} below minimum {config.min_volume_ratio:.2f}.",
        )

    atr_pct = atr / last_close
    if config.min_atr_pct_of_price is not None and atr_pct < config.min_atr_pct_of_price:
        return ExcludedCandidate(symbol=normalized, as_of=as_of, reason=f"ATR% of price {atr_pct:.4f} below minimum {config.min_atr_pct_of_price:.4f}.")
    if config.max_atr_pct_of_price is not None and atr_pct > config.max_atr_pct_of_price:
        return ExcludedCandidate(symbol=normalized, as_of=as_of, reason=f"ATR% of price {atr_pct:.4f} above maximum {config.max_atr_pct_of_price:.4f}.")

    sma_20 = float(last["sma_20"])
    sma_50 = float(last["sma_50"])
    if last_close > sma_20 > sma_50:
        trend_score, trend_note = 1.0, f"uptrend (close {last_close:.2f} > SMA20 {sma_20:.2f} > SMA50 {sma_50:.2f})"
    elif last_close < sma_20 < sma_50:
        trend_score, trend_note = -1.0, f"downtrend (close {last_close:.2f} < SMA20 {sma_20:.2f} < SMA50 {sma_50:.2f})"
    else:
        trend_score, trend_note = 0.0, f"sideways/mixed (close {last_close:.2f}, SMA20 {sma_20:.2f}, SMA50 {sma_50:.2f})"

    rsi = float(last["rsi_14"])
    momentum_score = (rsi - 50.0) / 50.0

    breakout_lookback = min(config.breakout_lookback, len(series) - 1)
    prior_window = series.iloc[-(breakout_lookback + 1):-1]
    prior_high = float(prior_window["high"].max()) if not prior_window.empty else float("nan")
    breakout_score = (last_close - prior_high) / prior_high if prior_high > 0 else 0.0

    rs_lookback = min(config.relative_strength_lookback, len(series) - 1)
    reference_close = float(series["close"].iloc[-(rs_lookback + 1)])
    trailing_return = (last_close / reference_close - 1) if reference_close > 0 else None

    relative_strength_score = None
    if trailing_return is not None and benchmark_series is not None:
        aligned = benchmark_series["close"].reindex(series.index, method="ffill")
        bench_reference = aligned.iloc[-(rs_lookback + 1)]
        bench_last = aligned.iloc[-1]
        if pd.notna(bench_reference) and pd.notna(bench_last) and bench_reference > 0:
            benchmark_return = float(bench_last) / float(bench_reference) - 1
            relative_strength_score = trailing_return - benchmark_return

    return _Passed(
        symbol=normalized, as_of=as_of, last_close=last_close, avg_daily_value=avg_daily_value,
        volume_ratio=volume_ratio, trend_score=trend_score, trend_note=trend_note,
        momentum_score=momentum_score, rsi=rsi, breakout_score=breakout_score, prior_high=prior_high,
        trailing_return=trailing_return, relative_strength_score=relative_strength_score,
    )


def _compute_sector_strength(
    passed: list[_Passed], sector_map: Mapping[str, str] | None
) -> dict[str, float]:
    """Sector strength is computed FROM the scanned universe's own sector
    composition (each sector's mean trailing return vs. the whole scanned
    universe's mean) -- not from an external sector-index feed, since none
    is integrated. Symbols with no sector tag, or when sector_map is not
    supplied at all, simply get no sector_strength_score (None, reported
    honestly in the explanation, never fabricated as 0)."""
    if not sector_map:
        return {}

    tagged = [(item.symbol, sector_map.get(item.symbol.strip().upper())) for item in passed]
    returns_by_symbol = {item.symbol: item.trailing_return for item in passed if item.trailing_return is not None}
    if not returns_by_symbol:
        return {}

    universe_avg = sum(returns_by_symbol.values()) / len(returns_by_symbol)

    sector_returns: dict[str, list[float]] = {}
    for symbol, sector in tagged:
        if sector is None or symbol not in returns_by_symbol:
            continue
        sector_returns.setdefault(sector, []).append(returns_by_symbol[symbol])

    sector_avg = {sector: sum(values) / len(values) for sector, values in sector_returns.items()}

    result: dict[str, float] = {}
    for symbol, sector in tagged:
        if sector is not None and sector in sector_avg:
            result[symbol] = sector_avg[sector] - universe_avg
    return result


def _finalize_candidate(item: _Passed, sector_strength_score: float | None, config: ScannerConfig) -> CandidateScore:
    composite = (
        config.weight_trend * item.trend_score
        + config.weight_momentum * item.momentum_score
        + config.weight_breakout * item.breakout_score
        + config.weight_relative_strength * (item.relative_strength_score or 0.0)
        + config.weight_sector_strength * (sector_strength_score or 0.0)
    )

    explanation = [
        f"Trend: {item.trend_note} -> score {item.trend_score:+.2f}",
        f"Momentum: RSI14={item.rsi:.1f} -> score {item.momentum_score:+.2f}",
        (
            f"Breakout: close {item.last_close:.2f} vs prior {config.breakout_lookback}-bar high {item.prior_high:.2f} "
            f"-> score {item.breakout_score:+.4f}"
        ),
        (
            f"Relative strength ({config.relative_strength_lookback}-bar) vs benchmark: {item.relative_strength_score:+.4f}"
            if item.relative_strength_score is not None
            else "Relative strength: not available (no benchmark data)."
        ),
        (
            f"Sector strength: {sector_strength_score:+.4f} (sector avg trailing return vs. scanned universe avg)"
            if sector_strength_score is not None
            else "Sector strength: not available (no sector tag configured for this symbol)."
        ),
        f"Liquidity: avg daily value {item.avg_daily_value:,.2f} over trailing bars.",
        (
            f"Volume: {item.volume_ratio:.2f}x its 20-day average."
            if item.volume_ratio is not None
            else "Volume: ratio not available."
        ),
    ]

    return CandidateScore(
        symbol=item.symbol, as_of=item.as_of, last_close=item.last_close, avg_daily_value=item.avg_daily_value,
        volume_ratio=item.volume_ratio, trend_score=item.trend_score, momentum_score=item.momentum_score,
        breakout_score=item.breakout_score, relative_strength_score=item.relative_strength_score,
        sector_strength_score=sector_strength_score, composite_score=composite, explanation=explanation,
    )


def _as_of(series: pd.DataFrame) -> datetime:
    value = series.index[-1]
    if not isinstance(value, datetime):
        value = pd.Timestamp(value).to_pydatetime()
    if value.tzinfo is not None:
        value = value.replace(tzinfo=None)
    return value
