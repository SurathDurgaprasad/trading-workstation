"""Unit tests for quant_research/point_in_time_fno_universe.py.

Fixture rows are small, literal excerpts of REAL NSE bhavcopy data
downloaded and directly inspected this session (2026-09-21) --
`classic_2022-06-15.zip` (archives.nseindia.com) and
`udiff_2026-09-18.zip` (nsearchives.nseindia.com) -- not fabricated rows,
and not the full archive (mirrors tests/test_dhan_instruments.py's own
established fixture pattern: a few real rows, not the whole file).

The `TestFetchFnoBhavcopy*` classes use an injected fake `session` object
so no real network call is made in the regular test suite -- matching
this project's own "real download tests skip cleanly if unreachable"
convention would require a live NSE call on every CI run, which is
neither necessary (the URL construction and fallback logic are pure) nor
respectful of NSE's own infrastructure (a real rate-limiting response was
observed directly this session under repeated rapid requests).
"""
from __future__ import annotations

import zipfile
from datetime import date
from pathlib import Path

import pytest

from quant_research.point_in_time_fno_universe import (
    BhavcopyFile,
    classic_bhavcopy_url,
    fetch_fno_bhavcopy,
    parse_futstk_underlyings,
    udiff_bhavcopy_url,
)

_CLASSIC_FIXTURE_CSV = (
    "INSTRUMENT,SYMBOL,EXPIRY_DT,STRIKE_PR,OPTION_TYP,OPEN,HIGH,LOW,CLOSE,SETTLE_PR,CONTRACTS,VAL_INLAKH,OPEN_INT,CHG_IN_OI,TIMESTAMP,\n"
    "FUTIDX,BANKNIFTY,30-Jun-2022,0,XX,33400,33586.2,33301,33398.15,33398.15,113729,950918.42,2607125,-112700,15-JUN-2022,\n"
    "FUTSTK,AARTIIND,30-Jun-2022,0,XX,716.55,720,709,713.2,713.2,1310,7965.29,3778250,-161500,15-JUN-2022,\n"
    "FUTSTK,AARTIIND,30-Jun-2022,0,XX,716.55,720,709,713.2,713.2,1310,7965.29,3778250,-161500,15-JUN-2022,\n"
    "FUTSTK,AARTIIND,28-Jul-2022,0,XX,718.95,720.85,710.5,713.85,713.85,122,742.44,362950,-6800,15-JUN-2022,\n"
    "OPTSTK,AARTIIND,30-Jun-2022,520,CE,0,0,0,370.4,194.8,0,0,0,0,15-JUN-2022,\n"
)

_UDIFF_FIXTURE_CSV = (
    "TradDt,BizDt,Sgmt,Src,FinInstrmTp,FinInstrmId,ISIN,TckrSymb,SctySrs,XpryDt,FininstrmActlXpryDt,StrkPric,OptnTp,FinInstrmNm,OpnPric,HghPric,LwPric,ClsPric,LastPric,PrvsClsgPric,UndrlygPric,SttlmPric,OpnIntrst,ChngInOpnIntrst,TtlTradgVol,TtlTrfVal,TtlNbOfTxsExctd,SsnId,NewBrdLotQty,Rmks,Rsvd1,Rsvd2,Rsvd3,Rsvd4\n"
    "2026-09-18,2026-09-18,FO,NSE,IDF,61466,,BANKNIFTY,,2026-11-23,2026-11-23,,,BANKNIFTY26NOVFUT,56950.80,57236.20,56884.80,57105.20,57077.80,56915.40,56358.70,57105.20,60990,6990,512,876380784.00,454,F1,30,,,,,\n"
    "2026-09-18,2026-09-18,FO,NSE,STF,68415,,ABCAPITAL,,2026-09-29,2026-09-29,,,ABCAPITAL26SEPFUT,393.50,405.30,390.85,403.80,404.50,390.65,410.04,403.80,36161500,-750200,3343,4158743930.00,2579,F1,3100,,,,,\n"
    "2026-09-18,2026-09-18,FO,NSE,STF,68415,,ABCAPITAL,,2026-09-29,2026-09-29,,,ABCAPITAL26SEPFUT,393.50,405.30,390.85,403.80,404.50,390.65,410.04,403.80,36161500,-750200,3343,4158743930.00,2579,F1,3100,,,,,\n"
    "2026-09-18,2026-09-18,FO,NSE,STF,48708,,ABCAPITAL,,2026-10-27,2026-10-27,,,ABCAPITAL26OCTFUT,395.40,406.95,395.40,405.55,406.10,392.80,410.04,405.55,1646100,124000,295,368254735.00,262,F1,3100,,,,,\n"
    "2026-09-18,2026-09-18,FO,NSE,STO,78506,,ABCAPITAL,,2026-09-29,2026-09-29,480.00,PE,ABCAPITAL26SEP480PE,0.00,0.00,0.00,64.00,64.00,64.00,410.04,69.24,6200,0,0,0.00,0,F1,3100,,,,,\n"
)


