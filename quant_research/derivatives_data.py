"""Phase 4 of the derivatives research mission (2026-09-21): the smallest
reusable data model for NSE futures/options history, built only after
Phase 3's own feasibility gate established that futures OHLC+OI and
options OI/OI-change are the strongest (Classification A) candidates
(`audit/derivatives_research/PHASE3_DATA_FEASIBILITY_GATE.md`).

Deliberately NOT a platform: two frozen dataclasses (`FuturesBar`,
`OptionBar`), two parsers that populate them from the SAME real,
already-verified NSE bhavcopy files
`quant_research.point_in_time_fno_universe.BhavcopyFile` already
retrieves (reused unmodified -- this module adds no new download
capability), and one deterministic futures-rollover selector. No trading
signal is computed anywhere in this module, per Phase 4's own explicit
scope boundary.

Every record carries full provenance (source, retrieval context, parser
version) so a downstream research script can always answer "where did
this number come from" -- matching this project's own established
no-fabrication discipline.
"""

from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass
from datetime import date, datetime

import pandas as pd

from quant_research.point_in_time_fno_universe import BhavcopyFile

PARSER_VERSION = "1.0"


@dataclass(frozen=True)
class FuturesBar:
    """One contract's own OHLC+OI observation, EOD-only (bhavcopy is the
    only source this module parses; a future, separately-scoped module
    could add Dhan's own intraday /charts/intraday+oi=true capability,
    confirmed available in Phase 1/2 but not built here)."""

    underlying: str  # Yahoo-style ".NS", e.g. "RELIANCE.NS"
    contract_symbol: str  # the raw underlying symbol as it appeared in the source row (pre ".NS" suffix)
    expiry: date
    timestamp: datetime  # the bhavcopy's own trade date, midnight -- EOD granularity, never fabricated as intraday
    open: float
    high: float
    low: float
    close: float
    volume: int
    open_interest: int
    open_interest_change: int | None  # None only if the source row's own OI-change field was itself missing/unparseable
    source: BhavcopyFile
    parser_version: str = PARSER_VERSION


@dataclass(frozen=True)
class OptionBar:
    underlying: str  # Yahoo-style ".NS"
    contract_symbol: str
    expiry: date
    strike: float
    option_type: str  # "CE" | "PE"
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int
    open_interest: int
    open_interest_change: int | None
    implied_volatility: float | None  # ALWAYS None from this module -- NSE bhavcopy has no IV field (Phase 3's own disclosed gap); never fabricated
    source: BhavcopyFile
    parser_version: str = PARSER_VERSION


def _read_bhavcopy_frame(bhavcopy: BhavcopyFile) -> pd.DataFrame:
    with zipfile.ZipFile(bhavcopy.local_path) as zf:
        names = zf.infolist()
        if not names:
            raise ValueError(f"{bhavcopy.local_path}: empty zip archive, cannot parse.")
        with zf.open(names[0].filename) as f:
            frame = pd.read_csv(io.BytesIO(f.read()))
    frame.columns = [c.strip() for c in frame.columns]
    return frame


def _is_sane_ohlc(open_: float, high: float, low: float, close: float) -> bool:
    """Deterministic impossible-price check: all positive, high is the
    true max, low is the true min. A row failing this is dropped, never
    silently included -- matches `market.data_provider.OHLCV.from_dataframe`'s
    own established OHLC-relationship validation for the equity pipeline."""
    if open_ <= 0 or high <= 0 or low <= 0 or close <= 0:
        return False
    return high >= max(open_, close, low) and low <= min(open_, close, high)


def _is_sane_oi(open_interest: float) -> bool:
    return open_interest >= 0


