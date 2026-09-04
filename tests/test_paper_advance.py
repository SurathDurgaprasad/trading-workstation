"""paper/advance.py: the fill/exit half of the paper-execution lifecycle.
The SINGLE most important property this file exists to prove is NO
LOOK-AHEAD BIAS -- a PENDING order must never fill using the same bar
that generated its signal, only a genuinely later one."""

from datetime import datetime, timedelta

import pytest

from market.data_provider import OHLCV, OHLCVBar
from paper.advance import advance_pending_paper_orders
from paper.engine import Bar, PaperTradingEngine
from paper.models import JournalOutcome, PositionStatus
from paper.store import PaperStore
from strategy.signal import ReasonCode, Side, Signal

_GENERATED_AT = datetime(2026, 1, 1)


def _signal(**overrides) -> Signal:
    base = dict(
        symbol="TEST", generated_at=_GENERATED_AT, side=Side.LONG,
        reference_price=100.0, stop_price=95.0, target_price=110.0, risk_reward=2.0,
        strategy_name="decision_engine_buy_bridge", reason_codes=[ReasonCode.DECISION_ENGINE_SCORED],
    )
    base.update(overrides)
    return Signal(**base)


@pytest.fixture
def engine() -> PaperTradingEngine:
    return PaperTradingEngine(PaperStore(":memory:"), initial_capital=20_000.0)


class _FakeProvider:
    def __init__(self, bars: list[OHLCVBar]):
        self._bars = bars

    def fetch_ohlcv(self, symbol, *, period="1y", interval="1d"):
        return OHLCV(symbol=symbol, interval=interval, bars=self._bars)


def _bar(day_offset: int, *, open, high, low, close, volume=1000.0) -> OHLCVBar:
    return OHLCVBar(timestamp=_GENERATED_AT + timedelta(days=day_offset), open=open, high=high, low=low, close=close, volume=volume)


# --- the core guarantee: no look-ahead bias -------------------------------------


def test_advance_never_fills_using_the_signal_generating_bar_itself(engine):
    """The provider's LATEST/only bar is the EXACT SAME bar the signal
    was generated from (day_offset=0, i.e. _GENERATED_AT itself) -- a
    real scenario if this function is called again before any genuinely
    new bar exists. Must NOT fill."""
    engine.submit_signal(_signal())
    provider = _FakeProvider([_bar(0, open=100.0, high=101.0, low=99.0, close=100.0)])

    results = advance_pending_paper_orders(engine, provider=provider)

    assert results[0].bars_processed == 0
    assert engine.store.get_pending_order("TEST") is not None  # still PENDING, never filled
    assert engine.store.get_open_position("TEST") is None


def test_advance_fills_using_a_genuinely_later_bar(engine):
    engine.submit_signal(_signal())
    provider = _FakeProvider([
        _bar(0, open=100.0, high=101.0, low=99.0, close=100.0),  # the signal-generating bar -- must be excluded
        _bar(1, open=103.0, high=104.0, low=102.0, close=103.5),  # genuinely later -- eligible
    ])

    results = advance_pending_paper_orders(engine, provider=provider)

    assert results[0].bars_processed == 1
    assert results[0].last_outcome == "PROCESSED"
    position = engine.store.get_open_position("TEST")
    assert position is not None
    assert abs(position.entry_price - 103.0) < 1.0  # slippage-adjusted, close to the later bar's open, NOT 100.0


def test_advance_is_idempotent_with_no_new_data(engine):
    engine.submit_signal(_signal())
    provider = _FakeProvider([_bar(0, open=100.0, high=101.0, low=99.0, close=100.0), _bar(1, open=103.0, high=104.0, low=102.0, close=103.5)])
    advance_pending_paper_orders(engine, provider=provider)

    results = advance_pending_paper_orders(engine, provider=provider)  # same data again, nothing new
    assert results[0].bars_processed == 0
    assert engine.store.get_open_position("TEST") is not None  # unchanged, not double-filled


# --- multi-bar stop/target detection --------------------------------------------


