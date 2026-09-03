"""Phase 18 -- configurable instrument universe. Phase 29 adds symbol
validation, exchange/instrument metadata enrichment, and a committed
starter watchlist -- see each addition's own docstring below for why.

Explicitly watchlist-only for now, per the roadmap's own staged guidance:
"Do not start with NIFTY 500... start with a configured watchlist."
Index-membership modes (nifty50/nifty100/nifty200/nifty500) remain a
documented, deliberately unimplemented future extension -- recognized by
name (so a typo'd future mode fails clearly) but never silently stubbed
to pretend they work. Phase 29 considered implementing `mode: nifty50`
backed by a bundled constituent list, and deliberately did NOT: an
index's actual membership changes over time (periodic rebalancing), and
this project has no live, verifiable source for current membership
integrated anywhere -- shipping a static list under the name "NIFTY 50"
would claim an accuracy this project cannot back up, the same
"never claim real-service verification from something that isn't"
discipline applied everywhere else. Phase 29's `starter_nse.yaml` (see
the bottom of this file) is the honest alternative: a small, clearly-
labeled, illustrative watchlist of liquid NSE large-caps, not a claim of
official index membership.
"""

from dataclasses import dataclass
from pathlib import Path

import yaml

_SUPPORTED_MODES = ("watchlist",)
_KNOWN_FUTURE_MODES = ("nifty50", "nifty100", "nifty200", "nifty500")

_YAHOO_SUFFIX_TO_EXCHANGE = {".NS": "NSE", ".BO": "BSE"}


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
            # Phase 29 audit finding: a common paste/typo error -- passing
            # "AAPL,MSFT" as ONE element of the list (e.g. --symbols
            # split incorrectly, or a copy-pasted comma-joined string
            # re-wrapped in a list) -- previously produced a single
            # bogus symbol that only failed much later, opaquely, at the
            # Yahoo fetch stage. Reject it here with a message that
            # names the actual mistake.
            if "," in symbol or any(ch.isspace() for ch in symbol):
                raise ValueError(
                    f"Watchlist symbol {raw!r} contains a comma or internal whitespace -- "
                    "this usually means a comma-joined string was passed as a single list "
                    "element instead of being split first (e.g. \"AAPL,MSFT\".split(','))."
                )
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

    def describe(self, *, instrument_map: "DhanInstrumentMap | None" = None) -> tuple["InstrumentMetadata", ...]:
        """Phase 29 -- symbol/exchange/instrument-identifier metadata for
        every symbol in this universe, in order. `instrument_map` is
        OPTIONAL and best-effort: pass a `live.dhan.instruments.
        DhanInstrumentMap` (built via its own, credential-free
        `.download()`) to additionally populate Dhan security IDs for
        symbols it recognizes -- a symbol it does not recognize, or no
        map at all, simply leaves those fields None. Never raises for a
        missing/unresolved instrument; enrichment must never block a
        universe from being usable, the same posture every other
        optional-enrichment step in this project already has (AI
        summaries, AI narratives, sector maps)."""
        return tuple(instrument_metadata_for(symbol, instrument_map=instrument_map) for symbol in self.symbols)


def exchange_for_symbol(symbol: str) -> str:
    """Pure, deterministic: ".NS" -> "NSE", ".BO" -> "BSE", anything else
    -> "OTHER" (e.g. "AAPL", "^NSEI", a future non-Indian symbol). Never
    raises -- an unrecognized suffix is a legitimate, expected case
    (this project's own test fixtures and existing watchlists already
    mix US tickers like AAPL/MSFT with NSE tickers like RELIANCE.NS)."""
    normalized = symbol.strip().upper()
    for suffix, exchange in _YAHOO_SUFFIX_TO_EXCHANGE.items():
        if normalized.endswith(suffix):
            return exchange
    return "OTHER"


@dataclass(frozen=True)
class InstrumentMetadata:
    symbol: str
    exchange: str
    """"NSE", "BSE", or "OTHER" -- see `exchange_for_symbol`."""
    dhan_security_id: str | None = None
    dhan_display_name: str | None = None
    """Both None unless a `DhanInstrumentMap` was supplied AND recognized
    this symbol -- never fabricated, never a placeholder value."""


def instrument_metadata_for(symbol: str, *, instrument_map: "DhanInstrumentMap | None" = None) -> InstrumentMetadata:
    normalized = symbol.strip().upper()
    exchange = exchange_for_symbol(normalized)

    dhan_security_id = None
    dhan_display_name = None
    if instrument_map is not None:
        from live.dhan.instruments import InstrumentNotFoundError

        try:
            instrument = instrument_map.lookup_yahoo_symbol(normalized)
        except InstrumentNotFoundError:
            pass
        else:
            dhan_security_id = instrument.security_id
            dhan_display_name = instrument.display_name

    return InstrumentMetadata(
        symbol=normalized, exchange=exchange,
        dhan_security_id=dhan_security_id, dhan_display_name=dhan_display_name,
    )
