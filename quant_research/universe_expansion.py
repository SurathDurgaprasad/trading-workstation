"""H_XSECT_006 (docs/research/H_XSECT_006_UNIVERSE_WIDENING_PREREGISTRATION.md):
builds the frozen ORIGINAL/EXPANDED-ONLY/COMBINED symbol groups that
pre-registration defines. The eligibility rule itself lives in
live.dhan.instruments.DhanInstrumentMap.underlying_symbols_with_active_derivative
(a general, reusable capability, F&O eligibility as an exchange-vetted
liquidity/market-cap gate); this module only converts that result into
this project's own Yahoo-style ".NS" symbols and forms the three
frozen comparison groups -- no eligibility logic of its own, and no
NIFTY-index-membership claim (market_data/universe.py's own module
docstring already declined to make that claim for lack of a verifiable
source; this module deliberately does not override that decision).
"""

from live.dhan.instruments import DhanInstrumentMap

ORIGINAL_32_NSE_UNIVERSE: tuple[str, ...] = (
    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "ICICIBANK.NS", "INFY.NS", "HINDUNILVR.NS", "ITC.NS", "SBIN.NS",
    "BHARTIARTL.NS", "KOTAKBANK.NS", "LT.NS", "AXISBANK.NS", "ASIANPAINT.NS", "MARUTI.NS", "SUNPHARMA.NS",
    "ADANIPORTS.NS", "BAJAJFINSV.NS", "BAJFINANCE.NS", "CIPLA.NS", "COALINDIA.NS", "DIVISLAB.NS", "DRREDDY.NS",
    "EICHERMOT.NS", "GRASIM.NS", "HCLTECH.NS", "HEROMOTOCO.NS", "NTPC.NS", "POWERGRID.NS", "TATASTEEL.NS",
    "TECHM.NS", "ULTRACEMCO.NS", "WIPRO.NS",
)
"""The exact 32-symbol universe H_XSECT_001 through H_XSECT_005 already
used, formalized here as a committed, versioned constant for the first
time -- previously only a hand-copied literal repeated across
uncommitted research scratch scripts (see the H_XSECT_006
pre-registration S2 for the full disclosure: no selection rationale
for these specific 32 symbols exists anywhere in this repository's
history; this is the historical control group, not a claim of
principled construction)."""


def build_universe_groups(instrument_map: DhanInstrumentMap) -> dict[str, tuple[str, ...]]:
    """Returns {"original": ..., "expanded_only": ..., "combined": ...}
    -- the three frozen comparison groups H_XSECT_006's own pre-
    registration S3 defines, each sorted for reproducibility. Never
    mutates ORIGINAL_32_NSE_UNIVERSE; EXPANDED-ONLY is exactly the
    F&O-eligible symbols NOT already in it, verified zero-overlap by
    construction (set subtraction), not assumed."""
    fno_underlyings = instrument_map.underlying_symbols_with_active_derivative()
    fno_yahoo_symbols = {f"{symbol}.NS" for symbol in fno_underlyings}

    original = set(ORIGINAL_32_NSE_UNIVERSE)
    expanded_only = tuple(sorted(fno_yahoo_symbols - original))
    combined = tuple(sorted(fno_yahoo_symbols | original))

    return {
        "original": ORIGINAL_32_NSE_UNIVERSE,
        "expanded_only": expanded_only,
        "combined": combined,
    }
