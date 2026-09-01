from typing import Protocol, runtime_checkable

import pandas as pd

from strategy.signal import Signal


@runtime_checkable
class Strategy(Protocol):
    """A deterministic rule: bar-indexed indicator data in, an optional Signal out.

    No LLM calls, no randomness, no I/O — `generate_signal` must be a pure
    function of `indicator_series.iloc[: index + 1]` (implementations may read
    the full frame, but must only look at rows <= index; see
    tests/test_backtest_lookahead.py, which is the enforcement mechanism).
    """

    name: str
    version: str  # explicit, e.g. "1.0" — Phase 6 records this on every trade; never "latest"

    def generate_signal(
        self, indicator_series: pd.DataFrame, index: int, symbol: str
    ) -> Signal | None:
        """Return a Signal formed at `indicator_series.iloc[index]`, or None."""
        ...
