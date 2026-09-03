from datetime import datetime, timedelta, timezone

from learning.regime import MarketRegime, classify_regime_at
from market.data_provider import OHLCV, MarketDataError, OHLCVBar

_START = datetime(2022, 1, 1)


def _ohlcv(symbol: str, closes: list[float]) -> OHLCV:
    bars = [
        OHLCVBar(timestamp=_START + timedelta(days=i), open=c, high=c * 1.01, low=c * 0.99, close=c, volume=1000.0)
        for i, c in enumerate(closes)
    ]
    return OHLCV(symbol=symbol, interval="1d", bars=bars)


class _FakeProvider:
    def __init__(self, ohlcv: OHLCV | None = None, error: Exception | None = None):
        self._ohlcv = ohlcv
        self._error = error

    def fetch_ohlcv(self, symbol, *, period="1y", interval="1d"):
        if self._error is not None:
            raise self._error
        return self._ohlcv


def test_classify_regime_uptrend_when_close_above_sma200():
    closes = [100.0 + i * 0.5 for i in range(250)]  # steadily rising -> close > SMA200
    provider = _FakeProvider(_ohlcv("AAPL", closes))
    as_of = _START + timedelta(days=249)

    regime = classify_regime_at("AAPL", as_of, provider=provider)

    assert regime == MarketRegime.UPTREND


def test_classify_regime_downtrend_when_close_below_sma200():
    closes = [300.0 - i * 0.5 for i in range(250)]  # steadily falling -> close < SMA200
    provider = _FakeProvider(_ohlcv("AAPL", closes))
    as_of = _START + timedelta(days=249)

    regime = classify_regime_at("AAPL", as_of, provider=provider)

    assert regime == MarketRegime.DOWNTREND


def test_classify_regime_unknown_on_insufficient_history():
    closes = [100.0 + i for i in range(50)]  # far fewer than 200 bars
    provider = _FakeProvider(_ohlcv("AAPL", closes))
    as_of = _START + timedelta(days=49)

    regime = classify_regime_at("AAPL", as_of, provider=provider)

    assert regime == MarketRegime.UNKNOWN


def test_classify_regime_unknown_on_fetch_failure():
    provider = _FakeProvider(error=MarketDataError("simulated outage"))
    regime = classify_regime_at("AAPL", _START, provider=provider)
    assert regime == MarketRegime.UNKNOWN


def test_classify_regime_only_uses_history_at_or_before_as_of():
    # 300 rising bars, but as_of is set to bar 100 -- only the first 101
    # bars (insufficient for SMA200) should be considered, not the full set.
    closes = [100.0 + i * 0.5 for i in range(300)]
    provider = _FakeProvider(_ohlcv("AAPL", closes))
    as_of = _START + timedelta(days=100)

    regime = classify_regime_at("AAPL", as_of, provider=provider)

    assert regime == MarketRegime.UNKNOWN


def test_classify_regime_accepts_a_utc_aware_as_of_against_naive_bars():
    """Regression (Phase 33): a real, UTC-aware `as_of` (e.g.
    `datetime.now(timezone.utc)`, what market_intelligence.regime passes
    for a live "regime right now" check) against naive Yahoo/mock bars
    previously raised `pandas.errors.InvalidComparison` -- Phase 24's own
    original call site always passed an already-naive as_of, so this
    never surfaced until a new caller exercised it."""
    closes = [100.0 + i * 0.5 for i in range(250)]
    provider = _FakeProvider(_ohlcv("AAPL", closes))
    aware_as_of = (_START + timedelta(days=249)).replace(tzinfo=timezone.utc)

    regime = classify_regime_at("AAPL", aware_as_of, provider=provider)

    assert regime == MarketRegime.UPTREND


def test_classify_regime_accepts_a_naive_as_of_against_aware_bars():
    """The reverse mix: real Dhan bars are UTC-aware since the Phase 16
    fix; a naive as_of against them must not raise either."""
    aware_start = _START.replace(tzinfo=timezone.utc)
    closes = [100.0 + i * 0.5 for i in range(250)]
    bars = [
        OHLCVBar(timestamp=aware_start + timedelta(days=i), open=c, high=c * 1.01, low=c * 0.99, close=c, volume=1000.0)
        for i, c in enumerate(closes)
    ]
    provider = _FakeProvider(OHLCV(symbol="AAPL", interval="1d", bars=bars))
    naive_as_of = _START + timedelta(days=249)

    regime = classify_regime_at("AAPL", naive_as_of, provider=provider)

    assert regime == MarketRegime.UPTREND
