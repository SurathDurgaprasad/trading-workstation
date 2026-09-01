from core.events import log_event
from market.context import get_market_context
from state import TradingState


def market_context_agent(state: TradingState) -> dict:
    symbol = state.get("symbol")
    if not symbol or not symbol.strip():
        raise ValueError(
            "No symbol provided. Pass --symbol (e.g. --symbol AAPL) — "
            "automatic symbol discovery is not implemented yet."
        )

    print(f"Fetching market data for {symbol}...")
    log_event("market_data_requested", symbol=symbol)

    market_context = get_market_context(symbol)

    log_event(
        "market_data_received",
        symbol=symbol,
        price=market_context.price,
        as_of=market_context.as_of.isoformat(),
    )
    log_event(
        "indicators_computed",
        symbol=symbol,
        sma_20=market_context.sma_20,
        sma_50=market_context.sma_50,
        rsi_14=market_context.rsi_14,
        atr_14=market_context.atr_14,
    )

    return {"market_context": market_context}
