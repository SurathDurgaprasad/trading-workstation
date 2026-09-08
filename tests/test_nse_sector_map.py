from market_intelligence.nse_sector_map import NSE_SECTOR_MAP, sector_for_symbol
from market_intelligence.regime import NIFTY_SECTOR_INDICES


def test_every_mapped_sector_is_a_real_available_index():
    assert set(NSE_SECTOR_MAP.values()).issubset(set(NIFTY_SECTOR_INDICES.keys()))


def test_sector_for_symbol_is_case_and_whitespace_insensitive():
    assert sector_for_symbol("tcs.ns") == "NIFTY_IT"
    assert sector_for_symbol("  TCS.NS  ") == "NIFTY_IT"


def test_sector_for_symbol_returns_none_for_unmapped_symbol():
    assert sector_for_symbol("RELIANCE.NS") is None
    assert sector_for_symbol("DOES_NOT_EXIST") is None


def test_no_symbol_is_mapped_to_more_than_one_sector():
    assert len(NSE_SECTOR_MAP) == len(set(NSE_SECTOR_MAP.keys()))
