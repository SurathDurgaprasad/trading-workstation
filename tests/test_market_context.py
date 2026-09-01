from datetime import datetime

from market.context import MarketContext
from market.indicators import MACDValues, TechnicalIndicators, VolumeAnalysis


def test_market_context_from_indicators_maps_all_fields():
    indicators = TechnicalIndicators(
        symbol="AAPL",
        as_of=datetime(2026, 8, 24),
        close=310.34,
        sma_20=313.01,
        sma_50=310.50,
        rsi_14=48.23,
        macd=MACDValues(macd=-1.49, signal=-1.25, histogram=-0.23),
        atr_14=6.04,
        volume=VolumeAnalysis(
            current_volume=1_000_000,
            volume_sma_20=1_500_000,
            volume_ratio=0.66,
            trend="decreasing",
        ),
    )

    context = MarketContext.from_indicators(indicators)

    assert context.symbol == "AAPL"
    assert context.price == 310.34
    assert context.macd == -1.49
    assert context.macd_signal == -1.25
    assert context.macd_histogram == -0.23
    assert context.volume_ratio == 0.66
    assert context.volume_trend == "decreasing"


def test_market_context_from_indicators_handles_missing_macd_and_volume():
    indicators = TechnicalIndicators(
        symbol="THIN",
        as_of=datetime(2026, 8, 24),
        close=10.0,
        sma_20=None,
        sma_50=None,
        rsi_14=None,
        macd=None,
        atr_14=None,
        volume=None,
    )

    context = MarketContext.from_indicators(indicators)

    assert context.macd is None
    assert context.macd_signal is None
    assert context.volume_trend is None


def test_market_context_is_frozen():
    context = MarketContext(symbol="AAPL", as_of=datetime(2026, 8, 24), price=1.0)
    try:
        context.price = 2.0
        assert False, "MarketContext should be immutable"
    except Exception:
        pass


def test_to_prompt_lines_renders_unknown_for_missing_values():
    context = MarketContext(symbol="THIN", as_of=datetime(2026, 8, 24), price=10.0)
    lines = context.to_prompt_lines()

    joined = "\n".join(lines)
    assert "UNKNOWN" in joined
    assert "THIN" in joined
    # A real number must never render as UNKNOWN.
    assert "Price: 10.00" in joined


def test_to_prompt_lines_never_hallucinates_missing_as_a_number():
    context = MarketContext(symbol="THIN", as_of=datetime(2026, 8, 24), price=10.0)
    rsi_line = next(line for line in context.to_prompt_lines() if line.startswith("RSI14"))
    assert rsi_line == "RSI14: UNKNOWN"
