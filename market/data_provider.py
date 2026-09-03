from datetime import datetime
from enum import Enum
from typing import Protocol, runtime_checkable

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field


class MarketDataProviderName(str, Enum):
    YAHOO = "yahoo"


class DataSource(str, Enum):
    """Phase 12 §5 — explicit provenance. MOCK/BROKER were added generic
    ("BROKER, not DHAN — no broker adapter exists yet") since no real
    broker existed at the time. Phase 15 adds DHAN, the first concrete
    broker value, once live/dhan/ actually exists; BROKER stays reserved
    for any future non-Dhan broker rather than being repurposed."""

    YAHOO = "YAHOO"
    MOCK = "MOCK"
    BROKER = "BROKER"
    DHAN = "DHAN"


class DataStatus(str, Enum):
    """Phase 12 §2/§5 — answers "is this safe to trade on?" at a glance.
    LIVE and DELAYED were reserved for a real broker feed that did not
    exist yet as of Phase 12; Phase 15's DhanMarketDataSource is the first
    code path allowed to set status=LIVE. SIMULATED is exclusively the
    mock feed's — it must never be confused with LIVE, even though both
    stream bar-by-bar."""

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
    # Phase 33 bug fix: `pd.Timestamp` IS a `datetime` subclass, so the
    # `isinstance(value, datetime)` branch below previously matched EVERY
    # real DataFrame index value from `.iterrows()` (always a pd.Timestamp)
    # and returned it completely as-is -- the tzinfo-stripping logic three
    # lines down was DEAD CODE for the one call site that actually matters
    # (OHLCV.from_dataframe), only ever running for a raw, non-Timestamp,
    # non-datetime input (e.g. a plain string) that needed `pd.Timestamp(value)`
    # to parse it in the first place. Found via a real scan against a live
    # benchmark (^NSEI) whose Yahoo data carries an Asia/Kolkata-aware
    # index: market_intelligence.scanner._screen_symbol's benchmark
    # reindex raised `TypeError: Cannot compare dtypes datetime64[us,
    # UTC+05:30] and datetime64[us]` because ^NSEI's bars kept their real
    # tzinfo while other symbols' bars (whatever Yahoo happened to hand
    # back for them) did not -- a direct violation of this project's own
    # "Yahoo/mock bars are naive by convention" invariant, documented and
    # relied on in live/freshness.py, market_data/quality.py, and
    # learning/regime.py alike.
    parsed = value if isinstance(value, datetime) else pd.Timestamp(value).to_pydatetime()
    if parsed.tzinfo is not None:
        return parsed.replace(tzinfo=None)
    return parsed
