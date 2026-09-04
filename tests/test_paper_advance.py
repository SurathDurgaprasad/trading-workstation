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


def test_advance_reports_the_real_partial_count_when_a_later_bar_in_the_loop_fails(engine, monkeypatch):
    """Real bug found via self-audit: bars before a mid-loop failure are
    ALREADY durably committed (each process_bar() call is its own
    transaction) -- the AdvanceResult must report that real count, not a
    hardcoded 0, or the audit trail understates what genuinely happened."""
    engine.submit_signal(_signal())
    provider = _FakeProvider([
        _bar(1, open=103.0, high=104.0, low=102.0, close=103.5),  # succeeds
        _bar(2, open=104.0, high=105.0, low=103.0, close=104.5),  # raises
        _bar(3, open=105.0, high=106.0, low=104.0, close=105.5),  # never reached
    ])

    real_process_bar = engine.process_bar
    calls = {"n": 0}

    def _flaky_process_bar(symbol, bar):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("simulated transient failure on the second bar")
        return real_process_bar(symbol, bar)

    monkeypatch.setattr(engine, "process_bar", _flaky_process_bar)

    results = advance_pending_paper_orders(engine, provider=provider)

    assert len(results) == 1
    assert results[0].bars_processed == 1  # NOT 0 -- the first bar genuinely committed before the failure
    assert results[0].error is not None
    assert "simulated transient failure" in results[0].error
    # Prove the first bar's effect is genuinely persisted, not just claimed:
    assert engine.store.get_last_bar_timestamp("TEST") == _GENERATED_AT + timedelta(days=1)


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


# --- account-level risk halts (weekend hardening audit) -------------------------


def _drive_account_into_max_drawdown(engine, risk_config, *, start_day: int = 1) -> int:
    """Repeatedly submits, fills, and hard-stops-out symbol "DRAWDOWN_X" until
    the account's current_drawdown_pct reaches risk_config.max_drawdown_pct.
    Returns the day offset the caller should continue from. Raises if the
    configured risk/drawdown combination genuinely cannot reach it within a
    bounded number of cycles (a test-authoring error, not a production one)."""
    day = start_day
    for _ in range(30):
        if engine.account.current_drawdown_pct >= risk_config.max_drawdown_pct:
            return day
        signal = _signal(
            symbol="DRAWDOWN_X", generated_at=_GENERATED_AT + timedelta(days=day),
            reference_price=100.0, stop_price=90.0, target_price=300.0, risk_reward=20.0,
        )
        journal = engine.submit_signal(signal)
        if journal.outcome != JournalOutcome.APPROVED_PENDING:
            raise AssertionError(f"expected APPROVED_PENDING while driving drawdown, got {journal.outcome} -- test setup needs adjustment")
        engine.process_bar("DRAWDOWN_X", Bar(timestamp=_GENERATED_AT + timedelta(days=day, hours=1), open=100.0, high=101.0, low=99.5, close=100.5))
        engine.process_bar("DRAWDOWN_X", Bar(timestamp=_GENERATED_AT + timedelta(days=day, hours=2), open=100.0, high=100.5, low=80.0, close=85.0))
        day += 1
    raise AssertionError(f"never reached max_drawdown_pct={risk_config.max_drawdown_pct} after 30 cycles -- test setup needs adjustment")


def test_advance_holds_back_a_stale_pending_order_when_the_account_is_in_max_drawdown():
    """Real bug found via adversarial audit, reproduced before this guard
    existed: a PENDING order is risk-evaluated exactly ONCE, at submission
    time -- process_bar()'s fill path never re-checks anything, and
    Account.open_position() itself performs NO risk validation at all.
    Combined with advance()'s own hold-back/retry mechanism (which can
    leave an approval outstanding indefinitely while OTHER trades cycle
    through the account's one position slot), a symbol approved while the
    account was healthy could fill unconditionally even after the account
    has since crossed max_drawdown_pct -- silently bypassing the exact
    circuit breaker that correctly rejects a brand-new signal in that same
    moment (the blueprint's own "Critical: All trading suspended" tier,
    defeated by nothing more than order timing)."""
    from risk.config import RiskConfig
    from risk.engine import RiskEngine

    risk_config = RiskConfig(risk_per_trade_pct=2.0, max_drawdown_pct=10.0, consecutive_loss_hard_limit=100)
    engine = PaperTradingEngine(PaperStore(":memory:"), risk_engine=RiskEngine(risk_config), initial_capital=20_000.0)

    # Approved while the account is still perfectly healthy.
    signal_b = _signal(symbol="B", generated_at=_GENERATED_AT, reference_price=50.0, stop_price=45.0, target_price=200.0, risk_reward=20.0)
    journal_b = engine.submit_signal(signal_b)
    assert journal_b.outcome == JournalOutcome.APPROVED_PENDING

    day = _drive_account_into_max_drawdown(engine, risk_config)
    assert engine.account.current_drawdown_pct >= risk_config.max_drawdown_pct

    # Sanity check: a BRAND NEW signal is correctly rejected right now.
    signal_c = _signal(symbol="C", generated_at=_GENERATED_AT + timedelta(days=day), reference_price=10.0, stop_price=9.0, target_price=30.0, risk_reward=20.0)
    journal_c = engine.submit_signal(signal_c)
    assert journal_c.outcome == JournalOutcome.REJECTED

    # THE FIX: B's stale, already-approved PENDING order must NOT fill either.
    provider = _FakeProvider([OHLCVBar(timestamp=_GENERATED_AT + timedelta(days=day + 1), open=50.0, high=50.5, low=49.5, close=50.2, volume=1000.0)])
    results = advance_pending_paper_orders(engine, provider=provider)

    b_result = next(r for r in results if r.symbol == "B")
    assert b_result.bars_processed == 0
    assert b_result.skipped_reason is not None
    assert "MAX_DRAWDOWN" in b_result.skipped_reason
    assert engine.store.get_open_position("B") is None  # never filled
    assert engine.store.get_pending_order("B") is not None  # still PENDING, not silently dropped either


