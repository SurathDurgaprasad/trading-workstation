"""H_XSECT_006: tests for quant_research/universe_expansion.py -- the
frozen ORIGINAL/EXPANDED-ONLY/COMBINED universe groups the H_XSECT_006
pre-registration (docs/research/
H_XSECT_006_UNIVERSE_WIDENING_PREREGISTRATION.md) defines."""

import io

import pandas as pd
import pytest

from live.dhan.instruments import DhanInstrumentMap
from quant_research.universe_expansion import ORIGINAL_32_NSE_UNIVERSE, build_universe_groups

_FIXTURE_CSV = """SEM_EXM_EXCH_ID,SEM_SEGMENT,SEM_SMST_SECURITY_ID,SEM_INSTRUMENT_NAME,SEM_EXPIRY_CODE,SEM_TRADING_SYMBOL,SEM_LOT_UNITS,SEM_CUSTOM_SYMBOL,SEM_EXPIRY_DATE,SEM_STRIKE_PRICE,SEM_OPTION_TYPE,SEM_TICK_SIZE,SEM_EXPIRY_FLAG,SEM_EXCH_INSTRUMENT_TYPE,SEM_SERIES,SM_SYMBOL_NAME
NSE,E,2885,EQUITY,0,RELIANCE,1.0,Reliance Industries,,,,10.0000,NA,ES,EQ,RELIANCE INDUSTRIES LTD
NSE,D,49081,FUTSTK,0,RELIANCE,500.0,RELIANCE FUT,2026-09-25,,,10.0000,NA,FUTSTK,,RELIANCE INDUSTRIES LTD
NSE,E,9999,EQUITY,0,NEWSTOCK,1.0,New Stock,,,,10.0000,NA,ES,EQ,NEW STOCK LTD
NSE,D,88881,FUTSTK,0,NEWSTOCK,500.0,NEWSTOCK FUT,2026-09-25,,,10.0000,NA,FUTSTK,,NEW STOCK LTD
NSE,E,7777,EQUITY,0,ILLIQUIDCO,1.0,Illiquid Co,,,,10.0000,NA,ES,EQ,ILLIQUID CO LTD
"""


@pytest.fixture
def instrument_map() -> DhanInstrumentMap:
    return DhanInstrumentMap(pd.read_csv(io.StringIO(_FIXTURE_CSV), dtype=str, keep_default_na=False))


def test_original_universe_is_exactly_32_symbols():
    assert len(ORIGINAL_32_NSE_UNIVERSE) == 32
    assert len(set(ORIGINAL_32_NSE_UNIVERSE)) == 32  # no duplicates
    assert "RELIANCE.NS" in ORIGINAL_32_NSE_UNIVERSE


def test_build_universe_groups_original_is_unchanged(instrument_map):
    groups = build_universe_groups(instrument_map)
    assert groups["original"] == ORIGINAL_32_NSE_UNIVERSE


def test_build_universe_groups_expanded_only_excludes_original_symbols(instrument_map):
    """RELIANCE.NS is F&O-eligible AND already in ORIGINAL -- must NOT
    appear in expanded_only (that would double-count it and contaminate
    the zero-overlap comparison this experiment depends on)."""
    groups = build_universe_groups(instrument_map)
    assert "RELIANCE.NS" not in groups["expanded_only"]
    assert "NEWSTOCK.NS" in groups["expanded_only"]  # F&O-eligible, not in original


def test_build_universe_groups_excludes_symbols_without_derivatives(instrument_map):
    """ILLIQUIDCO has no FUTSTK row -- must never appear in any group."""
    groups = build_universe_groups(instrument_map)
    assert "ILLIQUIDCO.NS" not in groups["expanded_only"]
    assert "ILLIQUIDCO.NS" not in groups["combined"]


def test_build_universe_groups_combined_is_the_union_with_no_duplicates():
    fixture_with_original = _FIXTURE_CSV + f"NSE,E,1,EQUITY,0,TCS,1.0,TCS,,,,10.0000,NA,ES,EQ,TCS LTD\nNSE,D,2,FUTSTK,0,TCS,500.0,TCS FUT,2026-09-25,,,10.0000,NA,FUTSTK,,TCS LTD\n"
    instrument_map = DhanInstrumentMap(pd.read_csv(io.StringIO(fixture_with_original), dtype=str, keep_default_na=False))
    groups = build_universe_groups(instrument_map)
    assert len(groups["combined"]) == len(set(groups["combined"]))
    assert set(groups["combined"]) == set(groups["original"]) | set(groups["expanded_only"])
    assert "TCS.NS" in groups["combined"]  # both F&O-eligible AND in original -- counted once


def test_build_universe_groups_returns_sorted_tuples_for_reproducibility(instrument_map):
    groups = build_universe_groups(instrument_map)
    assert groups["expanded_only"] == tuple(sorted(groups["expanded_only"]))
    assert groups["combined"] == tuple(sorted(groups["combined"]))
