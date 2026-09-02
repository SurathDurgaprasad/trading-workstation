"""Phase 15 §23 unit tests: Dhan instrument (symbol) mapping. The small
fixture tests run fully offline; the "real CSV" tests download Dhan's
actual public instrument master (no auth needed, it's a static file) and
skip cleanly if that download isn't reachable -- mirroring the
AAPL_CACHE_PATH skip pattern already used throughout this project for
real-data-dependent tests.
"""
import io

import pandas as pd
import pytest

from live.dhan.instruments import DEFAULT_INSTRUMENT_CACHE_PATH, DhanInstrumentMap, InstrumentNotFoundError

_FIXTURE_CSV = """SEM_EXM_EXCH_ID,SEM_SEGMENT,SEM_SMST_SECURITY_ID,SEM_INSTRUMENT_NAME,SEM_EXPIRY_CODE,SEM_TRADING_SYMBOL,SEM_LOT_UNITS,SEM_CUSTOM_SYMBOL,SEM_EXPIRY_DATE,SEM_STRIKE_PRICE,SEM_OPTION_TYPE,SEM_TICK_SIZE,SEM_EXPIRY_FLAG,SEM_EXCH_INSTRUMENT_TYPE,SEM_SERIES,SM_SYMBOL_NAME
NSE,E,2885,EQUITY,0,RELIANCE,1.0,Reliance Industries,,,,10.0000,NA,ES,EQ,RELIANCE INDUSTRIES LTD
BSE,E,500325,EQUITY,0,RELIANCE,1.0,Reliance Industries,,,,0.0500,NA,ES,A,RELIANCE INDUSTRIES LTD
NSE,D,49081,FUTSTK,0,RELIANCE,500.0,RELIANCE FUT,2026-09-25,,,10.0000,NA,FUTSTK,,RELIANCE INDUSTRIES LTD
NSE,E,1333,EQUITY,0,HDFCBANK,1.0,HDFC Bank,,,,10.0000,NA,ES,EQ,HDFC BANK LTD
"""


@pytest.fixture
def instrument_map() -> DhanInstrumentMap:
    return DhanInstrumentMap(pd.read_csv(io.StringIO(_FIXTURE_CSV), dtype=str, keep_default_na=False))


def test_lookup_nse_equity(instrument_map):
    instrument = instrument_map.lookup(trading_symbol="RELIANCE", exchange="NSE", segment="E")
    assert instrument.security_id == "2885"
    assert instrument.exchange_segment == "NSE_EQ"
    assert instrument.trading_symbol == "RELIANCE"


def test_lookup_bse_equity_is_a_different_security_id(instrument_map):
    instrument = instrument_map.lookup(trading_symbol="RELIANCE", exchange="BSE", segment="E")
    assert instrument.security_id == "500325"
    assert instrument.exchange_segment == "BSE_EQ"


def test_lookup_does_not_confuse_equity_with_futures(instrument_map):
    """Same trading_symbol, same exchange, different segment -- the
    equity lookup must never accidentally return the futures contract's
    security ID."""
    equity = instrument_map.lookup(trading_symbol="RELIANCE", exchange="NSE", segment="E")
    futures = instrument_map.lookup(trading_symbol="RELIANCE", exchange="NSE", segment="D")
    assert equity.security_id != futures.security_id
    assert equity.exchange_segment == "NSE_EQ"
    assert futures.exchange_segment == "NSE_FNO"


def test_lookup_yahoo_symbol_ns_suffix_maps_to_nse(instrument_map):
    instrument = instrument_map.lookup_yahoo_symbol("RELIANCE.NS")
    assert instrument.security_id == "2885"
    assert instrument.exchange_segment == "NSE_EQ"


def test_lookup_yahoo_symbol_bo_suffix_maps_to_bse(instrument_map):
    instrument = instrument_map.lookup_yahoo_symbol("RELIANCE.BO")
    assert instrument.security_id == "500325"
    assert instrument.exchange_segment == "BSE_EQ"


def test_lookup_yahoo_symbol_never_uses_the_yahoo_symbol_as_a_broker_id(instrument_map):
    """The whole point of this module: "RELIANCE.NS" itself must never
    leak through as if it were a Dhan security ID."""
    instrument = instrument_map.lookup_yahoo_symbol("RELIANCE.NS")
    assert instrument.security_id != "RELIANCE.NS"
    assert instrument.security_id.isdigit()


def test_lookup_yahoo_symbol_without_a_recognized_suffix_raises():
    empty_map = DhanInstrumentMap(pd.read_csv(io.StringIO(_FIXTURE_CSV), dtype=str, keep_default_na=False))
    with pytest.raises(InstrumentNotFoundError):
        empty_map.lookup_yahoo_symbol("RELIANCE")  # no .NS/.BO suffix


def test_lookup_unknown_symbol_raises_not_found(instrument_map):
    with pytest.raises(InstrumentNotFoundError):
        instrument_map.lookup(trading_symbol="NOSUCHSYMBOL", exchange="NSE", segment="E")


def test_lookup_is_deterministic(instrument_map):
    first = instrument_map.lookup(trading_symbol="RELIANCE", exchange="NSE", segment="E")
    second = instrument_map.lookup(trading_symbol="RELIANCE", exchange="NSE", segment="E")
    assert first == second


# --- against the real, public, unauthenticated Dhan instrument master -------
# Uses DhanInstrumentMap's own default cache path (data/dhan/scrip-master.csv,
# .gitignore'd) -- populated by calling DhanInstrumentMap.download() once;
# skips cleanly if that hasn't been done, exactly like AAPL_CACHE_PATH-gated
# tests elsewhere in this project skip when the real-data cache is absent.


@pytest.mark.skipif(not DEFAULT_INSTRUMENT_CACHE_PATH.exists(), reason=f"No cached Dhan instrument master at {DEFAULT_INSTRUMENT_CACHE_PATH}")
def test_real_instrument_master_maps_reliance_ns_correctly():
    """Regression check against Dhan's actual live instrument master --
    proves the fixture above matches production reality, not just an
    invented shape. Confirmed once during Phase 15 research: NSE
    RELIANCE.NS -> Security ID 2885."""
    real_map = DhanInstrumentMap.from_csv(DEFAULT_INSTRUMENT_CACHE_PATH)
    instrument = real_map.lookup_yahoo_symbol("RELIANCE.NS")
    assert instrument.security_id == "2885"
    assert instrument.exchange_segment == "NSE_EQ"