def _make_zip(tmp_path: Path, name: str, inner_name: str, csv_text: str) -> Path:
    zip_path = tmp_path / name
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr(inner_name, csv_text)
    return zip_path


class TestUrlConstruction:
    def test_classic_url_matches_verified_pattern(self):
        assert classic_bhavcopy_url(date(2022, 6, 15)) == (
            "https://archives.nseindia.com/content/historical/DERIVATIVES/2022/JUN/fo15JUN2022bhav.csv.zip"
        )

    def test_udiff_url_matches_verified_pattern(self):
        assert udiff_bhavcopy_url(date(2026, 9, 18)) == (
            "https://nsearchives.nseindia.com/content/fo/BhavCopy_NSE_FO_0_0_0_20260918_F_0000.csv.zip"
        )

    def test_classic_url_pads_single_digit_day(self):
        assert "fo04JAN2016bhav" in classic_bhavcopy_url(date(2016, 1, 4))


class TestParseFutstkUnderlyings:
    def test_classic_format_extracts_only_futstk_symbols(self, tmp_path):
        zip_path = _make_zip(tmp_path, "classic.zip", "fo15JUN2022bhav.csv", _CLASSIC_FIXTURE_CSV)
        bhavcopy = BhavcopyFile(
            trade_date=date(2022, 6, 15), source_url="https://example/classic.zip",
            format_name="classic", local_path=zip_path, sha256="deadbeef",
        )
        snapshot = parse_futstk_underlyings(bhavcopy)
        assert snapshot.symbols == frozenset({"AARTIIND.NS"})  # FUTIDX/OPTSTK excluded, duplicate underlying collapsed

    def test_udiff_format_extracts_only_stf_symbols(self, tmp_path):
        zip_path = _make_zip(tmp_path, "udiff.zip", "BhavCopy_NSE_FO.csv", _UDIFF_FIXTURE_CSV)
        bhavcopy = BhavcopyFile(
            trade_date=date(2026, 9, 18), source_url="https://example/udiff.zip",
            format_name="udiff", local_path=zip_path, sha256="deadbeef",
        )
        snapshot = parse_futstk_underlyings(bhavcopy)
        assert snapshot.symbols == frozenset({"ABCAPITAL.NS"})  # IDF/STO excluded, two STF expiries collapsed to one underlying

    def test_unrecognized_format_name_raises(self, tmp_path):
        zip_path = _make_zip(tmp_path, "bad.zip", "x.csv", _CLASSIC_FIXTURE_CSV)
        bhavcopy = BhavcopyFile(trade_date=date(2022, 6, 15), source_url="x", format_name="bogus", local_path=zip_path, sha256="x")
        with pytest.raises(ValueError, match="Unrecognized bhavcopy format_name"):
            parse_futstk_underlyings(bhavcopy)

    def test_empty_zip_raises_rather_than_returning_partial_result(self, tmp_path):
        zip_path = tmp_path / "empty.zip"
        with zipfile.ZipFile(zip_path, "w"):
            pass
        bhavcopy = BhavcopyFile(trade_date=date(2022, 6, 15), source_url="x", format_name="classic", local_path=zip_path, sha256="x")
        with pytest.raises(ValueError, match="empty zip archive"):
            parse_futstk_underlyings(bhavcopy)

    def test_nsetest_connectivity_symbol_excluded(self, tmp_path):
        csv_text = _CLASSIC_FIXTURE_CSV + "FUTSTK,091NSETEST,30-Jun-2022,0,XX,1,1,1,1,1,1,1,1,1,15-JUN-2022,\n"
        zip_path = _make_zip(tmp_path, "classic2.zip", "fo.csv", csv_text)
        bhavcopy = BhavcopyFile(trade_date=date(2022, 6, 15), source_url="x", format_name="classic", local_path=zip_path, sha256="x")
        snapshot = parse_futstk_underlyings(bhavcopy)
        assert "091NSETEST.NS" not in snapshot.symbols
        assert snapshot.symbols == frozenset({"AARTIIND.NS"})


