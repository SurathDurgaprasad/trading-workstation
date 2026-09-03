import logging
from datetime import datetime
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict

from market.data_provider import get_market_data_provider
from market.indicators import TechnicalIndicators, compute_indicators

if TYPE_CHECKING:
    from market_data.contracts import SnapshotAdapter

logger = logging.getLogger(__name__)

UNKNOWN = "UNKNOWN"

DEFAULT_PERIOD = "6mo"
DEFAULT_INTERVAL = "1d"


class MarketContext(BaseModel):
    """Deterministic, serializable snapshot of a symbol's price and indicators.

    This is the only market-data representation that crosses into LangGraph
    state or an LLM prompt. Raw OHLCV frames never leave the market package.
    """

    model_config = ConfigDict(frozen=True)

    symbol: str
    as_of: datetime
    price: float

    sma_20: float | None = None
    sma_50: float | None = None
    rsi_14: float | None = None
    macd: float | None = None
    macd_signal: float | None = None
    macd_histogram: float | None = None
    atr_14: float | None = None
    volume_ratio: float | None = None
    volume_trend: str | None = None

    data_source: str | None = None
    """Phase 31 -- market.data_provider.DataSource.value (e.g. "YAHOO",
    "DHAN") for the bar `price`/`as_of` actually came from. None only for
    a MarketContext built directly via `from_indicators` without going
    through `get_market_context` (e.g. some existing tests/fixtures
    construct one by hand) -- never fabricated."""
    data_status: str | None = None
    """market.data_provider.DataStatus.value (e.g. "HISTORICAL", "LIVE",
    "DELAYED", "SIMULATED") for the same bar. Reuses the EXISTING
    OHLCVBar.status field rather than inventing new labels -- a Yahoo
    daily close is honestly HISTORICAL, never mislabeled LIVE."""
    data_freshness_seconds: float | None = None
    """Age of the bar (now - bar timestamp) at the moment it was
    fetched, from market_data.quality.SourceHealth -- only populated
    when a `live_snapshot_provider` was supplied to `get_market_context`
    and returned a usable snapshot; None otherwise (a plain historical
    fetch has no live "freshness" concept the same way)."""

    @classmethod
    def from_indicators(cls, indicators: TechnicalIndicators) -> "MarketContext":
        return cls(
            symbol=indicators.symbol,
            as_of=indicators.as_of,
            price=indicators.close,
            sma_20=indicators.sma_20,
            sma_50=indicators.sma_50,
            rsi_14=indicators.rsi_14,
            macd=indicators.macd.macd if indicators.macd else None,
            macd_signal=indicators.macd.signal if indicators.macd else None,
            macd_histogram=indicators.macd.histogram if indicators.macd else None,
            atr_14=indicators.atr_14,
            volume_ratio=indicators.volume.volume_ratio if indicators.volume else None,
            volume_trend=indicators.volume.trend if indicators.volume else None,
        )

    def to_prompt_lines(self) -> list[str]:
        """Deterministic OBSERVED MARKET DATA lines for LLM prompts and CLI output.

        Missing values render as UNKNOWN rather than being omitted, so the
        model is told explicitly what it does not know instead of inferring
        absence from silence.
        """

        def fmt(value: float | str | None, digits: int = 2) -> str:
            if value is None:
                return UNKNOWN
            if isinstance(value, str):
                return value
            return f"{value:.{digits}f}"

        return [
            f"Symbol: {self.symbol}",
            f"As of: {self.as_of.isoformat()}",
            f"Price: {fmt(self.price)}",
            f"SMA20: {fmt(self.sma_20)}",
            f"SMA50: {fmt(self.sma_50)}",
            f"RSI14: {fmt(self.rsi_14)}",
            f"MACD: {fmt(self.macd)}",
            f"MACD Signal: {fmt(self.macd_signal)}",
            f"MACD Histogram: {fmt(self.macd_histogram)}",
            f"ATR14: {fmt(self.atr_14)}",
            f"Volume Ratio (vs 20d avg): {fmt(self.volume_ratio)}",
            f"Volume Trend: {fmt(self.volume_trend)}",
            f"Data Source: {fmt(self.data_source)}",
            f"Data Status: {fmt(self.data_status)}",
            f"Data Freshness (seconds): {fmt(self.data_freshness_seconds, digits=1)}",
        ]


def get_market_context(
    symbol: str,
    *,
    period: str = DEFAULT_PERIOD,
    interval: str = DEFAULT_INTERVAL,
    live_snapshot_provider: "SnapshotAdapter | None" = None,
) -> MarketContext:
    """Fetch OHLCV for `symbol` and compute indicators, deterministically.

    Raises market.data_provider.MarketDataError on any fetch/data problem —
    callers must not swallow it into a silently-empty context.

    Phase 31 -- `live_snapshot_provider` is OPTIONAL (default None,
    matching every prior call site's behavior exactly). Indicators
    (SMA/RSI/MACD/ATR/volume) always come from the Yahoo historical
    series above -- no live source in this project can supply the
    warm-up history those need. When a `market_data.contracts.
    SnapshotAdapter` IS supplied (e.g. `market_data.adapters.dhan.
    build_dhan_adapter(...)`, or a `market_data.provider.
    UnifiedMarketDataFacade`'s own adapter) and returns a HEALTHY
    snapshot, ONLY `price`/`as_of`/`data_source`/`data_status`/
    `data_freshness_seconds` are overridden with that live value --
    the indicators underneath are still the Yahoo-derived ones,
    computed against the (slightly older) historical closing series.
    A failed or unhealthy live snapshot is logged and silently ignored
    -- the Yahoo historical context is always a safe, working fallback;
    a live-data problem must never break `decide`/`size`/`predict`."""

    normalized_symbol = symbol.strip().upper()
    provider = get_market_data_provider()
    ohlcv = provider.fetch_ohlcv(normalized_symbol, period=period, interval=interval)
    indicators = compute_indicators(ohlcv)
    context = MarketContext.from_indicators(indicators)

    last_bar = ohlcv.bars[-1] if ohlcv.bars else None
    if last_bar is not None:
        context = context.model_copy(update={"data_source": last_bar.source.value, "data_status": last_bar.status.value})

    if live_snapshot_provider is not None:
        context = _apply_live_overlay(context, normalized_symbol, live_snapshot_provider)

    return context


def _apply_live_overlay(context: "MarketContext", symbol: str, live_snapshot_provider: "SnapshotAdapter") -> "MarketContext":
    from market_data.quality import SourceStatus

    try:
        snapshot = live_snapshot_provider.get_snapshot(symbol)
    except Exception as exc:  # noqa: BLE001 -- a live overlay must never break the Yahoo historical fallback
        logger.info("Live snapshot provider failed for %s, continuing with Yahoo historical context: %s", symbol, exc)
        return context

    if snapshot.health.status != SourceStatus.HEALTHY or snapshot.latest_bar is None:
        logger.info(
            "Live snapshot for %s not usable (status=%s) -- continuing with Yahoo historical context.",
            symbol, snapshot.health.status.value,
        )
        return context

    bar = snapshot.latest_bar
    return context.model_copy(update={
        "price": bar.close,
        "as_of": bar.timestamp,
        "data_source": bar.source.value,
        "data_status": bar.status.value,
        "data_freshness_seconds": snapshot.health.age_seconds,
    })
