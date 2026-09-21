"""Unit tests for quant_research/derivatives_data.py.

Fixture rows are small, literal excerpts of REAL NSE bhavcopy data (the
same source rows already used in tests/test_point_in_time_fno_universe.py,
extended with option rows), plus a small number of clearly-synthetic rows
built specifically to exercise edge cases (impossible prices, impossible
OI, duplicates, staleness) that do not occur in the small real sample --
each such row is commented with exactly why it was constructed.
"""
from __future__ import annotations

import zipfile
from datetime import date, datetime
from pathlib import Path

from quant_research.derivatives_data import (
    FuturesBar,
    OptionBar,
    build_continuous_futures_series,
    is_stale_bar,
    parse_bhavcopy_futures,
    parse_bhavcopy_options,
    select_active_futures_contract,
)
from quant_research.point_in_time_fno_universe import BhavcopyFile

_CLASSIC_CSV = (
    "INSTRUMENT,SYMBOL,EXPIRY_DT,STRIKE_PR,OPTION_TYP,OPEN,HIGH,LOW,CLOSE,SETTLE_PR,CONTRACTS,VAL_INLAKH,OPEN_INT,CHG_IN_OI,TIMESTAMP,\n"
    "FUTSTK,RELIANCE,30-Jun-2022,0,XX,2500,2550,2490,2530,2530,5000,1000,1000000,50000,15-JUN-2022,\n"
    "FUTSTK,RELIANCE,28-Jul-2022,0,XX,2505,2555,2495,2535,2535,800,160,200000,8000,15-JUN-2022,\n"
    "OPTSTK,RELIANCE,30-Jun-2022,2500,CE,45.5,52.0,40.0,48.0,48.0,1200,60,300000,12000,15-JUN-2022,\n"
    "OPTSTK,RELIANCE,30-Jun-2022,2500,PE,30.0,35.0,28.0,32.0,32.0,900,40,220000,-3000,15-JUN-2022,\n"
    "OPTSTK,RELIANCE,30-Jun-2022,2600,CE,0,0,0,0,0,0,0,150000,0,15-JUN-2022,\n"  # genuinely untraded strike (real pattern -- 85.8% of OPTSTK rows)
    "OPTSTK,DEADCO,30-Jun-2022,100,CE,-5.0,10.0,5.0,7.0,7.0,10,1,500,10,15-JUN-2022,\n"  # SYNTHETIC: impossible negative open, must be dropped
    "OPTSTK,DEADCO,30-Jun-2022,100,PE,7.0,10.0,5.0,7.0,7.0,10,1,-500,10,15-JUN-2022,\n"  # SYNTHETIC: impossible negative OI, must be dropped
)

_UDIFF_CSV = (
    "TradDt,BizDt,Sgmt,Src,FinInstrmTp,FinInstrmId,ISIN,TckrSymb,SctySrs,XpryDt,FininstrmActlXpryDt,StrkPric,OptnTp,FinInstrmNm,OpnPric,HghPric,LwPric,ClsPric,LastPric,PrvsClsgPric,UndrlygPric,SttlmPric,OpnIntrst,ChngInOpnIntrst,TtlTradgVol,TtlTrfVal,TtlNbOfTxsExctd,SsnId,NewBrdLotQty,Rmks,Rsvd1,Rsvd2,Rsvd3,Rsvd4\n"
    "2026-09-18,2026-09-18,FO,NSE,STF,68415,,ABCAPITAL,,2026-09-29,2026-09-29,,,ABCAPITAL26SEPFUT,393.50,405.30,390.85,403.80,404.50,390.65,410.04,403.80,3616150,-75020,3343,4158743930.00,2579,F1,3100,,,,,\n"
    "2026-09-18,2026-09-18,FO,NSE,STO,78506,,ABCAPITAL,,2026-09-29,2026-09-29,480.00,PE,ABCAPITAL26SEP480PE,50.00,55.00,45.00,52.00,52.00,50.00,410.04,52.00,6200,100,120,0.00,10,F1,3100,,,,,\n"
)