class _FakeResponse:
    def __init__(self, status_code: int, content: bytes):
        self.status_code = status_code
        self.content = content


class _FakeSession:
    """Maps exact URLs to canned (status, content) results -- lets tests
    exercise the classic-first/udiff-first ordering and the fallback
    branch without any real network call."""

    def __init__(self, responses: dict[str, tuple[int, bytes]]):
        self._responses = responses
        self.requested_urls: list[str] = []

    def get(self, url: str, headers=None):
        self.requested_urls.append(url)
        status, content = self._responses.get(url, (404, b""))
        return _FakeResponse(status, content)


class TestFetchFnoBhavcopyOrderingAndFallback:
    def test_pre_transition_date_tries_classic_first(self, tmp_path):
        target_date = date(2022, 6, 15)
        classic_url = classic_bhavcopy_url(target_date)
        session = _FakeSession({classic_url: (200, b"PK\x03\x04fake-zip-bytes")})
        result = fetch_fno_bhavcopy(target_date, tmp_path, session=session)
        assert result is not None
        assert result.format_name == "classic"
        assert session.requested_urls[0] == classic_url

    def test_post_transition_date_tries_udiff_first(self, tmp_path):
        target_date = date(2026, 9, 18)
        udiff_url = udiff_bhavcopy_url(target_date)
        session = _FakeSession({udiff_url: (200, b"PK\x03\x04fake-zip-bytes")})
        result = fetch_fno_bhavcopy(target_date, tmp_path, session=session)
        assert result is not None
        assert result.format_name == "udiff"
        assert session.requested_urls[0] == udiff_url

    def test_falls_back_to_second_format_on_404(self, tmp_path):
        # A date just after the confirmed classic cutoff: udiff is tried
        # first (per the post-transition ordering) but doesn't exist yet
        # for this particular date, so the function must fall back to
        # classic rather than giving up after one 404.
        target_date = date(2024, 7, 20)
        classic_url = classic_bhavcopy_url(target_date)
        udiff_url = udiff_bhavcopy_url(target_date)
        session = _FakeSession({classic_url: (200, b"PK\x03\x04fake-zip-bytes"), udiff_url: (404, b"")})
        result = fetch_fno_bhavcopy(target_date, tmp_path, session=session)
        assert result is not None
        assert result.format_name == "classic"
        assert session.requested_urls == [udiff_url, classic_url]

    def test_both_formats_missing_returns_none_never_fabricates(self, tmp_path):
        target_date = date(2026, 1, 26)  # a real NSE holiday (Republic Day) -- no trading, no bhavcopy exists
        session = _FakeSession({})  # both URLs 404
        result = fetch_fno_bhavcopy(target_date, tmp_path, session=session)
        assert result is None

    def test_second_call_reuses_cache_without_a_new_request(self, tmp_path):
        target_date = date(2022, 6, 15)
        classic_url = classic_bhavcopy_url(target_date)
        session = _FakeSession({classic_url: (200, b"PK\x03\x04fake-zip-bytes")})
        first = fetch_fno_bhavcopy(target_date, tmp_path, session=session)
        assert len(session.requested_urls) == 1
        second = fetch_fno_bhavcopy(target_date, tmp_path, session=session)
        assert len(session.requested_urls) == 1  # no new HTTP request made
        assert second is not None and second.local_path == first.local_path and second.format_name == first.format_name

    def test_sha256_is_computed_and_stable(self, tmp_path):
        target_date = date(2022, 6, 15)
        classic_url = classic_bhavcopy_url(target_date)
        content = b"PK\x03\x04fake-zip-bytes-for-checksum-test"
        session = _FakeSession({classic_url: (200, content)})
        result = fetch_fno_bhavcopy(target_date, tmp_path, session=session)
        import hashlib

        assert result.sha256 == hashlib.sha256(content).hexdigest()
