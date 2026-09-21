"""Point-in-time NSE single-stock-futures (FUTSTK) universe reconstruction.

Phase A of the edge-feasibility audit's newest mission
(audit/edge_feasibility/PHASE_A_POINT_IN_TIME_UNIVERSE.md, 2026-09-21):
`quant_research/universe_expansion.py`'s own "expanded" universe applies a
SINGLE CURRENT Dhan-scrip-master snapshot uniformly across 10 years of
history -- a disclosed, previously-unresolved survivorship dependency
(`H_XSECT_006` preregistration S7 item 5; `audit/edge_feasibility` Phase 2).
This module builds a REAL, DATED membership snapshot from NSE's own
authoritative bhavcopy archive, using the exact same semantic eligibility
definition `live.dhan.instruments.DhanInstrumentMap.
underlying_symbols_with_active_derivative(instrument_name="FUTSTK")`
already uses (single-stock futures specifically -- an exchange-vetted
liquidity/market-cap gate) -- this module does not redefine or widen that
criterion, per Phase A1's own explicit scope constraint.

Two real, distinct NSE archive generations were found and directly
verified this session (HTTP 200 responses observed; real file schema
downloaded and inspected) to jointly span the required window, with a
format transition confirmed to fall somewhere between 2024-06-28 (last
directly-verified classic-format 200) and 2024-07-15 (first directly
-verified classic-format 404):

  CLASSIC (verified back to at least 2016-01-04):
  https://archives.nseindia.com/content/historical/DERIVATIVES/{YYYY}/
  {MON}/fo{DD}{MON}{YYYY}bhav.csv.zip -- column `INSTRUMENT` == "FUTSTK",
  underlying NSE trading symbol in `SYMBOL`.

  UDiFF (verified forward to at least 2026-09-18):
  https://nsearchives.nseindia.com/content/fo/
  BhavCopy_NSE_FO_0_0_0_{YYYYMMDD}_F_0000.csv.zip -- column
  `FinInstrmTp` == "STF", underlying NSE trading symbol in `TckrSymb`.

The exact day-level transition date is NOT pinned down (a 2.5-week window
was directly verified via a small, deliberately paced sample of requests,
not exhaustive daily probing -- see the Phase A writeup for the full
disclosed rationale, including a real rate-limiting signal encountered
from NSE's own infrastructure after a burst of rapid archive requests).
`fetch_fno_bhavcopy` tries the format expected for the given date FIRST,
then falls back to the other format, so this ambiguity never causes a
wrong silent answer -- only, at worst, one extra HTTP round-trip on dates
inside the transition window.

KNOWN, DISCLOSED, NOT-RESOLVED-BY-THIS-MODULE gap (material, not
cosmetic -- see the Phase A writeup's own A5 decision): direct testing
this session found that of a 68-symbol sample of NSE names that show
FUTSTK eligibility in a 2022-06-15 snapshot but not in today's snapshot,
14/68 (20.6%) are COMPLETELY UNFETCHABLE from this project's own
yfinance-based `market.data_provider` under their historical ticker --
including large, currently very actively-traded names undergoing a
corporate action (e.g. Tata Motors' own 2024 demerger), not merely
genuinely illiquid/delisted names. This module can determine WAS-eligible
membership for a given historical date; it does NOT resolve historical
-ticker-to-current-ticker corporate-action chains (rename/merger/demerger)
-- that is a separate, substantial sub-project, out of this module's
scope. `SymbolMembershipSnapshot.symbols` may therefore include symbols
this project's OWN data provider cannot presently fetch price history
for; callers MUST check fetchability themselves before use, never assume
membership implies fetchable data.

This module NEVER fabricates a membership snapshot for a date it could
not actually retrieve and parse -- a failed/missing/unparseable date
returns `None` from `fetch_fno_bhavcopy`, never a guessed value or a
silent substitution of current-snapshot membership.
"""

from __future__ import annotations

import hashlib
import io
import zipfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd

# Last classic-format date directly verified to return HTTP 200 this
# session, and first classic-format date directly verified to return 404.
# The true cutover lies somewhere in this window -- not claimed more
# precisely than that.
CLASSIC_LAST_CONFIRMED_OK = date(2024, 6, 28)
CLASSIC_FIRST_CONFIRMED_404 = date(2024, 7, 15)

_MONTH_ABBR = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]


def classic_bhavcopy_url(trade_date: date) -> str:
    """archives.nseindia.com's legacy per-day F&O bhavcopy, verified this
    session to return real data for 2016-01-04, 2019-01-15, 2022-06-15,
    2024-01-15, and 2024-06-28 (all HTTP 200, real FUTSTK rows present)."""
    mon = _MONTH_ABBR[trade_date.month - 1]
    return (
        f"https://archives.nseindia.com/content/historical/DERIVATIVES/"
        f"{trade_date.year}/{mon}/fo{trade_date.day:02d}{mon}{trade_date.year}bhav.csv.zip"
    )


def udiff_bhavcopy_url(trade_date: date) -> str:
    """nsearchives.nseindia.com's current-generation "UDiFF Common
    Bhavcopy Final", verified this session to return real data for
    2026-09-18 (HTTP 200, real STF rows present) and confirmed NOT to
    exist for 2022-06-15 (HTTP 404)."""
    return (
        f"https://nsearchives.nseindia.com/content/fo/"
        f"BhavCopy_NSE_FO_0_0_0_{trade_date:%Y%m%d}_F_0000.csv.zip"
    )