def test_advance_still_manages_an_existing_open_position_during_a_risk_halt():
    """The fix above must NOT also block risk MANAGEMENT of an already-open
    position during a halt -- refusing to check its stop/target while the
    account is in max drawdown would be a worse, new bug (an unmonitored
    real position). Only a bare PENDING order (a NEW capital commitment)
    is held back."""
    from risk.config import RiskConfig
    from risk.engine import RiskEngine

    risk_config = RiskConfig(risk_per_trade_pct=2.0, max_drawdown_pct=10.0, consecutive_loss_hard_limit=100)
    engine = PaperTradingEngine(PaperStore(":memory:"), risk_engine=RiskEngine(risk_config), initial_capital=20_000.0)

    # Open a real position in "B" BEFORE the account enters max drawdown.
    signal_b = _signal(symbol="B", generated_at=_GENERATED_AT, reference_price=50.0, stop_price=45.0, target_price=200.0, risk_reward=20.0)
    engine.submit_signal(signal_b)
    engine.process_bar("B", Bar(timestamp=_GENERATED_AT + timedelta(hours=1), open=50.0, high=50.5, low=49.5, close=50.2))
    assert engine.store.get_open_position("B") is not None

    # Drive the account (via a DIFFERENT symbol) into max drawdown -- but B's
    # own position stays open throughout (single-position engine: submitting
    # for DRAWDOWN_X would itself be blocked while B is open, so drive
    # drawdown by closing B out first is not an option here -- instead,
    # directly force the account's own drawdown state to prove the
    # monitoring-continues guarantee in isolation).
    engine.account.peak_equity = engine.account.equity / (1 - risk_config.max_drawdown_pct / 100 - 0.01)
    assert engine.account.current_drawdown_pct >= risk_config.max_drawdown_pct

    # B must still be monitored for its stop/target -- advance() must not
    # skip it just because the account is halted.
    provider = _FakeProvider([OHLCVBar(timestamp=_GENERATED_AT + timedelta(days=1), open=50.0, high=50.5, low=44.0, close=44.5, volume=1000.0)])
    results = advance_pending_paper_orders(engine, provider=provider)

    b_result = next(r for r in results if r.symbol == "B")
    assert b_result.skipped_reason is None
    assert b_result.bars_processed == 1
    assert engine.store.get_open_position("B") is None  # correctly stopped out, not silently left unmonitored