def test_advance_detects_a_stop_hit_that_occurs_on_an_intermediate_bar_not_just_the_latest(engine):
    """Calling advance ONCE with three new bars must check the stop/target
    on EVERY one of them in order, not just the final/latest bar -- a
    stop hit on bar 2 (of 3) must be detected even though bar 3 is also
    fed in the same call."""
    engine.submit_signal(_signal(stop_price=95.0, target_price=110.0))
    provider = _FakeProvider([
        _bar(0, open=100.0, high=101.0, low=99.0, close=100.0),   # signal bar, excluded
        _bar(1, open=101.0, high=101.5, low=100.5, close=101.0),  # fills the order
        _bar(2, open=100.0, high=101.0, low=90.0, close=93.0),    # STOP HIT here (low=90 < stop=95)
        _bar(3, open=93.0, high=150.0, low=93.0, close=140.0),    # would have been a target hit if reached -- must NOT be, position already closed
    ])

    results = advance_pending_paper_orders(engine, provider=provider)

    assert results[0].bars_processed == 3  # bar 0 (the signal bar) correctly excluded -- bars 1, 2, 3 processed
    assert engine.store.get_open_position("TEST") is None  # closed

    trades = engine.store.list_trades()
    assert len(trades) == 1
    assert trades[0].exit_price == 95.0  # stopped out at the STOP price, not carried to bar 3's high


# --- retroactive baseline resolution (a pre-existing order never advanced before) ---


def test_advance_resolves_a_safe_baseline_from_the_orders_own_signal_when_never_advanced_before(engine):
    """A PENDING order that has NEVER had process_bar called for it (no
    last_bar_timestamp cursor exists yet) must still resolve a safe
    baseline via its own signal's generated_at -- proven by using a
    provider whose bars start exactly at day 0 (the signal bar): it
    must be excluded even with zero prior cursor state."""
    engine.submit_signal(_signal())
    assert engine.store.get_last_bar_timestamp("TEST") is None  # confirm: genuinely never advanced

    provider = _FakeProvider([_bar(0, open=100.0, high=101.0, low=99.0, close=100.0)])
    results = advance_pending_paper_orders(engine, provider=provider)
    assert results[0].bars_processed == 0  # day-0 bar correctly excluded despite no cursor


# --- multiple symbols --------------------------------------------------------------


def test_advance_gracefully_holds_back_a_second_symbol_until_the_open_position_closes(engine):
    """Real, demonstrated finding: Account is single-position (an
    aggregate field, not per-symbol). Two DIFFERENT symbols can each
    independently hold a PENDING order (submit_signal tolerates this),
    but only ONE can ever actually be OPEN at a time. The second symbol
    eligible to fill in the same advance() call must be gracefully held
    back -- never a raised exception, never a silently dropped order."""
    engine.submit_signal(_signal(symbol="AAA"))
    engine.submit_signal(_signal(symbol="BBB", generated_at=_GENERATED_AT + timedelta(days=5)))

    class _MultiProvider:
        def fetch_ohlcv(self, symbol, *, period="1y", interval="1d"):
            if symbol == "AAA":
                return OHLCV(symbol=symbol, interval=interval, bars=[_bar(0, open=100.0, high=101.0, low=99.0, close=100.0), _bar(1, open=102.0, high=103.0, low=101.0, close=102.5)])
            return OHLCV(symbol=symbol, interval=interval, bars=[
                OHLCVBar(timestamp=_GENERATED_AT + timedelta(days=5), open=100.0, high=101.0, low=99.0, close=100.0, volume=1000.0),
                OHLCVBar(timestamp=_GENERATED_AT + timedelta(days=6), open=105.0, high=106.0, low=104.0, close=105.5, volume=1000.0),
            ])

    results = advance_pending_paper_orders(engine, provider=_MultiProvider())
    by_symbol = {r.symbol: r for r in results}

    assert by_symbol["AAA"].bars_processed == 1
    assert engine.store.get_open_position("AAA") is not None

    assert by_symbol["BBB"].bars_processed == 0
    assert by_symbol["BBB"].error is None  # held back gracefully, never an exception
    assert by_symbol["BBB"].skipped_reason is not None
    assert "already holds" in by_symbol["BBB"].skipped_reason
    assert engine.store.get_open_position("BBB") is None
    assert engine.store.get_pending_order("BBB") is not None  # still PENDING, untouched -- not lost


