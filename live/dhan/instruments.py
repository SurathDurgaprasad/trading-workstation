"""Phase 15 §16 — deterministic Yahoo-symbol -> Dhan instrument mapping.
Never uses a Yahoo symbol as a Dhan identifier directly; Dhan's own
"Security ID" (an internal numeric ID, NOT the ISIN or trading symbol) is
what the WebSocket subscribe message and every REST call actually need.

Source of truth: Dhan's own public, unauthenticated instrument master CSV
(VERIFIED from https://dhanhq.co/docs/v2/instruments/, fetched and its
columns read directly on 2026-09-01):

  Compact:  https://images.dhan.co/api-data/api-scrip-master.csv
  Detailed: https://images.dhan.co/api-data/api-scrip-master-detailed.csv

Confirmed live example (fetched and read directly, not assumed): the
compact CSV's NSE/Equity row for RELIANCE is
`NSE,E,2885,EQUITY,0,RELIANCE,...` -- i.e. Dhan Security ID 2885 for
RELIANCE on NSE_EQ. tests/test_dhan_instruments.py uses this exact row as
its regression fixture.

Column layout (compact CSV, VERIFIED from the docs page):
  SEM_EXM_EXCH_ID, SEM_SEGMENT, SEM_SMST_SECURITY_ID, SEM_INSTRUMENT_NAME,
  SEM_EXPIRY_CODE, SEM_TRADING_SYMBOL, SEM_LOT_UNITS, SEM_CUSTOM_SYMBOL,
  SEM_EXPIRY_DATE, SEM_STRIKE_PRICE, SEM_OPTION_TYPE, SEM_TICK_SIZE,
  SEM_EXPIRY_FLAG, SEM_EXCH_INSTRUMENT_TYPE, SEM_SERIES, SM_SYMBOL_NAME

SEM_SEGMENT values (VERIFIED, Column Description table): C=Currency,
D=Derivatives, E=Equity, M=Commodity.
"""

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from core.config import PROJECT_ROOT

DHAN_SCRIP_MASTER_URL = "https://images.dhan.co/api-data/api-scrip-master.csv"
DEFAULT_INSTRUMENT_CACHE_PATH = PROJECT_ROOT / "data" / "dhan" / "scrip-master.csv"

# (SEM_EXM_EXCH_ID, SEM_SEGMENT) -> the WebSocket/REST "ExchangeSegment" string.
# VERIFIED against the Annexure's Exchange Segment table (same enum names used
# in both the instrument master and the live-feed subscribe request).
_EXCHANGE_SEGMENT_MAP: dict[tuple[str, str], str] = {
    ("NSE", "E"): "NSE_EQ",
    ("NSE", "D"): "NSE_FNO",
    ("NSE", "C"): "NSE_CURRENCY",
    ("BSE", "E"): "BSE_EQ",
    ("BSE", "D"): "BSE_FNO",
    ("BSE", "C"): "BSE_CURRENCY",
    ("MCX", "M"): "MCX_COMM",
}

_YAHOO_SUFFIX_TO_EXCHANGE = {".NS": "NSE", ".BO": "BSE"}


class InstrumentNotFoundError(LookupError):
    """No row in the instrument master matched -- raised rather than
    returning None, since a silently-missing mapping would otherwise
    surface as a much more confusing error deep inside the WebSocket
    client."""


@dataclass(frozen=True)
class DhanInstrument:
    security_id: str
    exchange_segment: str  # e.g. "NSE_EQ" -- the string the feed/REST APIs expect
    trading_symbol: str
    display_name: str


class DhanInstrumentMap:
    """Loads the instrument master once and answers lookups from an
    in-memory index -- 197k+ rows, so this is built once per process, not
    per lookup."""

    def __init__(self, frame: pd.DataFrame):
        self._frame = frame

    @classmethod
    def from_csv(cls, path: Path) -> "DhanInstrumentMap":
        frame = pd.read_csv(path, dtype=str, keep_default_na=False)
        return cls(frame)

    @classmethod
    def download(cls, cache_path: Path = DEFAULT_INSTRUMENT_CACHE_PATH, *, force: bool = False) -> "DhanInstrumentMap":
        """Downloads Dhan's public instrument master CSV (no authentication
        required -- it's a static file) and caches it locally. Reuses the
        cached copy unless `force=True`; the file is regenerated daily by
        Dhan, so callers running a live session should force-refresh at
        the start of each trading day rather than relying on a stale
        multi-day-old cache."""
        import urllib.request

        cache_path.parent.mkdir(parents=True, exist_ok=True)
        if force or not cache_path.exists():
            urllib.request.urlretrieve(DHAN_SCRIP_MASTER_URL, cache_path)  # noqa: S310 -- fixed, hardcoded HTTPS URL, not user input
        return cls.from_csv(cache_path)

    def lookup(self, *, trading_symbol: str, exchange: str, segment: str = "E") -> DhanInstrument:
        """`exchange` is "NSE"/"BSE"/"MCX" (SEM_EXM_EXCH_ID); `segment` is
        the single-letter SEM_SEGMENT code (default "E" for equity)."""
        exchange_segment = _EXCHANGE_SEGMENT_MAP.get((exchange, segment))
        if exchange_segment is None:
            raise InstrumentNotFoundError(f"No known ExchangeSegment mapping for exchange={exchange!r} segment={segment!r}.")

        matches = self._frame[
            (self._frame["SEM_EXM_EXCH_ID"] == exchange)
            & (self._frame["SEM_SEGMENT"] == segment)
            & (self._frame["SEM_TRADING_SYMBOL"] == trading_symbol)
        ]
        if matches.empty:
            raise InstrumentNotFoundError(f"No instrument found for trading_symbol={trading_symbol!r} exchange={exchange!r} segment={segment!r}.")
        row = matches.iloc[0]
        return DhanInstrument(
            security_id=row["SEM_SMST_SECURITY_ID"], exchange_segment=exchange_segment,
            trading_symbol=row["SEM_TRADING_SYMBOL"], display_name=row["SEM_CUSTOM_SYMBOL"],
        )

    def lookup_yahoo_symbol(self, yahoo_symbol: str) -> DhanInstrument:
        """"RELIANCE.NS" -> NSE equity lookup; "RELIANCE.BO" -> BSE. Never
        treats the Yahoo symbol itself as a broker identifier -- this is
        purely a convenience that parses the suffix this project's Yahoo
        data already uses elsewhere, then delegates to lookup()."""
        for suffix, exchange in _YAHOO_SUFFIX_TO_EXCHANGE.items():
            if yahoo_symbol.endswith(suffix):
                trading_symbol = yahoo_symbol[: -len(suffix)]
                return self.lookup(trading_symbol=trading_symbol, exchange=exchange, segment="E")
        raise InstrumentNotFoundError(f"Yahoo symbol {yahoo_symbol!r} has no recognized exchange suffix (.NS/.BO) -- pass exchange explicitly via lookup() instead.")
