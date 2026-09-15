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

import os
import time
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from core.config import PROJECT_ROOT

DHAN_SCRIP_MASTER_URL = "https://images.dhan.co/api-data/api-scrip-master.csv"
DEFAULT_INSTRUMENT_CACHE_PATH = PROJECT_ROOT / "data" / "dhan" / "scrip-master.csv"


def _replace_with_retry(src: Path, dst: Path, *, attempts: int = 6, initial_delay: float = 0.02) -> None:
    """Real-time strategy validation mission, multi-symbol hardening pass
    -- found via a real, threaded concurrency test, not assumed:
    `os.replace()` on Windows can raise `PermissionError` ([WinError 5]
    "Access is denied") when another thread/process has `dst` open at
    that exact instant (e.g. a concurrent reader mid-`read_csv`, or
    another worker's own `from_csv` call) -- POSIX `rename()` has no such
    restriction (it atomically replaces the destination regardless of
    open handles), so this is a genuine Windows-specific failure mode a
    POSIX-first mental model misses. The lock is expected to be brief
    (a reader holds the file open only for the few milliseconds it takes
    to read+parse a ~a few-MB CSV, not indefinitely), so a short, bounded
    retry-with-backoff resolves the transient case; if `dst` is
    genuinely locked for longer than this budget (~1.3s total across 6
    attempts), that is a real, different problem this function
    deliberately does not paper over -- it re-raises the last error."""
    delay = initial_delay
    for attempt in range(attempts):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if attempt == attempts - 1:
                raise
            time.sleep(delay)
            delay *= 2

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
        import tempfile
        import urllib.request

        cache_path.parent.mkdir(parents=True, exist_ok=True)
        if force or not cache_path.exists():
            # Real-time strategy validation mission, multi-symbol hardening
            # pass: multiple independent `paper-live` worker PROCESSES (one
            # per symbol in tomorrow's fleet) can all reach this branch at
            # the same moment on a cold/force-refreshed cache. The original
            # urlretrieve(URL, cache_path) wrote DIRECTLY to the shared
            # final path -- not atomic, so two concurrent writers could
            # interleave and leave a torn/truncated CSV that a third reader
            # (from_csv below, in this or another process) could load
            # mid-write. Download to a unique temp file in the SAME
            # directory (so the final os.replace() is a same-filesystem
            # atomic rename on both POSIX and Windows -- never a partial
            # file visible to any reader) and only then publish it under
            # the real name. If two processes race, the loser's completed
            # temp file is simply discarded; both downloads fetch the SAME
            # public, unauthenticated, static content, so whichever
            # process's rename lands last is equally correct -- this is a
            # safety fix (never expose a torn file), not a claim of
            # avoiding redundant downloads under a startup burst.
            fd, tmp_name = tempfile.mkstemp(dir=cache_path.parent, prefix=f"{cache_path.name}.", suffix=".tmp")
            os.close(fd)
            tmp_path = Path(tmp_name)
            try:
                urllib.request.urlretrieve(DHAN_SCRIP_MASTER_URL, tmp_path)  # noqa: S310 -- fixed, hardcoded HTTPS URL, not user input
                _replace_with_retry(tmp_path, cache_path)
            except BaseException:
                tmp_path.unlink(missing_ok=True)
                raise
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

    def underlying_symbols_with_active_derivative(self, *, exchange: str = "NSE", instrument_name: str = "FUTSTK") -> set[str]:
        """The set of EQ-series trading symbols (this exchange's own
        convention, e.g. NSE's "RELIANCE") that are the underlying of at
        least one `instrument_name` derivative contract currently in this
        instrument master -- an exchange-vetted liquidity/market-cap gate
        (NSE only permits single-stock derivatives on names meeting
        SEBI's own eligibility criteria), used by quant_research/
        universe_expansion.py's H_XSECT_006 universe-widening
        pre-registration as an objective alternative to an unverifiable
        NIFTY-index-membership claim (market_data/universe.py's own
        module docstring already declined to implement that, for lack of
        a verifiable membership source). Excludes NSE's own exchange-
        connectivity test instruments (any trading symbol containing
        "NSETEST", never a real security)."""
        derivatives = self._frame[
            (self._frame["SEM_EXM_EXCH_ID"] == exchange)
            & (self._frame["SEM_SEGMENT"] == "D")
            & (self._frame["SEM_INSTRUMENT_NAME"] == instrument_name)
        ]
        underlyings = {symbol.split("-")[0] for symbol in derivatives["SEM_TRADING_SYMBOL"]}
        underlyings = {symbol for symbol in underlyings if "NSETEST" not in symbol}

        equity = self._frame[
            (self._frame["SEM_EXM_EXCH_ID"] == exchange) & (self._frame["SEM_SEGMENT"] == "E") & (self._frame["SEM_SERIES"] == "EQ")
        ]
        equity_symbols = set(equity["SEM_TRADING_SYMBOL"])
        return underlyings & equity_symbols

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