def test_advance_lets_the_held_back_symbol_fill_once_the_open_position_closes(engine):
    """Follow-up to the above: once AAA's position closes (a later
    advance() call reaches a stop/target), a SUBSEQUENT call must let
    BBB's still-PENDING order fill normally -- proves it retries, rather
    than being permanently stuck."""
    engine.submit_signal(_signal(symbol="AAA", stop_price=95.0, target_price=110.0))
    engine.submit_signal(_signal(symbol="BBB", generated_at=_GENERATED_AT + timedelta(days=5)))

    class _Round1Provider:
        def fetch_ohlcv(self, symbol, *, period="1y", interval="1d"):
            if symbol == "AAA":
                return OHLCV(symbol=symbol, interval=interval, bars=[
                    _bar(0, open=100.0, high=101.0, low=99.0, close=100.0),
                    _bar(1, open=101.0, high=101.5, low=100.5, close=101.0),  # fills AAA
                    _bar(2, open=100.0, high=120.0, low=100.0, close=115.0),  # TARGET HIT -- closes AAA
                ])
            return OHLCV(symbol=symbol, interval=interval, bars=[
                OHLCVBar(timestamp=_GENERATED_AT + timedelta(days=5), open=100.0, high=101.0, low=99.0, close=100.0, volume=1000.0),
            ])  # BBB has no genuinely new bar yet in round 1

    advance_pending_paper_orders(engine, provider=_Round1Provider())
    assert engine.store.get_open_position("AAA") is None  # closed via target hit
    assert engine.store.get_pending_order("BBB") is not None  # still pending after round 1

    class _Round2Provider:
        def fetch_ohlcv(self, symbol, *, period="1y", interval="1d"):
            return OHLCV(symbol=symbol, interval=interval, bars=[
                OHLCVBar(timestamp=_GENERATED_AT + timedelta(days=5), open=100.0, high=101.0, low=99.0, close=100.0, volume=1000.0),
                OHLCVBar(timestamp=_GENERATED_AT + timedelta(days=6), open=105.0, high=106.0, low=104.0, close=105.5, volume=1000.0),
            ])

    results = advance_pending_paper_orders(engine, provider=_Round2Provider())
    by_symbol = {r.symbol: r for r in results}
    assert by_symbol["BBB"].bars_processed == 1
    assert engine.store.get_open_position("BBB") is not None  # now filled -- no longer held back


def test_advance_isolates_one_symbols_provider_failure_from_the_rest(engine):
    engine.submit_signal(_signal(symbol="GOOD"))
    engine.submit_signal(_signal(symbol="BAD"))

    class _FlakyProvider:
        def fetch_ohlcv(self, symbol, *, period="1y", interval="1d"):
            if symbol == "BAD":
                raise RuntimeError("simulated provider outage")
            return OHLCV(symbol=symbol, interval=interval, bars=[_bar(1, open=103.0, high=104.0, low=102.0, close=103.5)])

    results = advance_pending_paper_orders(engine, provider=_FlakyProvider())
    by_symbol = {r.symbol: r for r in results}
    assert by_symbol["GOOD"].bars_processed == 1
    assert by_symbol["GOOD"].error is None
    assert by_symbol["BAD"].error is not None
    assert "simulated provider outage" in by_symbol["BAD"].error
    assert engine.store.get_open_position("GOOD") is not None  # unaffected by BAD's failure


# --- fail-closed on an unresolvable baseline ------------------------------------


def test_advance_skips_a_symbol_with_no_resolvable_baseline_fail_closed(engine):
    """Pathological/defensive case: a symbol appears to have an OPEN
    position (so it's a candidate for advancing) but genuinely has no
    baseline timestamp available -- must be skipped, never treated as
    "everything is new"."""
    from paper.models import Position, PositionStatus

    # Directly inject an OPEN position with no corresponding bar_cursor row and no
    # resolvable pending order/signal -- simulates data that should be structurally
    # impossible via the normal engine API, exercised here purely to prove the guard.
    engine.store.save_position(Position(
        position_id="p1", symbol="GHOST", status=PositionStatus.OPEN, signal_id="does-not-exist",
        entry_order_id="o1", entry_fill_id="f1", entry_time=_GENERATED_AT, entry_price=100.0,
        quantity=1, stop_price=95.0, target_price=110.0,
    ))

    provider = _FakeProvider([_bar(0, open=100.0, high=101.0, low=99.0, close=100.0)])
    results = advance_pending_paper_orders(engine, provider=provider)

    ghost_result = next(r for r in results if r.symbol == "GHOST")
    assert ghost_result.bars_processed == 0
    assert ghost_result.skipped_reason is not None
    assert "no safe baseline" in ghost_result.skipped_reason