def parse_bhavcopy_futures(bhavcopy: BhavcopyFile) -> list[FuturesBar]:
    """FUTSTK/FUTIDX (classic) or STF/IDF (udiff) rows only -- reuses the
    exact same instrument-type dispatch `quant_research.point_in_time_
    fno_universe.parse_futstk_underlyings` already established, extended
    to keep the full OHLC/OI/expiry/index-vs-stock distinction that
    function itself discards (it only needs the underlying symbol)."""
    frame = _read_bhavcopy_frame(bhavcopy)
    bars: list[FuturesBar] = []

    if bhavcopy.format_name == "classic":
        rows = frame[frame["INSTRUMENT"].astype(str).str.strip().isin(["FUTSTK", "FUTIDX"])]
        for _, row in rows.iterrows():
            symbol = str(row["SYMBOL"]).strip()
            if not symbol or "NSETEST" in symbol:
                continue
            try:
                expiry = datetime.strptime(str(row["EXPIRY_DT"]).strip(), "%d-%b-%Y").date()
                o, h, l, c = float(row["OPEN"]), float(row["HIGH"]), float(row["LOW"]), float(row["CLOSE"])
                volume = int(row["CONTRACTS"])
                oi = int(row["OPEN_INT"])
                oi_change_raw = row.get("CHG_IN_OI")
                oi_change = int(oi_change_raw) if pd.notna(oi_change_raw) else None
                trade_date = datetime.strptime(str(row["TIMESTAMP"]).strip(), "%d-%b-%Y")
            except (ValueError, KeyError, TypeError):
                continue
            if not _is_sane_ohlc(o, h, l, c) or not _is_sane_oi(oi):
                continue
            bars.append(FuturesBar(
                underlying=f"{symbol}.NS", contract_symbol=symbol, expiry=expiry, timestamp=trade_date,
                open=o, high=h, low=l, close=c, volume=volume, open_interest=oi, open_interest_change=oi_change, source=bhavcopy,
            ))
    elif bhavcopy.format_name == "udiff":
        rows = frame[frame["FinInstrmTp"].astype(str).str.strip().isin(["STF", "IDF"])]
        for _, row in rows.iterrows():
            symbol = str(row["TckrSymb"]).strip()
            if not symbol or "NSETEST" in symbol:
                continue
            try:
                expiry = datetime.strptime(str(row["XpryDt"]).strip(), "%Y-%m-%d").date()
                o, h, l, c = float(row["OpnPric"]), float(row["HghPric"]), float(row["LwPric"]), float(row["ClsPric"])
                volume = int(row["TtlTradgVol"])
                oi = int(row["OpnIntrst"])
                oi_change_raw = row.get("ChngInOpnIntrst")
                oi_change = int(oi_change_raw) if pd.notna(oi_change_raw) else None
                trade_date = datetime.strptime(str(row["TradDt"]).strip(), "%Y-%m-%d")
            except (ValueError, KeyError, TypeError):
                continue
            if not _is_sane_ohlc(o, h, l, c) or not _is_sane_oi(oi):
                continue
            bars.append(FuturesBar(
                underlying=f"{symbol}.NS", contract_symbol=symbol, expiry=expiry, timestamp=trade_date,
                open=o, high=h, low=l, close=c, volume=volume, open_interest=oi, open_interest_change=oi_change, source=bhavcopy,
            ))
    else:
        raise ValueError(f"Unrecognized bhavcopy format_name={bhavcopy.format_name!r} (expected 'classic' or 'udiff').")

    # Deterministic ordering + dedup: a genuine duplicate row (identical
    # underlying+expiry+timestamp) collapses to one, never double-counted.
    seen: dict[tuple, FuturesBar] = {}
    for bar in bars:
        key = (bar.underlying, bar.expiry, bar.timestamp)
        seen[key] = bar
    return sorted(seen.values(), key=lambda b: (b.underlying, b.timestamp, b.expiry))