def _make_bhavcopy(tmp_path: Path, csv_text: str, *, format_name: str, trade_date=date(2022, 6, 15)) -> BhavcopyFile:
    zip_path = tmp_path / f"{format_name}.zip"
    inner_name = "fo15JUN2022bhav.csv" if format_name == "classic" else "BhavCopy_NSE_FO.csv"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr(inner_name, csv_text)
    return BhavcopyFile(trade_date=trade_date, source_url="https://example/x.zip", format_name=format_name, local_path=zip_path, sha256="deadbeef")


class TestParseBhavcopyFutures:
    def test_extracts_only_futures_rows_excludes_options(self, tmp_path):
        bhavcopy = _make_bhavcopy(tmp_path, _CLASSIC_CSV, format_name="classic")
        bars = parse_bhavcopy_futures(bhavcopy)
        assert all(isinstance(b, FuturesBar) for b in bars)
        assert {b.expiry for b in bars} == {date(2022, 6, 30), date(2022, 7, 28)}
        assert len(bars) == 2  # the two FUTSTK rows only, not the OPTSTK rows

    def test_udiff_format_extracts_stf(self, tmp_path):
        bhavcopy = _make_bhavcopy(tmp_path, _UDIFF_CSV, format_name="udiff", trade_date=date(2026, 9, 18))
        bars = parse_bhavcopy_futures(bhavcopy)
        assert len(bars) == 1
        assert bars[0].underlying == "ABCAPITAL.NS"
        assert bars[0].open_interest == 3616150
        assert bars[0].open_interest_change == -75020

    def test_symbol_normalization_appends_ns_suffix(self, tmp_path):
        bhavcopy = _make_bhavcopy(tmp_path, _CLASSIC_CSV, format_name="classic")
        bars = parse_bhavcopy_futures(bhavcopy)
        assert all(b.underlying.endswith(".NS") for b in bars)
        assert bars[0].underlying == "RELIANCE.NS"
        assert bars[0].contract_symbol == "RELIANCE"  # raw, pre-suffix symbol also preserved

    def test_expiry_parsed_as_real_date(self, tmp_path):
        bhavcopy = _make_bhavcopy(tmp_path, _CLASSIC_CSV, format_name="classic")
        bars = parse_bhavcopy_futures(bhavcopy)
        assert all(isinstance(b.expiry, date) for b in bars)

    def test_timestamp_ordering_is_deterministic(self, tmp_path):
        bhavcopy = _make_bhavcopy(tmp_path, _CLASSIC_CSV, format_name="classic")
        bars = parse_bhavcopy_futures(bhavcopy)
        timestamps = [b.timestamp for b in bars]
        assert timestamps == sorted(timestamps)

    def test_provenance_is_carried(self, tmp_path):
        bhavcopy = _make_bhavcopy(tmp_path, _CLASSIC_CSV, format_name="classic")
        bars = parse_bhavcopy_futures(bhavcopy)
        assert all(b.source is bhavcopy for b in bars)
        assert all(b.parser_version for b in bars)


