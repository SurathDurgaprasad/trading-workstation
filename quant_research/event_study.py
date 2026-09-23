"""EDGE DISCOVERY mission, Family A (corporate/event information):
H_EVENT_001/H_EVENT_002 preregistrations (strategy/hypothesis_registry.py).

Attaches real, company-disclosed ex-dividend event timing onto the same
causal per-symbol SymbolDataset frame every other hypothesis in this
project's history already uses (quant_research.market_behavior) -- the
event itself (a real historical date) is fetched once via yfinance
Ticker.dividends (already a trusted dependency -- see
market_intelligence/corporate_actions.py's own live-verified finding),
never derived from price/volume history.

Deliberately outside strategy/, risk/, paper/, backtesting/, and never
imported by any of them, the MCP server, or main.py -- same research-only
posture as every other quant_research module.
"""

from datetime import date

import pandas as pd

from quant_research.market_behavior import SymbolDataset

DEFAULT_PRE_EVENT_LEAD_DAYS = 5
"""Trading days before a known ex-dividend date, used by H_EVENT_002.
Conservative, pre-chosen (not tuned after seeing any result) and
deliberately well inside SEBI LODR Regulation 42's minimum advance-
intimation requirement for a record date/book closure -- see
H_EVENT_002's own registry entry for the full leakage-risk disclosure:
this is an INFERRED assumption (a cited external regulatory requirement),
not something directly verified from any dataset this project holds."""


def fetch_ex_dividend_dates(symbol: str) -> list[date]:
    """Full historical ex-dividend date list for `symbol`, oldest first.
    Returns [] (never raises) on a fetch failure or a symbol with no
    dividend history -- a research tool must not abort the whole universe
    over one bad/dividend-free symbol, same posture as
    quant_research.market_behavior.build_symbol_dataset."""
    import yfinance as yf

    try:
        dividends = yf.Ticker(symbol).dividends
    except Exception:  # noqa: BLE001 -- a real fetch failure yields no events, not a crash
        return []
    if dividends is None or dividends.empty:
        return []
    return sorted(ts.date() for ts in dividends.index)


def attach_dividend_event_columns(
    datasets: dict[str, SymbolDataset],
    *,
    pre_event_lead_days: int = DEFAULT_PRE_EVENT_LEAD_DAYS,
) -> dict[str, list[date]]:
    """Mutates every dataset's frame in place, adding two causal-safe
    integer columns (NaN where undefined):

    - trading_days_since_ex_div: 0 on the bar that IS a known ex-dividend
      date, 1/2/3/... on subsequent bars since the MOST RECENT past
      ex-date, NaN before the symbol's first known dividend. Strictly
      backward-looking -- a row's value never depends on a future event.

    - trading_days_until_ex_div: N on the bar exactly N trading days
      before a known FUTURE ex-dividend date (0 on the ex-date bar
      itself, matching the since-column's own convention at the event).
      Read H_EVENT_002's own registry entry before treating this as a
      real-time-tradable signal -- it encodes "N days before a date that
      has already occurred in this symbol's OWN historical record", which
      is only a legitimate real-time entry rule under the disclosed,
      unverified regulatory-lead-time assumption.

    Returns {symbol: [ex-dividend dates used]} for the leakage audit and
    the final report's own sample-size accounting.
    """
    dividend_dates_by_symbol: dict[str, list[date]] = {}

    for symbol, dataset in datasets.items():
        ex_dates = fetch_ex_dividend_dates(symbol)
        dividend_dates_by_symbol[symbol] = ex_dates

        index = dataset.frame.index
        since = pd.Series(float("nan"), index=index)
        until = pd.Series(float("nan"), index=index)

        if not ex_dates:
            dataset.frame["trading_days_since_ex_div"] = since
            dataset.frame["trading_days_until_ex_div"] = until
            continue

        # Map each ex-dividend date onto the symbol's own trading-day
        # calendar via searchsorted (nearest bar AT OR AFTER the ex-date --
        # a dividend record date on a non-trading day still lands on the
        # next real trading day, never invents a bar that doesn't exist).
        positions = index.searchsorted([pd.Timestamp(d) for d in ex_dates])
        event_positions = sorted({int(p) for p in positions if 0 <= p < len(index)})

        if event_positions:
            since_values = [float("nan")] * len(index)
            until_values = [float("nan")] * len(index)
            for i in range(len(index)):
                past_events = [p for p in event_positions if p <= i]
                if past_events:
                    since_values[i] = float(i - max(past_events))
                future_events = [p for p in event_positions if p >= i]
                if future_events:
                    until_values[i] = float(min(future_events) - i)
            since = pd.Series(since_values, index=index)
            until = pd.Series(until_values, index=index)

        dataset.frame["trading_days_since_ex_div"] = since
        dataset.frame["trading_days_until_ex_div"] = until

    return dividend_dates_by_symbol