def parse_bhavcopy_options(bhavcopy: BhavcopyFile) -> list[OptionBar]:
    """OPTSTK/OPTIDX (classic) or STO/IDO (udiff) rows. Always sets
    `implied_volatility=None` -- NSE bhavcopy carries no IV field (Phase
    3's own disclosed gap); fabricating one via an in-house pricing model
    is explicitly out of this phase's scope."""
    frame = _read_bhavcopy_frame(bhavcopy)
    bars: list[OptionBar] = []

    if bhavcopy.format_name == "classic":
        rows = frame[frame["INSTRUMENT"].astype(str).str.strip().isin(["OPTSTK", "OPTIDX"])]
        for _, row in rows.iterrows():
            symbol = str(row["SYMBOL"]).strip()
            option_type_raw = str(row["OPTION_TYP"]).strip().upper()
            if not symbol or "NSETEST" in symbol or option_type_raw not in ("CE", "PE"):
                continue
            try:
                expiry = datetime.strptime(str(row["EXPIRY_DT"]).strip(), "%d-%b-%Y").date()
                strike = float(row["STRIKE_PR"])
                o, h, l, c = float(row["OPEN"]), float(row["HIGH"]), float(row["LOW"]), float(row["CLOSE"])
                volume = int(row["CONTRACTS"])
                oi = int(row["OPEN_INT"])
                oi_change_raw = row.get("CHG_IN_OI")
                oi_change = int(oi_change_raw) if pd.notna(oi_change_raw) else None
                trade_date = datetime.strptime(str(row["TIMESTAMP"]).strip(), "%d-%b-%Y")
            except (ValueError, KeyError, TypeError):
                continue
            if strike <= 0 or (o == 0 and h == 0 and l == 0 and c == 0):
                # A genuinely untraded strike (all-zero OHLC, per the real, quantified
                # illiquidity finding -- Phase 1) is not a "sane OHLC" violation, it is
                # an honest zero -- excluded here as uninformative, not fabricated as
                # bad data. Strike<=0 is a genuine parsing/data defect, excluded.
                continue
            if not _is_sane_ohlc(o, h, l, c) or not _is_sane_oi(oi):
                continue
            bars.append(OptionBar(
                underlying=f"{symbol}.NS", contract_symbol=symbol, expiry=expiry, strike=strike, option_type=option_type_raw,
                timestamp=trade_date, open=o, high=h, low=l, close=c, volume=volume, open_interest=oi,
                open_interest_change=oi_change, implied_volatility=None, source=bhavcopy,
            ))
    elif bhavcopy.format_name == "udiff":
        rows = frame[frame["FinInstrmTp"].astype(str).str.strip().isin(["STO", "IDO"])]
        for _, row in rows.iterrows():
            symbol = str(row["TckrSymb"]).strip()
            option_type_raw = str(row["OptnTp"]).strip().upper()
            if not symbol or "NSETEST" in symbol or option_type_raw not in ("CE", "PE"):
                continue
            try:
                expiry = datetime.strptime(str(row["XpryDt"]).strip(), "%Y-%m-%d").date()
                strike = float(row["StrkPric"])
                o, h, l, c = float(row["OpnPric"]), float(row["HghPric"]), float(row["LwPric"]), float(row["ClsPric"])
                volume = int(row["TtlTradgVol"])
                oi = int(row["OpnIntrst"])
                oi_change_raw = row.get("ChngInOpnIntrst")
                oi_change = int(oi_change_raw) if pd.notna(oi_change_raw) else None
                trade_date = datetime.strptime(str(row["TradDt"]).strip(), "%Y-%m-%d")
            except (ValueError, KeyError, TypeError):
                continue
            if strike <= 0 or (o == 0 and h == 0 and l == 0 and c == 0):
                continue
            if not _is_sane_ohlc(o, h, l, c) or not _is_sane_oi(oi):
                continue
            bars.append(OptionBar(
                underlying=f"{symbol}.NS", contract_symbol=symbol, expiry=expiry, strike=strike, option_type=option_type_raw,
                timestamp=trade_date, open=o, high=h, low=l, close=c, volume=volume, open_interest=oi,
                open_interest_change=oi_change, implied_volatility=None, source=bhavcopy,
            ))
    else:
        raise ValueError(f"Unrecognized bhavcopy format_name={bhavcopy.format_name!r} (expected 'classic' or 'udiff').")

    seen: dict[tuple, OptionBar] = {}
    for bar in bars:
        key = (bar.underlying, bar.expiry, bar.strike, bar.option_type, bar.timestamp)
        seen[key] = bar
    return sorted(seen.values(), key=lambda b: (b.underlying, b.timestamp, b.expiry, b.strike, b.option_type))


