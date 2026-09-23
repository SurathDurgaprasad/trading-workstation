"""Real-time strategy validation mission, multi-symbol hardening pass --
deterministic per-symbol runtime directory layout for the independent-
process multi-symbol paper-live fleet.

Hard constraint (see FINAL_FAILURE_MODE_ANALYSIS.md and this mission's
own explicit instruction): live/pipeline.py is NOT modified to support
multi-symbol operation -- CriticGate is documented as "one instance per
(symbol, interval)" and LiveSimPipeline holds exactly one critic_gate
object applied to every signal regardless of symbol, so a single process
handling multiple symbols with the critic enabled would silently
evaluate every signal against the wrong symbol's scanner evidence. The
production mechanism for tomorrow's 15-symbol session is therefore N
INDEPENDENT single-symbol `paper-live` processes -- this module gives
each one a deterministic, collision-proof place to persist its own
state:

    runtime/
      RELIANCE.NS/
        paper.db
        state.db
        predictions.db
        logs/
      TCS.NS/
      ...

Pure path arithmetic and a pure verification check -- no store/DB
imports, no symbol-specific trading logic, no I/O beyond directory
creation.
"""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SymbolRuntimePaths:
    symbol: str
    """Normalized (stripped, uppercased) -- see symbol_runtime_paths."""
    root: Path
    paper_db: Path
    state_db: Path
    predictions_db: Path
    logs_dir: Path
    heartbeat_path: Path
    """live/heartbeat.py: overwritten periodically while a paper-live
    process for this symbol is running -- see that module's docstring."""
    graceful_shutdown_path: Path
    """live/heartbeat.py: written only on a normal/caught exit."""


def symbol_runtime_paths(runtime_dir: str | Path, symbol: str) -> SymbolRuntimePaths:
    """Derives the deterministic {runtime_dir}/{symbol}/... layout for
    one symbol. The symbol is normalized (stripped, uppercased) before
    being used as a directory name -- matching this project's own
    established symbol-normalization convention
    (market_data.universe.MarketUniverse.from_watchlist,
    market.data_provider.YahooFinanceProvider) -- so "reliance.ns" and
    "RELIANCE.NS" always resolve to the SAME directory, never two
    silently-different ones that could each accumulate half of one
    symbol's real history."""
    normalized = symbol.strip().upper()
    if not normalized:
        raise ValueError("symbol must not be empty.")
    if "/" in normalized or "\\" in normalized or ".." in normalized:
        # Defensive hardening (2026-09-22 continuous red-team pass): every
        # current caller sources `symbol` from an operator-supplied CLI
        # argument or a local YAML watchlist file, never from network/HTTP
        # input, so this was not independently exploitable today -- but a
        # symbol containing a path separator or `..` could otherwise
        # resolve `root` outside the intended runtime_dir tree entirely.
        # Rejected explicitly rather than left to accidentally work (or
        # accidentally break) if a future caller ever sources `symbol`
        # from a less-trusted place.
        raise ValueError(f"symbol must not contain a path separator or '..': {symbol!r}")
    root = Path(runtime_dir) / normalized
    return SymbolRuntimePaths(
        symbol=normalized,
        root=root,
        paper_db=root / "paper.db",
        state_db=root / "state.db",
        predictions_db=root / "predictions.db",
        logs_dir=root / "logs",
        heartbeat_path=root / "heartbeat.json",
        graceful_shutdown_path=root / "graceful_shutdown.json",
    )


def ensure_symbol_runtime_dirs(paths: SymbolRuntimePaths) -> None:
    """Creates root + logs/ if they don't already exist yet. Idempotent
    -- safe to call on every startup, including a restart against an
    already-populated directory (mkdir(exist_ok=True) never truncates or
    disturbs existing files)."""
    paths.root.mkdir(parents=True, exist_ok=True)
    paths.logs_dir.mkdir(parents=True, exist_ok=True)


class CrossSymbolContaminationError(ValueError):
    """Raised by verify_no_cross_symbol_contamination when a store this
    process is about to use already contains persisted data for a
    DIFFERENT symbol than the one this process is starting as -- the
    real, mission-required guard against a manual --db/--state-db/
    --predictions-db typo (or a --runtime-dir mixup) accidentally
    pointing one symbol's worker at another symbol's history."""


def verify_no_cross_symbol_contamination(*, expected_symbol: str, observed_symbols: set[str]) -> None:
    """`observed_symbols` is every symbol already found in a store this
    process is about to use (e.g. every trade/position/prediction symbol
    already persisted there). Raises CrossSymbolContaminationError if
    anything other than `expected_symbol` (case/whitespace-normalized)
    is present. A store with NO data yet (observed_symbols empty) or
    data ONLY for the expected symbol both pass silently -- this is not
    a claim that the store is otherwise well-formed, only that it has
    never held another symbol's data."""
    normalized_expected = expected_symbol.strip().upper()
    unexpected = {s.strip().upper() for s in observed_symbols} - {normalized_expected}
    if unexpected:
        raise CrossSymbolContaminationError(
            f"This store already contains data for symbol(s) {sorted(unexpected)!r}, but this process is "
            f"starting as {normalized_expected!r} -- refusing to start to avoid mixing two symbols' state. "
            "This usually means a --db/--state-db/--predictions-db path (or --runtime-dir) was pointed at "
            "the wrong symbol's directory -- check for a copy-pasted command where one flag was not updated."
        )