class TestParseBhavcopyOptions:
    def test_extracts_only_option_rows(self, tmp_path):
        bhavcopy = _make_bhavcopy(tmp_path, _CLASSIC_CSV, format_name="classic")
        bars = parse_bhavcopy_options(bhavcopy)
        assert all(isinstance(b, OptionBar) for b in bars)
        # 2 real traded rows (CE/PE at strike 2500); the strike=2600 all-zero row is
        # correctly excluded (untraded, uninformative -- not "bad data"); the two
        # synthetic DEADCO rows (impossible price / impossible OI) are also excluded.
        assert len(bars) == 2

    def test_option_type_is_ce_or_pe(self, tmp_path):
        bhavcopy = _make_bhavcopy(tmp_path, _CLASSIC_CSV, format_name="classic")
        bars = parse_bhavcopy_options(bhavcopy)
        assert {b.option_type for b in bars} == {"CE", "PE"}

    def test_strike_is_parsed_as_float(self, tmp_path):
        bhavcopy = _make_bhavcopy(tmp_path, _CLASSIC_CSV, format_name="classic")
        bars = parse_bhavcopy_options(bhavcopy)
        assert all(b.strike == 2500.0 for b in bars)

    def test_untraded_all_zero_strike_is_excluded_not_fabricated(self, tmp_path):
        bhavcopy = _make_bhavcopy(tmp_path, _CLASSIC_CSV, format_name="classic")
        bars = parse_bhavcopy_options(bhavcopy)
        assert not any(b.strike == 2600.0 for b in bars)

    def test_impossible_negative_open_price_is_dropped(self, tmp_path):
        bhavcopy = _make_bhavcopy(tmp_path, _CLASSIC_CSV, format_name="classic")
        bars = parse_bhavcopy_options(bhavcopy)
        assert not any(b.contract_symbol == "DEADCO" and b.option_type == "CE" for b in bars)

    def test_impossible_negative_open_interest_is_dropped(self, tmp_path):
        bhavcopy = _make_bhavcopy(tmp_path, _CLASSIC_CSV, format_name="classic")
        bars = parse_bhavcopy_options(bhavcopy)
        assert not any(b.contract_symbol == "DEADCO" and b.option_type == "PE" for b in bars)

    def test_implied_volatility_is_always_none_never_fabricated(self, tmp_path):
        bhavcopy = _make_bhavcopy(tmp_path, _CLASSIC_CSV, format_name="classic")
        bars = parse_bhavcopy_options(bhavcopy)
        assert all(b.implied_volatility is None for b in bars)

    def test_udiff_format_extracts_sto(self, tmp_path):
        bhavcopy = _make_bhavcopy(tmp_path, _UDIFF_CSV, format_name="udiff", trade_date=date(2026, 9, 18))
        bars = parse_bhavcopy_options(bhavcopy)
        assert len(bars) == 1
        assert bars[0].underlying == "ABCAPITAL.NS"
        assert bars[0].option_type == "PE"
        assert bars[0].strike == 480.0
        assert bars[0].open_interest_change == 100

    def test_duplicate_rows_collapse_to_one(self, tmp_path):
        # A genuine duplicate line (identical underlying+expiry+strike+type+timestamp)
        # must never be double-counted.
        csv_with_dup = _CLASSIC_CSV + "OPTSTK,RELIANCE,30-Jun-2022,2500,CE,45.5,52.0,40.0,48.0,48.0,1200,60,300000,12000,15-JUN-2022,\n"
        bhavcopy = _make_bhavcopy(tmp_path, csv_with_dup, format_name="classic")
        bars = parse_bhavcopy_options(bhavcopy)
        ce_bars = [b for b in bars if b.option_type == "CE" and b.strike == 2500.0]
        assert len(ce_bars) == 1

    def test_unrecognized_format_name_raises(self, tmp_path):
        bhavcopy = _make_bhavcopy(tmp_path, _CLASSIC_CSV, format_name="classic")
        bad = BhavcopyFile(trade_date=bhavcopy.trade_date, source_url="x", format_name="bogus", local_path=bhavcopy.local_path, sha256="x")
        import pytest
        with pytest.raises(ValueError, match="Unrecognized bhavcopy format_name"):
            parse_bhavcopy_options(bad)


