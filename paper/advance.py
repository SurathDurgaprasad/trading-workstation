"""Advances existing PENDING paper orders / OPEN paper positions using
GENUINELY LATER market data fetched fresh from a provider -- the fill/
exit half of the paper-execution lifecycle the decision_engine bridge
(main.py's `shadow-run --paper-execute`) deliberately does not attempt
itself: PaperTradingEngine.submit_signal() only ever creates a PENDING
order (see its own docstring). Something must separately feed it a bar
strictly newer than the signal-generating one to actually fill or exit
it -- that is what this module does, and ONLY what it does.

Reuses PaperTradingEngine.process_bar() verbatim -- the SAME primitive
paper.replay's historical replay and live.pipeline's live-sim driver
already use. This is not a second execution engine, just a new way of
DRIVING the existing one with a different bar source.

NO LOOK-AHEAD BIAS BY CONSTRUCTION -- the one property this module
exists to guarantee: every bar fed to process_bar() here is freshly
fetched from the provider AT CALL TIME, filtered to strictly newer than
a per-symbol BASELINE timestamp. That baseline is never the bar that
generated the order:
  - If process_bar has already run at least once for this symbol (an
    OPEN position, or a PENDING order already advanced by a prior call
    to this function), PaperStore.get_last_bar_timestamp(symbol) is
    authoritative -- it was set by that earlier process_bar call, which
    itself was already validated against this same guarantee.
  - Otherwise (a PENDING order that has NEVER been advanced), the
    baseline falls back to the order's OWN signal's generated_at --
    the one moment already, definitionally, "seen" (it is what
    produced the order) and therefore never eligible to fill against.
  - If neither can be established, the symbol is SKIPPED entirely
    (fail-closed) rather than risk treating every historical bar as
    "new".
"""

from dataclasses import dataclass
from datetime import datetime

from market.data_provider import MarketDataProvider
from paper.engine import Bar, PaperTradingEngine, _naive
from paper.models import PositionStatus


@dataclass(frozen=True)
class AdvanceResult:
    symbol: str
    bars_processed: int
    last_outcome: str | None
    skipped_reason: str | None = None
    error: str | None = None


def _baseline_timestamp_for(engine: PaperTradingEngine, symbol: str) -> datetime | None:
    last_processed = engine.store.get_last_bar_timestamp(symbol)
    if last_processed is not None:
        return last_processed

    pending = engine.store.get_pending_order(symbol)
    if pending is not None:
        signal = engine.store.get_signal(pending.signal_id)
        if signal is not None:
            return _naive(signal.generated_at)

    return None


def advance_pending_paper_orders(
    engine: PaperTradingEngine, *, provider: MarketDataProvider, period: str = "1y", interval: str = "1d",
) -> list[AdvanceResult]:
    """For every symbol with a PENDING order or an OPEN position in
    `engine`'s account, fetches fresh OHLCV and feeds every bar strictly
    newer than that symbol's safe baseline through engine.process_bar()
    -- in chronological order, so an intermediate stop/target crossing
    between two calls to this function is never silently skipped (only
    checking the single latest bar each time would miss that).

    Idempotent: calling this again with no new data for a symbol simply
    finds zero eligible bars and does nothing (bars_processed=0) --
    process_bar()'s own DUPLICATE_SKIPPED handling is a second,
    redundant layer of the same guarantee, not the only one.

    One symbol's failure (a bad provider response, an unexpected
    exception) never aborts advancing the rest -- same posture as
    shadow-run's own per-symbol isolation. If the failure happens
    mid-loop (bar N of several), bars before it were already durably
    committed (each process_bar() call is its own transaction) --
    the returned AdvanceResult.bars_processed reports that real count,
    never a hardcoded 0, so the audit trail never under-states what
    actually happened before the error."""
    pending_symbols = {order.symbol for order in engine.store.list_pending_orders()}
    open_symbols = {position.symbol for position in engine.store.list_positions() if position.status == PositionStatus.OPEN}
    symbols = sorted(pending_symbols | open_symbols)

    results: list[AdvanceResult] = []
    for symbol in symbols:
        # Tracked OUTSIDE the try block (not just inside it) so a mid-loop
        # failure's `except` clause below can report how many bars ACTUALLY
        # got committed before the error, not a hardcoded 0 -- each
        # process_bar() call commits in its own transaction, so bars before
        # the failing one are genuinely persisted even though this whole
        # symbol's iteration is about to be reported as an error. Found via
        # self-audit: the previous version reported bars_processed=0 on any
        # exception, silently under-stating real state changes in the very
        # audit trail this project is required to keep honest.
        bars_processed = 0
        last_outcome: str | None = None
        try:
            baseline = _baseline_timestamp_for(engine, symbol)
            if baseline is None:
                results.append(AdvanceResult(
                    symbol=symbol, bars_processed=0, last_outcome=None,
                    skipped_reason="no safe baseline timestamp could be established -- skipped to avoid look-ahead risk",
                ))
                continue

            # Real, demonstrated finding: Account is single-position (an
            # aggregate field, not per-symbol) -- PaperTradingEngine.
            # submit_signal() already tolerates multiple simultaneous
            # PENDING orders across different symbols (nothing vetoes a
            # second symbol until one actually FILLS), but process_bar()'s
            # own fill path has no equivalent graceful check: it calls
            # Account.open_position() unconditionally, which RAISES its
            # own hard single-position invariant if a DIFFERENT symbol is
            # already open. Reproduced directly (two symbols, both
            # eligible to fill in the same advance() call) before adding
            # this guard. A symbol that already HAS an open position of
            # its own is unaffected -- only a symbol with just a PENDING
            # order, while some OTHER symbol already holds the account's
            # one open position, is held back here.
            if engine.store.get_open_position(symbol) is None and engine.account.open_positions > 0:
                results.append(AdvanceResult(
                    symbol=symbol, bars_processed=0, last_outcome=None,
                    skipped_reason="another symbol already holds this single-position account's one open position -- will retry once it closes",
                ))
                continue

            ohlcv = provider.fetch_ohlcv(symbol, period=period, interval=interval)
            new_bars = sorted(
                (bar for bar in ohlcv.bars if _naive(bar.timestamp) > baseline),
                key=lambda bar: bar.timestamp,
            )

            for ohlcv_bar in new_bars:
                engine_bar = Bar(
                    timestamp=ohlcv_bar.timestamp, open=ohlcv_bar.open, high=ohlcv_bar.high,
                    low=ohlcv_bar.low, close=ohlcv_bar.close, volume=ohlcv_bar.volume,
                )
                outcome = engine.process_bar(symbol, engine_bar)
                last_outcome = outcome.value
                bars_processed += 1

            results.append(AdvanceResult(symbol=symbol, bars_processed=bars_processed, last_outcome=last_outcome))
        except Exception as exc:  # noqa: BLE001 -- one symbol's failure must never abort advancing the rest
            results.append(AdvanceResult(symbol=symbol, bars_processed=bars_processed, last_outcome=last_outcome, error=f"{type(exc).__name__}: {exc}"))

    return results
