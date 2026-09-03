"""Phase 18 -- configurable instrument universe.

Explicitly watchlist-only for now, per the roadmap's own staged guidance:
"Do not start with NIFTY 500... start with a configured watchlist."
Index-membership modes (nifty50/nifty100/nifty200/nifty500) are a
documented, deliberately unimplemented future extension -- recognized by
name (so a typo'd future mode fails clearly) but never silently stubbed
to pretend they work.
"""

from dataclasses import dataclass
from pathlib import Path

import yaml

_SUPPORTED_MODES = ("watchlist",)
_KNOWN_FUTURE_MODES = ("nifty50", "nifty100", "nifty200", "nifty500")


class UnsupportedUniverseModeError(ValueError):
    """Raised for a recognized-but-not-yet-implemented mode (e.g.
    "nifty50") or a genuinely unknown one, so the failure is specific and
    actionable -- not a generic KeyError/ValueError from deep inside some
    other lookup."""


@dataclass(frozen=True)
class MarketUniverse:
    mode: str
    symbols: tuple[str, ...]

    @classmethod
    def from_watchlist(cls, symbols: list[str]) -> "MarketUniverse":
        """Phase 18 audit fix: symbols are normalized (stripped, uppercased
        -- matching market.data_provider.YahooFinanceProvider's own
        internal `symbol.strip().upper()`, so a universe symbol and the
        adapter that fetches it never silently disagree on casing) and
        deduplicated (first occurrence wins, order otherwise preserved) --
        without this, a duplicate or differently-cased entry would inflate
        len(universe) and cause UnifiedMarketDataFacade.get_market_snapshot()
        to redundantly re-fetch the same instrument."""
        if not symbols:
            raise ValueError("A watchlist universe must contain at least one symbol.")
        normalized: list[str] = []
        seen: set[str] = set()
        for raw in symbols:
            symbol = raw.strip().upper()
            if not symbol:
                raise ValueError(f"Watchlist contains an empty/blank symbol: {raw!r}.")
            if symbol not in seen:
                seen.add(symbol)
                normalized.append(symbol)
        return cls(mode="watchlist", symbols=tuple(normalized))

    @classmethod
    def from_config(cls, config: dict) -> "MarketUniverse":
        """`config` matches the roadmap's own documented shape:
        {"mode": "watchlist", "symbols": [...]}."""
        mode = config.get("mode")
        if mode == "watchlist":
            return cls.from_watchlist(list(config.get("symbols") or []))
        if mode in _KNOWN_FUTURE_MODES:
            raise UnsupportedUniverseModeError(
                f"Universe mode {mode!r} is a recognized future mode (index-membership universes) "
                f"but is not implemented yet -- use mode: watchlist with an explicit symbol list."
            )
        raise UnsupportedUniverseModeError(f"Unknown universe mode: {mode!r}. Supported modes: {_SUPPORTED_MODES}.")

    @classmethod
    def from_yaml_file(cls, path: Path | str) -> "MarketUniverse":
        with open(path) as handle:
            raw = yaml.safe_load(handle)
        config = (raw or {}).get("market_universe")
        if not config:
            raise ValueError(f"{path} has no top-level 'market_universe' key.")
        return cls.from_config(config)

    def __len__(self) -> int:
        return len(self.symbols)

    def __contains__(self, symbol: str) -> bool:
        return symbol.strip().upper() in self.symbols
