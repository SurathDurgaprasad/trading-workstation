import io

import pandas as pd
import pytest

from live.dhan.instruments import DhanInstrumentMap
from market_data.universe import (
    InstrumentMetadata,
    MarketUniverse,
    UnsupportedUniverseModeError,
    exchange_for_symbol,
    instrument_metadata_for,
)

_FIXTURE_CSV = """SEM_EXM_EXCH_ID,SEM_SEGMENT,SEM_SMST_SECURITY_ID,SEM_INSTRUMENT_NAME,SEM_EXPIRY_CODE,SEM_TRADING_SYMBOL,SEM_LOT_UNITS,SEM_CUSTOM_SYMBOL,SEM_EXPIRY_DATE,SEM_STRIKE_PRICE,SEM_OPTION_TYPE,SEM_TICK_SIZE,SEM_EXPIRY_FLAG,SEM_EXCH_INSTRUMENT_TYPE,SEM_SERIES,SM_SYMBOL_NAME
NSE,E,2885,EQUITY,0,RELIANCE,1.0,Reliance Industries,,,,10.0000,NA,ES,EQ,RELIANCE INDUSTRIES LTD
NSE,E,1333,EQUITY,0,HDFCBANK,1.0,HDFC Bank,,,,10.0000,NA,ES,EQ,HDFC BANK LTD
"""


@pytest.fixture
def instrument_map() -> DhanInstrumentMap:
    return DhanInstrumentMap(pd.read_csv(io.StringIO(_FIXTURE_CSV), dtype=str, keep_default_na=False))


def test_from_watchlist():
    universe = MarketUniverse.from_watchlist(["RELIANCE", "TCS", "INFY"])
    assert universe.mode == "watchlist"
    assert universe.symbols == ("RELIANCE", "TCS", "INFY")
    assert len(universe) == 3
    assert "TCS" in universe
    assert "HDFCBANK" not in universe


def test_from_watchlist_rejects_empty_list():
    with pytest.raises(ValueError):
        MarketUniverse.from_watchlist([])


def test_from_watchlist_deduplicates_preserving_first_occurrence_order():
    """Phase 18 audit fix: a duplicate entry must not inflate len(universe)
    or cause UnifiedMarketDataFacade.get_market_snapshot() to redundantly
    re-fetch the same instrument."""
    universe = MarketUniverse.from_watchlist(["RELIANCE", "TCS", "RELIANCE", "INFY", "TCS"])
    assert universe.symbols == ("RELIANCE", "TCS", "INFY")
    assert len(universe) == 3


def test_from_watchlist_normalizes_case_and_whitespace():
    """Phase 18 audit fix: matches market.data_provider.YahooFinanceProvider's
    own internal symbol.strip().upper() normalization, so a universe entry
    and the adapter that fetches it never silently disagree on casing."""
    universe = MarketUniverse.from_watchlist([" reliance ", "Tcs", "INFY"])
    assert universe.symbols == ("RELIANCE", "TCS", "INFY")


def test_from_watchlist_case_and_duplicate_normalization_combine():
    universe = MarketUniverse.from_watchlist(["reliance", "RELIANCE", " Reliance "])
    assert universe.symbols == ("RELIANCE",)


def test_from_watchlist_rejects_a_blank_symbol():
    with pytest.raises(ValueError, match="empty/blank"):
        MarketUniverse.from_watchlist(["RELIANCE", "   "])


def test_contains_normalizes_the_query_symbol():
    universe = MarketUniverse.from_watchlist(["RELIANCE"])
    assert "reliance" in universe
    assert " RELIANCE " in universe


def test_from_config_watchlist_mode():
    universe = MarketUniverse.from_config({"mode": "watchlist", "symbols": ["RELIANCE", "TCS"]})
    assert universe.symbols == ("RELIANCE", "TCS")


def test_from_config_rejects_a_known_future_mode_with_a_clear_message():
    """nifty50/100/200/500 are documented, deliberately unimplemented --
    must fail with a specific, actionable error, never silently succeed
    with an empty or fabricated universe."""
    with pytest.raises(UnsupportedUniverseModeError, match="not implemented yet"):
        MarketUniverse.from_config({"mode": "nifty50"})


def test_from_config_rejects_an_unknown_mode():
    with pytest.raises(UnsupportedUniverseModeError, match="Unknown universe mode"):
        MarketUniverse.from_config({"mode": "totally_made_up"})


def test_from_yaml_file(tmp_path):
    config_path = tmp_path / "universe.yaml"
    config_path.write_text(
        "market_universe:\n"
        "  mode: watchlist\n"
        "  symbols:\n"
        "    - RELIANCE\n"
        "    - TCS\n"
        "    - INFY\n"
        "    - HDFCBANK\n"
    )
    universe = MarketUniverse.from_yaml_file(config_path)
    assert universe.mode == "watchlist"
    assert universe.symbols == ("RELIANCE", "TCS", "INFY", "HDFCBANK")


def test_from_yaml_file_missing_top_level_key(tmp_path):
    config_path = tmp_path / "bad.yaml"
    config_path.write_text("something_else:\n  foo: bar\n")
    with pytest.raises(ValueError, match="market_universe"):
        MarketUniverse.from_yaml_file(config_path)


