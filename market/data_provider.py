from datetime import datetime
from enum import Enum
from typing import Protocol, runtime_checkable

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field


class MarketDataProviderName(str, Enum):
    YAHOO = "yahoo"


class DataSource(str, Enum):
    """Phase 12 §5 — explicit provenance. MOCK/BROKER are new; YAHOO is the
    only source that has ever existed before this phase. Deliberately
    generic (BROKER, not DHAN) — no broker adapter exists yet (spec §1: "the
    interface must NOT assume Dhan")."""

    YAHOO = "YAHOO"
    MOCK = "MOCK"
    BROKER = "BROKER"


class DataStatus(str, Enum):
    """Phase 12 §2/§5 — answers "is this safe to trade on?" at a glance.
    LIVE and DELAYED are reserved for a real broker feed that does not exist
    yet in this phase; nothing in this codebase may set status=LIVE today.
    SIMULATED is exclusively the mock feed's — it must never be confused
    with LIVE, even though both stream bar-by-bar."""

    LIVE = "LIVE"
    DELAYED = "DELAYED"
    HISTORICAL = "HISTORICAL"
    SIMULATED = "SIMULATED"


class OHLCVBar(BaseModel):
    model_config = ConfigDict(frozen=True)

    timestamp: datetime
    open: float = Field(gt=0)
    high: float = Field(gt=0)
    low: float = Field(gt=0)
    close: float = Field(gt=0)
    volume: float = Field(ge=0)

    # Additive, Phase 12 §2/§5 — defaults match every pre-Phase-12 call site
    # exactly (Yahoo, historical) so no existing construction site, CSV
    # cache round-trip, or test needs to change. New code paths (the mock
    # feed; a future real broker feed) set these explicitly.
    source: DataSource = DataSource.YAHOO
    status: DataStatus = DataStatus.HISTORICAL
    received_at: datetime | None = Field(
        default=None, description="When THIS process observed the bar — None for historical fetches, where the distinction from `timestamp` is not meaningful."
    )
    source_timestamp: datetime | None = Field(
        default=None, description="The upstream source's own timestamp for this bar, if it can differ from `timestamp` (e.g. late/delayed delivery). None when not applicable."
    )


class OHLCV(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    interval: str
    bars: list[OHLCVBar]

    def to_dataframe(self) -> pd.DataFrame:
        if not self.bars:
            return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])

        records = [
            {
                "Open": bar.open,
                "High": bar.high,
                "Low": bar.low,
                "Close": bar.close,
                "Volume": bar.volume,
            }
            for bar in self.bars
        ]
        index = pd.DatetimeIndex([bar.timestamp for bar in self.bars], name="Date")
        return pd.DataFrame(records, index=index)

    @classmethod
    def from_dataframe(
        cls,
        *,
        symbol: str,
        interval: str,
        frame: pd.DataFrame,
    ) -> "OHLCV":
        normalized = frame.copy()
        if normalized.empty:
            return cls(symbol=symbol, interval=interval, bars=[])

        if "Date" in normalized.columns:
            normalized = normalized.set_index("Date")

        required_columns = {"Open", "High", "Low", "Close", "Volume"}
        missing = required_columns.difference(normalized.columns)
        if missing:
            raise MarketDataError(
                f"OHLCV frame for {symbol} is missing columns: {sorted(missing)}"
            )

        bars = [
            OHLCVBar(
                timestamp=_to_timestamp(index_value),
                open=float(row["Open"]),
                high=float(row["High"]),
                low=float(row["Low"]),
                close=float(row["Close"]),
                volume=float(row["Volume"]),
            )
            for index_value, row in normalized.iterrows()
            if pd.notna(row["Open"])
            and pd.notna(row["High"])
            and pd.notna(row["Low"])
            and pd.notna(row["Close"])
            and pd.notna(row["Volume"])
        ]
        return cls(symbol=symbol, interval=interval, bars=bars)


class MarketDataError(Exception):
    """Raised when market data cannot be fetched or normalized."""


@runtime_checkable
class MarketDataProvider(Protocol):
    def fetch_ohlcv(
        self,
        symbol: str,
        *,
        period: str = "1y",
        interval: str = "1d",
    ) -> OHLCV:
        """Fetch OHLCV bars for a symbol."""


class YahooFinanceProvider:
    def fetch_ohlcv(
        self,
        symbol: str,
        *,
        period: str = "1y",
        interval: str = "1d",
    ) -> OHLCV:
        import yfinance as yf

        normalized_symbol = symbol.strip().upper()
        if not normalized_symbol:
            raise MarketDataError("Symbol must not be empty.")

        try:
            frame = yf.Ticker(normalized_symbol).history(
                period=period,
                interval=interval,
                auto_adjust=False,
            )
        except Exception as exc:
            raise MarketDataError(
                f"Failed to fetch Yahoo Finance data for {normalized_symbol}."
            ) from exc

        if frame is None or frame.empty:
            raise MarketDataError(
                f"No Yahoo Finance data returned for {normalized_symbol}."
            )

        return OHLCV.from_dataframe(
            symbol=normalized_symbol,
            interval=interval,
            frame=frame,
        )


def get_market_data_provider(
    provider: MarketDataProviderName = MarketDataProviderName.YAHOO,
) -> MarketDataProvider:
    if provider == MarketDataProviderName.YAHOO:
        return YahooFinanceProvider()

    raise ValueError(f"Unsupported market data provider: {provider}")


def _to_timestamp(value: object) -> datetime:
    if isinstance(value, datetime):
        return value
    parsed = pd.Timestamp(value).to_pydatetime()
    if parsed.tzinfo is not None:
        return parsed.replace(tzinfo=None)
    return parsed
