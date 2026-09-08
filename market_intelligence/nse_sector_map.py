"""A conservative, high-confidence-only symbol -> NIFTY sector-index
mapping, promoted here from the INDIAN TRADING DECISION BRAIN mission's
own research scratchpad (used to build H_CONTEXT_SECTOR_001/002 and
H_CONTEXT_ALIGN_001 in strategy/hypothesis_registry.py) so both future
research AND the live-facing daily decision report reuse the SAME
mapping instead of each hand-rolling their own.

NOT sourced from an official NSE/NSE-Indices index-constituent file --
none is integrated in this project (see market_intelligence/regime.py's
own NIFTY_SECTOR_INDICES docstring for the same caveat on the index
tickers themselves). Deliberately narrow: only symbols this project is
confident belong to exactly one of the 9 real NIFTY_SECTOR_INDICES
sectors are included; anything ambiguous (a diversified conglomerate, a
sector with no matching official index) is left out rather than guessed
-- `market_intelligence.regime.NIFTY_SECTOR_INDICES` lists which 9
sectors actually have a real, working index ticker.

Covers 20 of the 32-symbol NSE research universe
(backtesting-side symbol list documented in quant_research/
context_experiments.py's own research scripts / strategy/
hypothesis_registry.py's H_CONTEXT_SECTOR_001 entry). Deliberately
excluded: RELIANCE.NS, LT.NS, ASIANPAINT.NS, BHARTIARTL.NS,
ADANIPORTS.NS, GRASIM.NS, ULTRACEMCO.NS, TATASTEEL.NS, COALINDIA.NS,
NTPC.NS, POWERGRID.NS -- no confident single-sector match among the 9
available indices. A symbol not in this map simply gets no sector
context anywhere this map is used -- never fabricated as "no sector" in
a way that could be confused with a real classification.
"""

NSE_SECTOR_MAP: dict[str, str] = {
    "HDFCBANK.NS": "NIFTY_BANK",
    "ICICIBANK.NS": "NIFTY_BANK",
    "SBIN.NS": "NIFTY_BANK",
    "KOTAKBANK.NS": "NIFTY_BANK",
    "AXISBANK.NS": "NIFTY_BANK",
    "TCS.NS": "NIFTY_IT",
    "INFY.NS": "NIFTY_IT",
    "HCLTECH.NS": "NIFTY_IT",
    "TECHM.NS": "NIFTY_IT",
    "WIPRO.NS": "NIFTY_IT",
    "MARUTI.NS": "NIFTY_AUTO",
    "EICHERMOT.NS": "NIFTY_AUTO",
    "HEROMOTOCO.NS": "NIFTY_AUTO",
    "SUNPHARMA.NS": "NIFTY_PHARMA",
    "CIPLA.NS": "NIFTY_PHARMA",
    "DIVISLAB.NS": "NIFTY_PHARMA",
    "DRREDDY.NS": "NIFTY_PHARMA",
    "HINDUNILVR.NS": "NIFTY_FMCG",
    "ITC.NS": "NIFTY_FMCG",
    "BAJFINANCE.NS": "NIFTY_FINANCIAL_SERVICES",
    "BAJAJFINSV.NS": "NIFTY_FINANCIAL_SERVICES",
}


def sector_for_symbol(symbol: str) -> str | None:
    return NSE_SECTOR_MAP.get(symbol.strip().upper())
