import pytest

from market_data.universe import MarketUniverse, UnsupportedUniverseModeError


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