def test_advance_holds_back_a_stale_pending_order_on_max_daily_loss():
    """The same fix, exercised via MAX_DAILY_LOSS specifically -- not just
    MAX_DRAWDOWN. account_level_halt_reasons() covers all three
    account-level circuit breakers (daily loss, drawdown, consecutive-loss
    hard limit) with one shared method, but each deserves its own direct
    coverage rather than relying on the drawdown test alone to imply the
    others are wired correctly too."""
    from risk.config import RiskConfig
    from risk.engine import RiskEngine

    risk_config = RiskConfig(max_daily_loss_pct=3.0)
    engine = PaperTradingEngine(PaperStore(":memory:"), risk_engine=RiskEngine(risk_config), initial_capital=20_000.0)

    signal_b = _signal(symbol="B", generated_at=_GENERATED_AT, reference_price=50.0, stop_price=45.0, target_price=200.0, risk_reward=20.0)
    journal_b = engine.submit_signal(signal_b)
    assert journal_b.outcome == JournalOutcome.APPROVED_PENDING

    # Directly force a same-day loss beyond the 3% threshold (equivalent to
    # what several real intraday losing trades would produce) -- isolates
    # this specific halt condition without needing a multi-cycle drive.
    engine.account.daily_start_equity = engine.account.equity / (1 - risk_config.max_daily_loss_pct / 100 - 0.01)
    assert engine.account.daily_pnl < 0
    assert -engine.account.daily_pnl >= engine.account.daily_start_equity * risk_config.max_daily_loss_pct / 100

    # Sanity check: a BRAND NEW signal is correctly rejected right now.
    signal_c = _signal(symbol="C", generated_at=_GENERATED_AT + timedelta(days=1), reference_price=10.0, stop_price=9.0, target_price=30.0, risk_reward=20.0)
    journal_c = engine.submit_signal(signal_c)
    assert journal_c.outcome == JournalOutcome.REJECTED

    provider = _FakeProvider([OHLCVBar(timestamp=_GENERATED_AT + timedelta(days=1), open=50.0, high=50.5, low=49.5, close=50.2, volume=1000.0)])
    results = advance_pending_paper_orders(engine, provider=provider)

    b_result = next(r for r in results if r.symbol == "B")
    assert b_result.bars_processed == 0
    assert b_result.skipped_reason is not None
    assert "MAX_DAILY_LOSS" in b_result.skipped_reason
    assert engine.store.get_open_position("B") is None


def test_advance_holds_back_a_stale_pending_order_when_the_kill_switch_is_active(tmp_path, engine):
    """Real bug found via adversarial audit, reproduced before this guard
    existed: advance_pending_paper_orders() had NO kill-switch awareness
    at all -- unlike _bridge_to_paper_execution (which checks
    state_store.is_kill_switch_active() before every NEW submission), the
    fill path this function drives had no equivalent check whatsoever. A
    symbol approved and left PENDING BEFORE the kill switch was activated
    would still fill via advance() afterward, completely bypassing the
    project's own primary emergency stop -- exactly the "Never bypass kill
    switches" rule stated as an absolute, non-negotiable safety boundary."""
    from live.state_store import LiveStateStore

    signal_b = _signal(symbol="B")
    journal_b = engine.submit_signal(signal_b)
    assert journal_b.outcome == JournalOutcome.APPROVED_PENDING

    state_store = LiveStateStore(tmp_path / "state.db")
    state_store.activate_kill_switch(reason="test")

    provider = _FakeProvider([_bar(1, open=100.0, high=101.0, low=99.0, close=100.5)])
    results = advance_pending_paper_orders(engine, provider=provider, state_store=state_store)
    state_store.close()

    b_result = next(r for r in results if r.symbol == "B")
    assert b_result.bars_processed == 0
    assert b_result.skipped_reason is not None
    assert "kill switch" in b_result.skipped_reason.lower()
    assert engine.store.get_open_position("B") is None  # never filled
    assert engine.store.get_pending_order("B") is not None  # still PENDING, not silently dropped


def test_advance_still_manages_an_open_position_while_the_kill_switch_is_active(tmp_path, engine):
    """Same distinction as the risk-halt fix: an active kill switch must
    still block a NEW fill, but must NOT stop monitoring a position that
    is ALREADY open -- refusing to check its stop/target during a kill
    switch would leave a real position unmonitored, a worse, new bug."""
    from live.state_store import LiveStateStore

    engine.submit_signal(_signal(symbol="B"))
    engine.process_bar("B", Bar(timestamp=_GENERATED_AT + timedelta(days=1), open=100.0, high=101.0, low=99.5, close=100.5))
    assert engine.store.get_open_position("B") is not None

    state_store = LiveStateStore(tmp_path / "state.db")
    state_store.activate_kill_switch(reason="test")

    provider = _FakeProvider([_bar(2, open=100.0, high=100.5, low=90.0, close=91.0)])  # hits the 95 stop
    results = advance_pending_paper_orders(engine, provider=provider, state_store=state_store)
    state_store.close()

    b_result = next(r for r in results if r.symbol == "B")
    assert b_result.skipped_reason is None
    assert b_result.bars_processed == 1
    assert engine.store.get_open_position("B") is None  # correctly stopped out, not left unmonitored


def test_advance_kill_switch_check_is_optional_backward_compatible(engine):
    """No state_store supplied (the parameter's default) must behave
    exactly as it did before this parameter existed -- never fabricates a
    kill-switch state it cannot actually observe."""
    engine.submit_signal(_signal(symbol="B"))
    provider = _FakeProvider([_bar(1, open=100.0, high=101.0, low=99.0, close=100.5)])
    results = advance_pending_paper_orders(engine, provider=provider)
    b_result = next(r for r in results if r.symbol == "B")
    assert b_result.skipped_reason is None
    assert engine.store.get_open_position("B") is not None
