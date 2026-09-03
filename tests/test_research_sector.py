import pytest

from research.errors import ResearchDataError
from research.models import SectorInfo
from research.sector import YahooSectorInfoProvider, build_sector_map


def _install_fake_ticker(monkeypatch, *, info_by_symbol=None, raise_by_symbol=None):
    import yfinance

    info_by_symbol = info_by_symbol or {}
    raise_by_symbol = raise_by_symbol or {}

    class _FakeTicker:
        def __init__(self, symbol):
            if symbol in raise_by_symbol:
                raise raise_by_symbol[symbol]
            self.info = info_by_symbol.get(symbol, {})

    monkeypatch.setattr(yfinance, "Ticker", _FakeTicker)


def test_fetch_sector_info_returns_real_shaped_fields(monkeypatch):
    _install_fake_ticker(monkeypatch, info_by_symbol={"AAPL": {"sector": "Technology", "industry": "Consumer Electronics"}})

    info = YahooSectorInfoProvider().fetch_sector_info("AAPL")

    assert isinstance(info, SectorInfo)
    assert info.symbol == "AAPL"
    assert info.sector == "Technology"
    assert info.industry == "Consumer Electronics"


def test_fetch_sector_info_treats_missing_fields_as_none(monkeypatch):
    _install_fake_ticker(monkeypatch, info_by_symbol={"AAPL": {}})

    info = YahooSectorInfoProvider().fetch_sector_info("AAPL")

    assert info.sector is None
    assert info.industry is None


def test_fetch_sector_info_normalizes_symbol_case(monkeypatch):
    _install_fake_ticker(monkeypatch, info_by_symbol={"AAPL": {"sector": "Technology"}})

    info = YahooSectorInfoProvider().fetch_sector_info("aapl")

    assert info.symbol == "AAPL"


def test_fetch_sector_info_raises_research_data_error_on_failure(monkeypatch):
    _install_fake_ticker(monkeypatch, raise_by_symbol={"AAPL": RuntimeError("simulated outage")})

    with pytest.raises(ResearchDataError):
        YahooSectorInfoProvider().fetch_sector_info("AAPL")


def test_fetch_sector_info_rejects_an_empty_symbol():
    with pytest.raises(ResearchDataError):
        YahooSectorInfoProvider().fetch_sector_info("  ")


def test_build_sector_map_includes_only_symbols_with_a_real_sector(monkeypatch):
    _install_fake_ticker(
        monkeypatch,
        info_by_symbol={
            "AAPL": {"sector": "Technology"},
            "JPM": {"sector": "Financial Services"},
            "UNKNOWN": {},
        },
    )

    result = build_sector_map(["AAPL", "JPM", "UNKNOWN"], YahooSectorInfoProvider())

    assert result == {"AAPL": "Technology", "JPM": "Financial Services"}


def test_build_sector_map_skips_a_symbol_whose_lookup_fails(monkeypatch):
    _install_fake_ticker(
        monkeypatch,
        info_by_symbol={"AAPL": {"sector": "Technology"}},
        raise_by_symbol={"BAD": RuntimeError("simulated outage")},
    )

    result = build_sector_map(["AAPL", "BAD"], YahooSectorInfoProvider())

    assert result == {"AAPL": "Technology"}


def test_build_sector_map_returns_empty_for_no_symbols(monkeypatch):
    _install_fake_ticker(monkeypatch)
    assert build_sector_map([], YahooSectorInfoProvider()) == {}