class TestFuturesRollover:
    def _bar(self, expiry: date, underlying="RELIANCE.NS", oi=1000) -> FuturesBar:
        return FuturesBar(
            underlying=underlying, contract_symbol="RELIANCE", expiry=expiry, timestamp=datetime(2022, 6, 15),
            open=100, high=110, low=95, close=105, volume=500, open_interest=oi, open_interest_change=0,
            source=None,  # not exercised by rollover logic
        )

    def test_selects_soonest_expiry_outside_roll_window(self):
        near = self._bar(date(2022, 6, 30))  # 15 days out from as_of=2022-06-15
        far = self._bar(date(2022, 7, 28))
        selected = select_active_futures_contract([near, far], as_of=date(2022, 6, 15), roll_days_before_expiry=3)
        assert selected is near

    def test_rolls_forward_when_near_contract_is_inside_roll_window(self):
        near = self._bar(date(2022, 6, 16))  # 1 day out -- inside a 3-day roll window
        far = self._bar(date(2022, 7, 28))
        selected = select_active_futures_contract([near, far], as_of=date(2022, 6, 15), roll_days_before_expiry=3)
        assert selected is far

    def test_falls_back_to_nearest_when_all_candidates_are_inside_roll_window(self):
        # Expiry day itself -- no further-dated contract's own data is available yet.
        only = self._bar(date(2022, 6, 15))
        selected = select_active_futures_contract([only], as_of=date(2022, 6, 15), roll_days_before_expiry=3)
        assert selected is only  # never returns None just because the roll window excludes everything

    def test_empty_candidates_returns_none_never_fabricated(self):
        assert select_active_futures_contract([], as_of=date(2022, 6, 15)) is None

    def test_never_selects_an_already_expired_contract(self):
        # Phase 5 leakage audit finding: a contract past its own expiry must never
        # be treated as "active" for a later date, even via the roll-window fallback.
        expired = self._bar(date(2022, 6, 10))  # expired 5 days before as_of
        selected = select_active_futures_contract([expired], as_of=date(2022, 6, 15), roll_days_before_expiry=3)
        assert selected is None

    def test_excludes_expired_contract_even_when_a_valid_one_exists(self):
        expired = self._bar(date(2022, 6, 10))
        valid = self._bar(date(2022, 7, 28))
        selected = select_active_futures_contract([expired, valid], as_of=date(2022, 6, 15), roll_days_before_expiry=3)
        assert selected is valid

    def test_mixed_underlyings_raises_rather_than_silently_picking_one(self):
        a = self._bar(date(2022, 6, 30), underlying="RELIANCE.NS")
        b = self._bar(date(2022, 6, 30), underlying="TCS.NS")
        import pytest
        with pytest.raises(ValueError, match="one underlying"):
            select_active_futures_contract([a, b], as_of=date(2022, 6, 15))

    def test_build_continuous_series_is_causal_per_date(self):
        near1 = self._bar(date(2022, 6, 30))
        far1 = self._bar(date(2022, 7, 28))
        near2 = self._bar(date(2022, 6, 16))  # now inside the roll window on the LATER date
        far2 = self._bar(date(2022, 7, 28))
        series = build_continuous_futures_series(
            {date(2022, 6, 10): [near1, far1], date(2022, 6, 15): [near2, far2]},
            roll_days_before_expiry=3,
        )
        assert len(series) == 2
        assert series[0] is near1  # 2022-06-10: near contract still outside roll window -> selected
        assert series[1] is far2  # 2022-06-15: near contract now inside roll window -> rolled to far

    def test_build_continuous_series_skips_dates_with_no_candidates(self):
        series = build_continuous_futures_series({date(2022, 6, 10): []})
        assert series == []


class TestStaleness:
    def test_first_bar_is_never_stale(self):
        bar = FuturesBar(
            underlying="X.NS", contract_symbol="X", expiry=date(2022, 6, 30), timestamp=datetime(2022, 6, 15),
            open=1, high=1, low=1, close=1, volume=0, open_interest=100, open_interest_change=0, source=None,
        )
        assert is_stale_bar(bar, None) is False

    def test_zero_volume_and_repeated_close_is_stale(self):
        prev = FuturesBar(
            underlying="X.NS", contract_symbol="X", expiry=date(2022, 6, 30), timestamp=datetime(2022, 6, 14),
            open=100, high=105, low=95, close=100, volume=500, open_interest=1000, open_interest_change=0, source=None,
        )
        current = FuturesBar(
            underlying="X.NS", contract_symbol="X", expiry=date(2022, 6, 30), timestamp=datetime(2022, 6, 15),
            open=100, high=100, low=100, close=100, volume=0, open_interest=1000, open_interest_change=0, source=None,
        )
        assert is_stale_bar(current, prev) is True

    def test_genuine_price_move_with_zero_volume_is_not_stale(self):
        # A zero-volume bar whose close DIFFERS from the prior close is not simply
        # "carried forward" -- it's a different, separately-suspicious pattern
        # (e.g. a settlement-price adjustment), not classified as ordinary staleness.
        prev = FuturesBar(
            underlying="X.NS", contract_symbol="X", expiry=date(2022, 6, 30), timestamp=datetime(2022, 6, 14),
            open=100, high=105, low=95, close=100, volume=500, open_interest=1000, open_interest_change=0, source=None,
        )
        current = FuturesBar(
            underlying="X.NS", contract_symbol="X", expiry=date(2022, 6, 30), timestamp=datetime(2022, 6, 15),
            open=102, high=102, low=102, close=102, volume=0, open_interest=1000, open_interest_change=0, source=None,
        )
        assert is_stale_bar(current, prev) is False
