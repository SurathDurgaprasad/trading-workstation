"""market/data_provider.py::YahooFinanceProvider -- direct failure-
injection tests against the real provider class, not just the
downstream OHLCV parsing layer (market_data_validation.py, adapters)
that already had coverage. A provider-failure-matrix survey found this
was a real, previously-untested boundary: `yf.Ticker(...).history()`
raising, or returning an empty frame, was only ever exercised via fake
providers standing in for YahooFinanceProvider, never the real class's
own try/except around the yfinance call itself."""

import pandas as pd
import pytest

from market.data_provider import MarketDataError, YahooFinanceProvider


class _FakeTicker:
    def __init__(self, *, raises: Exception | None = None, frame: pd.DataFrame | None = None):
        self._raises = raises
        self._frame = frame

    def history(self, **kwargs):
        if self._raises is not None:
            raise self._raises
        return self._frame


def test_a_timeout_from_yfinance_is_wrapped_in_a_clear_marketdataerror(monkeypatch):
    """yfinance itself can raise a requests-level timeout (or any other
    transport failure) from deep inside its own HTTP client -- this must
    never propagate as a raw, unrelated exception type; it must become
    the same MarketDataError every other failure in this provider does,
    naming the symbol."""
    import yfinance as yf

    timeout_exc = TimeoutError("Yahoo Finance request timed out after 30s")
    monkeypatch.setattr(yf, "Ticker", lambda symbol: _FakeTicker(raises=timeout_exc))

    with pytest.raises(MarketDataError, match="AAPL"):
        YahooFinanceProvider().fetch_ohlcv("AAPL", period="1y", interval="1d")


def test_a_connection_error_from_yfinance_is_wrapped_the_same_way(monkeypatch):
    import yfinance as yf

    monkeypatch.setattr(yf, "Ticker", lambda symbol: _FakeTicker(raises=ConnectionError("connection refused")))

    with pytest.raises(MarketDataError):
        YahooFinanceProvider().fetch_ohlcv("MSFT", period="1y", interval="1d")


def test_an_empty_dataframe_from_yfinance_raises_marketdataerror_not_a_silent_empty_result(monkeypatch):
    """A symbol that genuinely has no data (delisted, mistyped, or a
    Yahoo-side gap) must be a clear, visible failure at the provider
    boundary -- never silently returned as an empty-but-valid OHLCV a
    caller might mistake for "fetched successfully, just no bars"."""
    import yfinance as yf

    monkeypatch.setattr(yf, "Ticker", lambda symbol: _FakeTicker(frame=pd.DataFrame()))

    with pytest.raises(MarketDataError, match="No Yahoo Finance data returned"):
        YahooFinanceProvider().fetch_ohlcv("DELISTEDCO", period="1y", interval="1d")


def test_a_none_result_from_yfinance_also_raises_marketdataerror(monkeypatch):
    """Defensive: some yfinance versions/edge cases return None rather
    than an empty DataFrame on a genuinely empty result."""
    import yfinance as yf

    monkeypatch.setattr(yf, "Ticker", lambda symbol: _FakeTicker(frame=None))

    with pytest.raises(MarketDataError, match="No Yahoo Finance data returned"):
        YahooFinanceProvider().fetch_ohlcv("AAPL", period="1y", interval="1d")


def test_a_normal_response_still_parses_correctly(monkeypatch):
    """Confirms the mocking approach itself is sound -- a real-shaped
    response still reaches OHLCV.from_dataframe and produces bars,
    so the failure-path tests above are testing the failure branch
    specifically, not an artifact of the mock breaking the happy path."""
    import yfinance as yf

    dates = pd.date_range("2026-01-01", periods=5, freq="D")
    frame = pd.DataFrame(
        {"Open": [100.0] * 5, "High": [101.0] * 5, "Low": [99.0] * 5, "Close": [100.5] * 5, "Volume": [1_000_000.0] * 5},
        index=pd.DatetimeIndex(dates, name="Date"),
    )
    monkeypatch.setattr(yf, "Ticker", lambda symbol: _FakeTicker(frame=frame))

    ohlcv = YahooFinanceProvider().fetch_ohlcv("AAPL", period="1y", interval="1d")

    assert ohlcv.symbol == "AAPL"
    assert len(ohlcv.bars) == 5


def test_a_short_truncated_series_is_not_silently_accepted_as_full_history():
    """"Partial response" (Yahoo returning fewer bars than a real
    multi-year fetch would) has no dedicated detection code of its own
    -- and does not need one: it is already caught downstream by the
    scanner's own min_bars gate (a short series is excluded, never
    silently treated as sufficient history for a decision) and by
    market_data.validation's gap detection for an internal truncation.
    This test proves that existing mechanism, rather than adding a new
    one for a failure mode two other mechanisms already cover."""
    from market_intelligence.scanner import run_scan
    from market_data.universe import MarketUniverse

    dates = pd.date_range("2026-01-01", periods=5, freq="D")  # far short of any real min_bars default
    short_frame = pd.DataFrame(
        {"Open": [100.0] * 5, "High": [101.0] * 5, "Low": [99.0] * 5, "Close": [100.5] * 5, "Volume": [1_000_000.0] * 5},
        index=pd.DatetimeIndex(dates, name="Date"),
    )

    from market.data_provider import OHLCV

    class _TruncatedProvider:
        def fetch_ohlcv(self, symbol, *, period="1y", interval="1d"):
            return OHLCV.from_dataframe(symbol=symbol, interval=interval, frame=short_frame)

    report = run_scan(MarketUniverse.from_watchlist(["AAPL"]), provider=_TruncatedProvider(), benchmark_symbol=None)

    assert report.candidates == []
    assert "Insufficient history" in report.excluded[0].reason