def select_active_futures_contract(
    candidates: list[FuturesBar], *, as_of: date, roll_days_before_expiry: int = 3,
) -> FuturesBar | None:
    """Deterministic, pre-declared futures-rollover rule: among same
    -underlying, same-date candidate contracts, pick the SOONEST-expiring
    one that still has MORE than `roll_days_before_expiry` days left
    before its own expiry (rolling forward early to avoid the illiquid
    final days of a contract's own life -- a standard, disclosed,
    non-optimized convention, not tuned against any historical result).
    If every non-expired candidate is within the roll window (e.g. on
    expiry day itself, when no further-dated contract has data yet),
    falls back to the soonest-expiring NON-EXPIRED one available rather
    than returning nothing -- NEVER silently drops a trading day. A
    contract whose own `expiry` is strictly before `as_of` is EXCLUDED
    from every path, including the fallback -- Phase 5's own leakage
    audit (item 5, "can a contract after expiry remain active?") found
    an earlier version of this function could fall through to an
    already-expired contract if one were ever passed in as a candidate
    (expected never to happen given real bhavcopy files, which stop
    listing a contract the day after its own expiry, but this function
    must not silently depend on that external guarantee). Returns `None`
    if `candidates` is empty, every candidate is already expired as of
    `as_of`, or `candidates` contains multiple underlyings is a raised
    error (a caller error, not a data gap)."""
    if not candidates:
        return None
    underlyings = {c.underlying for c in candidates}
    if len(underlyings) != 1:
        raise ValueError(f"select_active_futures_contract requires all candidates to share one underlying, got {underlyings}")

    not_expired = [c for c in candidates if c.expiry >= as_of]
    if not not_expired:
        return None

    eligible = [c for c in not_expired if (c.expiry - as_of).days > roll_days_before_expiry]
    pool = eligible if eligible else not_expired
    return min(pool, key=lambda c: c.expiry)


def build_continuous_futures_series(
    bars_by_date: dict[date, list[FuturesBar]], *, roll_days_before_expiry: int = 3,
) -> list[FuturesBar]:
    """Applies `select_active_futures_contract` independently at each
    date -- a genuinely causal rollover (only that date's own candidate
    contracts are considered, never a later date's). Dates with no
    candidates are simply absent from the result, never fabricated."""
    series: list[FuturesBar] = []
    for as_of in sorted(bars_by_date):
        candidates = bars_by_date[as_of]
        if not candidates:
            continue
        selected = select_active_futures_contract(candidates, as_of=as_of, roll_days_before_expiry=roll_days_before_expiry)
        if selected is not None:
            series.append(selected)
    return series


def is_stale_bar(bar: FuturesBar | OptionBar, previous_bar: FuturesBar | OptionBar | None) -> bool:
    """A bar is STALE if it exactly repeats the previous bar's own close
    price with zero volume -- a real, common options/futures phenomenon
    (an untraded contract's own EOD "close" is often just carried
    forward by the exchange, not a genuine new observation). Flags, does
    not drop -- the caller decides whether a stale bar is still usable
    for OI-only analysis (OI in this case is meaningful; the PRICE is
    not)."""
    if previous_bar is None:
        return False
    return bar.volume == 0 and bar.close == previous_bar.close