@dataclass(frozen=True)
class BhavcopyFile:
    """A successfully retrieved, on-disk bhavcopy archive, with full
    provenance -- required by Phase A3's own reporting spec."""

    trade_date: date
    source_url: str
    format_name: str  # "classic" | "udiff"
    local_path: Path
    sha256: str


@dataclass(frozen=True)
class SymbolMembershipSnapshot:
    """The FUTSTK-eligible underlying universe as of one specific trade
    date, in this project's own Yahoo-style ".NS" symbol convention --
    directly comparable to `quant_research.universe_expansion`'s own
    symbol format, never to be confused with it (that module is a single,
    CURRENT snapshot; this is one of potentially many DATED snapshots)."""

    trade_date: date
    source: BhavcopyFile
    symbols: frozenset[str]


def _sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fetch_fno_bhavcopy(trade_date: date, cache_dir: Path, *, session=None) -> BhavcopyFile | None:
    """Downloads (or reuses a cached copy of) the real NSE F&O bhavcopy
    for `trade_date`, trying the format expected for that date first and
    falling back to the other format once. Returns `None` -- never a
    fabricated/guessed result -- if neither format is retrievable (a
    genuinely missing trading date, a holiday, or a transient failure).

    `session` is an injected `requests`-like object (must expose `.get(url,
    headers=...) -> response` with `.status_code`/`.content`) purely for
    testability without a real network call; production callers omit it
    and a real `requests.Session` (or `urllib`) is used. Callers are
    responsible for PACING repeated calls -- NSE's own infrastructure was
    directly observed this session to rate-limit/challenge a burst of
    rapid requests; this function makes exactly one (or, on a format
    -boundary date, two) HTTP request(s) per call and does not retry
    internally."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    cached = cache_dir / f"fno_bhav_{trade_date:%Y%m%d}.zip"
    manifest = cache_dir / f"fno_bhav_{trade_date:%Y%m%d}.manifest.txt"
    if cached.exists() and manifest.exists():
        source_url, format_name = manifest.read_text(encoding="utf-8").strip().split("\n")
        return BhavcopyFile(trade_date=trade_date, source_url=source_url, format_name=format_name, local_path=cached, sha256=_sha256_of(cached))

    try_udiff_first = trade_date > CLASSIC_FIRST_CONFIRMED_404
    ordered = (
        [(udiff_bhavcopy_url(trade_date), "udiff"), (classic_bhavcopy_url(trade_date), "classic")]
        if try_udiff_first
        else [(classic_bhavcopy_url(trade_date), "classic"), (udiff_bhavcopy_url(trade_date), "udiff")]
    )

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
        "Accept": "*/*",
        "Referer": "https://www.nseindia.com/all-reports-derivatives",
    }

    for url, format_name in ordered:
        if session is not None:
            response = session.get(url, headers=headers)
            status, content = response.status_code, response.content
        else:
            import urllib.error
            import urllib.request

            req = urllib.request.Request(url, headers=headers)
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 -- fixed HTTPS host, not user input
                    status, content = resp.status, resp.read()
            except urllib.error.HTTPError as exc:
                status, content = exc.code, b""

        if status == 200 and content:
            cached.write_bytes(content)
            manifest.write_text(f"{url}\n{format_name}", encoding="utf-8")
            return BhavcopyFile(trade_date=trade_date, source_url=url, format_name=format_name, local_path=cached, sha256=_sha256_of(cached))

    return None


def parse_futstk_underlyings(bhavcopy: BhavcopyFile) -> SymbolMembershipSnapshot:
    """Parses a downloaded bhavcopy zip and returns the FUTSTK/STF
    underlying symbols as Yahoo-style ".NS" symbols. Malformed or
    unexpected rows are dropped via pandas' own NaN/parsing behavior, not
    silently coerced; duplicate underlyings collapse naturally via `set`.
    Raises `ValueError` on a genuinely unrecognized format_name or a zip
    with no inner CSV -- never returns a partial/guessed result."""
    with zipfile.ZipFile(bhavcopy.local_path) as zf:
        names = zf.infolist()
        if not names:
            raise ValueError(f"{bhavcopy.local_path}: empty zip archive, cannot parse.")
        with zf.open(names[0].filename) as f:
            frame = pd.read_csv(io.BytesIO(f.read()))
    frame.columns = [c.strip() for c in frame.columns]

    if bhavcopy.format_name == "classic":
        rows = frame[frame["INSTRUMENT"].astype(str).str.strip() == "FUTSTK"]
        raw_symbols = rows["SYMBOL"].dropna().astype(str).str.strip()
    elif bhavcopy.format_name == "udiff":
        rows = frame[frame["FinInstrmTp"].astype(str).str.strip() == "STF"]
        raw_symbols = rows["TckrSymb"].dropna().astype(str).str.strip()
    else:
        raise ValueError(f"Unrecognized bhavcopy format_name={bhavcopy.format_name!r} (expected 'classic' or 'udiff').")

    symbols = frozenset(f"{s}.NS" for s in raw_symbols.unique() if s and "NSETEST" not in s)
    return SymbolMembershipSnapshot(trade_date=bhavcopy.trade_date, source=bhavcopy, symbols=symbols)
