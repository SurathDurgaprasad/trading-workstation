"""H_BREADTH_001 (docs/research/H_BREADTH_001_MARKET_BREADTH_
PREREGISTRATION.md, frozen design, committed before this module):
market breadth -- does the FRACTION of the universe individually
trending up predict the market's own forward return, distinct from
whether the index itself is trending up?

Pure cross-sectional aggregation, no new per-symbol indicator: reuses
each SymbolDataset's own causal `trend_regime` column
(backtesting.regime.classify_trend_at, already computed by
quant_research.market_behavior.build_symbol_dataset for every
hypothesis in this registry that touches trend regime).
"""

import pandas as pd

from quant_research.market_behavior import SymbolDataset

TRENDING_UP = "TRENDING_UP"

_VALID_REGIME_VALUES = {"TRENDING_UP", "TRENDING_DOWN", "SIDEWAYS"}
"""Excludes UNKNOWN (a symbol's own regime-classification warmup
period) from both the numerator and denominator -- a symbol still
warming up must not silently count as "not trending up," which would
bias breadth downward during each symbol's own early history."""


def compute_universe_breadth_series(datasets: dict[str, SymbolDataset]) -> pd.Series:
    """One breadth_pct value per calendar date, indexed over the union
    of every dataset's own calendar: (# symbols with trend_regime ==
    TRENDING_UP) / (# symbols with a non-UNKNOWN trend_regime), that
    date. A date where no symbol in `datasets` has a valid regime
    reading yields NaN, never a fabricated 0/1. Causal: trend_regime
    itself is already causal, and this aggregation adds no
    forward-looking step of its own -- each date's breadth uses only
    that date's own per-symbol values."""
    columns = {symbol: dataset.frame["trend_regime"] for symbol, dataset in datasets.items()}
    combined = pd.DataFrame(columns)

    up_count = combined.eq(TRENDING_UP).sum(axis=1)
    valid_count = combined.isin(_VALID_REGIME_VALUES).sum(axis=1)

    breadth = (up_count / valid_count).where(valid_count > 0)
    breadth.name = "breadth_pct"
    return breadth
