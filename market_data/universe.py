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
        if not symbols:
            raise ValueError("A watchlist universe must contain at least one symbol.")
        return cls(mode="watchlist", symbols=tuple(symbols))

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
        return symbol in self.symbols