def test_universe_is_frozen_and_reproducible():
    a = MarketUniverse.from_watchlist(["RELIANCE", "TCS"])
    b = MarketUniverse.from_watchlist(["RELIANCE", "TCS"])
    assert a == b
    with pytest.raises(AttributeError):
        a.symbols = ("X",)  # frozen dataclass -- no accidental mutation


# --- Phase 29: validation, exchange metadata, instrument enrichment ------------


def test_from_watchlist_rejects_a_comma_joined_symbol_with_a_clear_message():
    """A common paste/typo error: "AAPL,MSFT" passed as ONE list element
    instead of being split first. Must fail here with an actionable
    message, not silently produce a bogus symbol that only fails much
    later, opaquely, at the Yahoo fetch stage."""
    with pytest.raises(ValueError, match="comma or internal whitespace"):
        MarketUniverse.from_watchlist(["AAPL,MSFT"])


def test_from_watchlist_rejects_internal_whitespace():
    with pytest.raises(ValueError, match="comma or internal whitespace"):
        MarketUniverse.from_watchlist(["RELIANCE NS"])


def test_from_watchlist_still_accepts_leading_trailing_whitespace():
    """Leading/trailing whitespace is a normal, already-handled case
    (stripped before the internal-whitespace check runs) -- must not
    regress into being rejected."""
    universe = MarketUniverse.from_watchlist([" RELIANCE "])
    assert universe.symbols == ("RELIANCE",)


@pytest.mark.parametrize("symbol,expected", [
    ("RELIANCE.NS", "NSE"),
    ("reliance.ns", "NSE"),
    ("TCS.BO", "BSE"),
    ("tcs.bo", "BSE"),
    ("AAPL", "OTHER"),
    ("^NSEI", "OTHER"),
    ("RELIANCE", "OTHER"),  # no suffix at all -- not assumed NSE
])
def test_exchange_for_symbol(symbol, expected):
    assert exchange_for_symbol(symbol) == expected


def test_instrument_metadata_for_without_a_map_leaves_dhan_fields_none():
    metadata = instrument_metadata_for("RELIANCE.NS")
    assert metadata == InstrumentMetadata(symbol="RELIANCE.NS", exchange="NSE", dhan_security_id=None, dhan_display_name=None)


def test_instrument_metadata_for_resolves_a_known_symbol(instrument_map):
    metadata = instrument_metadata_for("RELIANCE.NS", instrument_map=instrument_map)
    assert metadata.exchange == "NSE"
    assert metadata.dhan_security_id == "2885"
    assert metadata.dhan_display_name == "Reliance Industries"


def test_instrument_metadata_for_never_raises_for_an_unresolved_symbol(instrument_map):
    """Enrichment is best-effort and must never block -- same posture as
    every other optional-enrichment step in this project (AI summaries,
    AI narratives, sector maps)."""
    metadata = instrument_metadata_for("UNKNOWNTICKER.NS", instrument_map=instrument_map)
    assert metadata.dhan_security_id is None
    assert metadata.dhan_display_name is None


def test_instrument_metadata_for_a_non_indian_symbol_never_attempts_a_dhan_lookup(instrument_map):
    """AAPL has no .NS/.BO suffix -- DhanInstrumentMap.lookup_yahoo_symbol
    would raise for it; metadata_for must catch that internally and
    return a clean 'not found' result, not propagate."""
    metadata = instrument_metadata_for("AAPL", instrument_map=instrument_map)
    assert metadata.exchange == "OTHER"
    assert metadata.dhan_security_id is None


def test_describe_returns_metadata_for_every_symbol_in_order(instrument_map):
    universe = MarketUniverse.from_watchlist(["RELIANCE.NS", "AAPL", "HDFCBANK.NS"])
    described = universe.describe(instrument_map=instrument_map)

    assert len(described) == 3
    assert described[0].symbol == "RELIANCE.NS" and described[0].dhan_security_id == "2885"
    assert described[1].symbol == "AAPL" and described[1].exchange == "OTHER"
    assert described[2].symbol == "HDFCBANK.NS" and described[2].dhan_security_id == "1333"


def test_describe_without_a_map_still_returns_exchange_metadata():
    universe = MarketUniverse.from_watchlist(["RELIANCE.NS", "AAPL"])
    described = universe.describe()
    assert [m.exchange for m in described] == ["NSE", "OTHER"]
    assert all(m.dhan_security_id is None for m in described)


def test_starter_nse_watchlist_file_loads_and_is_all_nse():
    """The committed starter watchlist (market_data/watchlists/
    starter_nse.yaml) must actually load via the existing from_yaml_file
    path and every symbol must resolve to NSE -- a real, load-bearing
    regression test for a file operators are expected to use directly."""
    from pathlib import Path

    from core.config import PROJECT_ROOT

    path = PROJECT_ROOT / "market_data" / "watchlists" / "starter_nse.yaml"
    assert Path(path).exists()

    universe = MarketUniverse.from_yaml_file(path)
    assert universe.mode == "watchlist"
    assert len(universe) >= 10  # bounded, not blind hundreds -- but a real, useful starting set
    for symbol in universe.symbols:
        assert exchange_for_symbol(symbol) == "NSE", f"{symbol} in the starter watchlist is not an NSE (.NS) symbol"
