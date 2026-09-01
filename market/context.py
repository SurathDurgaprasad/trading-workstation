from datetime import datetime

from pydantic import BaseModel, ConfigDict

from market.data_provider import get_market_data_provider
from market.indicators import TechnicalIndicators, compute_indicators

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
        ]


def get_market_context(
    symbol: str,
    *,
    period: str = DEFAULT_PERIOD,
    interval: str = DEFAULT_INTERVAL,
) -> MarketContext:
    """Fetch OHLCV for `symbol` and compute indicators, deterministically.

    Raises market.data_provider.MarketDataError on any fetch/data problem —
    callers must not swallow it into a silently-empty context.
    """

    normalized_symbol = symbol.strip().upper()
    provider = get_market_data_provider()
    ohlcv = provider.fetch_ohlcv(normalized_symbol, period=period, interval=interval)
    indicators = compute_indicators(ohlcv)
    return MarketContext.from_indicators(indicators)
