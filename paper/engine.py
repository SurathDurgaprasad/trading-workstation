"""The stateful paper-trading service: Signal -> RiskEngine -> RiskDecision
-> (reject | PaperOrder -> PaperFill -> Position -> Trade), all persisted,
all journaled. Two public entry points:

  submit_signal(signal)               -- a new signal arrived
  process_bar(symbol, bar)            -- a new bar arrived (fills pending
                                          orders, checks open positions for
                                          stop/target)

This split (vs. the backtester's single monolithic loop) is what a
live/streaming caller actually needs: signals and bars arrive as separate
events, not as one pre-known DataFrame. Historical replay (paper/replay.py)
drives both methods in the same chronological order the backtester uses,
over the same cached data — but nothing here duplicates the backtester's
fill/exit math: check_exit/close_trade/OpenPosition come directly from
backtesting.execution (Phase 6 promoted them to public for exactly this).

Phase 7A adds continuous-bar-ingestion guarantees directly to process_bar()
so EVERY caller gets them for free — historical replay, PaperSession
(paper/session.py), and the MCP submit_paper_market_bar_tool alike:

  - duplicate bars (same symbol, same timestamp as the last one processed)
    are a no-op, not an error — resubmission is treated like Signal
    idempotency (spec §6).
  - a bar strictly OLDER than the last processed one raises
    OutOfOrderBarError rather than silently reordering history (spec §7).
  - the per-symbol "last processed bar timestamp" is persisted (bar_cursor
    table) so both guarantees, and PaperSession's resume-after-restart,
    survive a process restart — not just an in-memory Python object.
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum

import pandas as pd

from backtesting.costs import CostModel
from backtesting.execution import EXECUTION_MODEL_VERSION, OpenPosition, check_exit, close_trade
from backtesting.trade import ExitReason
from paper.errors import OutOfOrderBarError
from paper.models import (
    FillKind,
    JournalEntry,
    JournalOutcome,
    OrderStatus,
    PaperFill,
    PaperOrder,
    Position,
    PositionStatus,
)
from paper.store import PaperStore
from risk.account import new_account
from risk.engine import RiskEngine
from strategy.signal import Signal

logger = logging.getLogger(__name__)

# Purely observational (spec §8 — "do not invent market-calendar logic"):
# flags an unusually large time jump between consecutive bars for the same
# symbol so it's visible in logs. NOT a real trading calendar (knows nothing
# about weekends/holidays specifically) and NEVER rejects a bar on its own —
# only OutOfOrderBarError (a bar going BACKWARDS in time) does that.
_GAP_WARNING_THRESHOLD = timedelta(days=10)


def _new_id() -> str:
    # Deliberately NOT content-derived (unlike Signal.stable_id()) — these
    # identify individual EVENTS (an order, a fill), where uniqueness is
    # what matters, not reproducibility. Spec §17 explicitly allows this:
    # "random UUIDs may differ, but deterministic business values must not."
    return uuid.uuid4().hex


def _naive(ts: datetime) -> datetime:
    """Strips tzinfo so bar timestamps compare/store consistently regardless
    of whether the data provider returned tz-aware or tz-naive values — same
    normalization market/context.py already applies to `as_of`."""
    return ts.replace(tzinfo=None) if ts.tzinfo is not None else ts


class BarOutcome(str, Enum):
    PROCESSED = "PROCESSED"
    DUPLICATE_SKIPPED = "DUPLICATE_SKIPPED"


@dataclass
class Bar:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0  # OHLCV-complete (spec §2); unused by fill/exit logic today


class PaperTradingEngine:
    def __init__(
        self,
        store: PaperStore,
        *,
        risk_engine: RiskEngine | None = None,
        cost_model: CostModel | None = None,
        initial_capital: float = 100_000.0,
        max_holding_bars: int | None = None,
    ):
        self.store = store
        self.risk_engine = risk_engine or RiskEngine()
        self.cost_model = cost_model or CostModel()
        # Explicit opt-in, default OFF (None = unlimited hold, byte-for-byte
        # the same behavior as before this parameter existed): the mission's
        # own position lifecycle definition names STOP/TARGET/EXIT/EXPIRY as
        # distinct terminal states, but this engine previously had no
        # EXPIRY at all -- a real position could stay OPEN forever in
        # continuous unattended operation (`schedule loop --paper-execute`)
        # if it never happens to hit its stop or target. When set, a
        # position open for >= this many processed bars is force-closed at
        # that bar's close with ExitReason.EXPIRED, mirroring the existing
        # --horizon-bars concept predictions.tracker.py already applies to
        # unresolved PREDICTIONS (a separate, unrelated concept -- this is
        # for real OPEN positions).
        self.max_holding_bars = max_holding_bars

        account = store.get_account()
        if account is None:
            account = new_account(initial_capital)
            store.save_account(account)
        self.account = account

    # -- signal submission -----------------------------------------------------

    def submit_signal(self, signal: Signal, *, strategy_version: str = "1.0") -> JournalEntry:
        """Idempotent: resubmitting the same Signal (same stable_id()) never
        creates a second order/journal row — the existing result is
        returned unchanged (spec §8)."""
        signal_id = signal.stable_id()

        existing = self.store.find_journal_entry_by_signal_id(signal_id)
        if existing is not None:
            return existing

        with self.store.transaction():
            self.store.save_signal(signal, strategy_version=strategy_version)

            decision = self.risk_engine.evaluate(signal, self.account)
            risk_decision_id = _new_id()
            self.store.save_risk_decision(
                risk_decision_id, signal_id, decision, risk_config_version=self.risk_engine.config.version_id()
            )

            now = datetime.now(timezone.utc)
            base_journal_fields = dict(
                journal_entry_id=_new_id(),
                signal_id=signal_id,
                symbol=signal.symbol,
                risk_decision_id=risk_decision_id,
                strategy_name=signal.strategy_name,
                strategy_version=strategy_version,
                risk_config_version=self.risk_engine.config.version_id(),
                execution_model_version=EXECUTION_MODEL_VERSION,
                created_at=now,
                updated_at=now,
            )

            # Step 6: one open position per symbol. RiskEngine's own
            # POSITION_ALREADY_OPEN veto only fires once account.open_positions
            # is incremented — which happens at FILL time, not order-creation
            # time. A signal arriving while an order is still PENDING (not yet
            # filled) would slip past that check, so it's enforced explicitly
            # here too, at the paper-engine level.
            already_active = (
                self.store.get_pending_order(signal.symbol) is not None
                or self.store.get_open_position(signal.symbol) is not None
            )

            if not decision.approved:
                journal = JournalEntry(order_id=None, position_id=None, trade_id=None, outcome=JournalOutcome.REJECTED, **base_journal_fields)
            elif already_active:
                journal = JournalEntry(order_id=None, position_id=None, trade_id=None, outcome=JournalOutcome.SKIPPED_ALREADY_ACTIVE, **base_journal_fields)
            else:
                order = PaperOrder(
                    order_id=_new_id(),
                    signal_id=signal_id,
                    symbol=signal.symbol,
                    side=signal.side,
                    quantity=decision.position_size.quantity,
                    requested_price=signal.reference_price,
                    status=OrderStatus.PENDING,
                    created_at=now,
                    stop_price=signal.stop_price,
                    target_price=signal.target_price,
                )
                self.store.save_order(order)
                journal = JournalEntry(order_id=order.order_id, position_id=None, trade_id=None, outcome=JournalOutcome.APPROVED_PENDING, **base_journal_fields)

            self.store.save_journal_entry(journal)
            return journal

    # -- bar processing ----------------------------------------------------------

    def process_bar(self, symbol: str, bar: Bar) -> BarOutcome:
        """Advance time for `symbol` by one bar: check any OPEN position's
        stop/target against this bar (same conservative same-bar-ambiguity
        rule as the backtester), then fill any PENDING order at this bar's
        open. At most one action per call — matches the backtester's
        one-position-per-symbol, one-action-per-bar model.

        Phase 7A: idempotent and order-preserving over repeated/out-of-order
        calls. A bar whose timestamp exactly repeats the last one processed
        for `symbol` is a no-op (BarOutcome.DUPLICATE_SKIPPED) — safe to
        call again with the identical bar, e.g. after a retried delivery. A
        bar strictly OLDER than the last one processed raises
        OutOfOrderBarError instead of silently reordering history.
        """
        incoming_ts = _naive(bar.timestamp)

        with self.store.transaction():
            last_ts = self.store.get_last_bar_timestamp(symbol)
            if last_ts is not None:
                if incoming_ts == last_ts:
                    return BarOutcome.DUPLICATE_SKIPPED
                if incoming_ts < last_ts:
                    raise OutOfOrderBarError(symbol=symbol, incoming_timestamp=incoming_ts, last_processed_timestamp=last_ts)
                if incoming_ts - last_ts > _GAP_WARNING_THRESHOLD:
                    logger.warning(
                        "Large gap between consecutive bars for %s: %s -> %s (%s). "
                        "Not rejected — this is an observational check only, not a market calendar.",
                        symbol, last_ts, incoming_ts, incoming_ts - last_ts,
                    )

            self.account.roll_to_day(bar.timestamp.date())

            open_position = self.store.get_open_position(symbol)
            if open_position is not None:
                self._process_open_position(open_position, bar)
            else:
                pending_order = self.store.get_pending_order(symbol)
                if pending_order is not None:
                    new_position = self._fill_pending_order(pending_order, bar)
                    # The bar that just filled this order must ALSO be
                    # checked against the new stop/target — matches the
                    # backtester exactly: entry uses bar i+1's open, and the
                    # very next backtester loop iteration (i+1) checks exit
                    # using that same bar's full OHLC. Skipping this delays
                    # a legitimate same-bar exit by one bar (found via real
                    # AAPL replay diverging from the backtester — Phase 6).
                    self._process_open_position(new_position, bar)

            # Always persisted, even when this bar had nothing to do for
            # `symbol` (no open position, no pending order) — previously
            # only saved on the two branches above, which meant an
            # in-memory-only roll_to_day() (daily_start_equity reset) could
            # be lost if the process were killed before a later bar
            # happened to touch a position. Found while hardening the
            # restart guarantee for Phase 7A's continuous ingestion.
            self.store.save_account(self.account)
            self.store.set_last_bar_timestamp(symbol, incoming_ts)
            return BarOutcome.PROCESSED

    def close_at_end_of_data(self, symbol: str, bar: Bar) -> None:
        """Mirrors the backtester's end-of-data forced close — any position
        still open when historical replay data runs out is closed at the
        last bar's close, reason END_OF_DATA."""
        with self.store.transaction():
            open_position = self.store.get_open_position(symbol)
            if open_position is None:
                return
            self._close_position(open_position, exit_price_override=bar.close, exit_time=bar.timestamp, is_end_of_data=True)
            self.store.save_account(self.account)

    # -- internals ------------------------------------------------------------------

    def _fill_pending_order(self, order: PaperOrder, bar: Bar) -> Position:
        entry_price = self.cost_model.slippage_adjusted_price(price=bar.open, side=order.side, is_entry=True)
        entry_cost = self.cost_model.cost_for_fill(notional=entry_price * order.quantity)

        fill = PaperFill(
            fill_id=_new_id(), order_id=order.order_id, symbol=order.symbol, quantity=order.quantity,
            fill_price=entry_price, fees=entry_cost, slippage_amount=abs(entry_price - bar.open) * order.quantity,
            timestamp=bar.timestamp, fill_kind=FillKind.ENTRY,
        )
        self.store.save_fill(fill)

        filled_order = order.model_copy(update={"status": OrderStatus.FILLED})
        self.store.update_order(filled_order)

        position = Position(
            position_id=_new_id(), symbol=order.symbol, status=PositionStatus.OPEN, signal_id=order.signal_id,
            entry_order_id=order.order_id, entry_fill_id=fill.fill_id, entry_time=bar.timestamp,
            entry_price=entry_price, quantity=order.quantity, stop_price=order.stop_price, target_price=order.target_price,
        )
        self.store.save_position(position)

        self.account.open_position(quantity=order.quantity, entry_price=entry_price, entry_cost=entry_cost)

        journal = self.store.find_journal_entry_by_signal_id(order.signal_id)
        if journal is not None:
            self.store.update_journal_entry(
                journal.model_copy(update={"position_id": position.position_id, "outcome": JournalOutcome.APPROVED_FILLED_OPEN, "updated_at": bar.timestamp})
            )

        return position

    def _process_open_position(self, position: Position, bar: Bar) -> None:
        self.account.mark_to_market(bar.close)

        open_position = self._to_open_position(position)
        bar_series = _bar_to_series(bar)
        exit_outcome = check_exit(open_position, bar_series)
        if exit_outcome is not None:
            exit_price, exit_reason = exit_outcome
            self._close_position(position, exit_price_override=exit_price, exit_time=bar.timestamp, exit_reason_override=exit_reason)
            return

        if self.max_holding_bars is None:
            return  # unlimited hold -- default, unchanged behavior

        bars_held = position.bars_held + 1
        if bars_held >= self.max_holding_bars:
            self._close_position(
                position, exit_price_override=bar.close, exit_time=bar.timestamp, exit_reason_override=ExitReason.EXPIRED,
            )
            return

        self.store.update_position(position.model_copy(update={"bars_held": bars_held}))

    def _close_position(
        self,
        position: Position,
        *,
        exit_price_override: float,
        exit_time: datetime,
        exit_reason_override=None,
        is_end_of_data: bool = False,
    ) -> None:
        open_position = self._to_open_position(position)
        exit_reason = ExitReason.END_OF_DATA if is_end_of_data else exit_reason_override
        # STOP/TARGET exit at an exact, pre-agreed price level -- no
        # slippage applied, matching this engine's existing, unmodified
        # design. END_OF_DATA and EXPIRED both close at the bar's raw
        # market CLOSE price (a forced exit, not a level the position was
        # resting on) -- slippage-adjusted the same way, for the same
        # reason END_OF_DATA already was.
        apply_slippage = is_end_of_data or exit_reason == ExitReason.EXPIRED
        exit_price = self.cost_model.slippage_adjusted_price(
            price=exit_price_override, side=open_position.signal.side, is_entry=False
        ) if apply_slippage else exit_price_override

        trade = close_trade(
            open_position, exit_price=exit_price, exit_time=exit_time, exit_reason=exit_reason,
            symbol=position.symbol, cost_model=self.cost_model,
        )
        exit_cost = self.cost_model.cost_for_fill(notional=exit_price * position.quantity)

        exit_fill = PaperFill(
            fill_id=_new_id(), order_id=position.entry_order_id, symbol=position.symbol, quantity=position.quantity,
            fill_price=exit_price, fees=exit_cost, slippage_amount=abs(exit_price - exit_price_override) * position.quantity,
            timestamp=exit_time, fill_kind=FillKind.EXIT,
        )
        self.store.save_fill(exit_fill)

        trade_id = _new_id()
        self.store.save_trade(trade, position_id=position.position_id, trade_id=trade_id, execution_model_version=EXECUTION_MODEL_VERSION)

        closed_position = position.model_copy(
            update={
                "status": PositionStatus.CLOSED, "exit_fill_id": exit_fill.fill_id, "exit_time": exit_time,
                "exit_price": exit_price, "exit_reason": exit_reason, "trade_id": trade_id,
            }
        )
        self.store.update_position(closed_position)

        self.account.close_position(exit_price=exit_price, exit_cost=exit_cost, net_pnl=trade.net_pnl)

        journal = self.store.find_journal_entry_by_signal_id(position.signal_id)
        if journal is not None:
            self.store.update_journal_entry(
                journal.model_copy(update={"trade_id": trade_id, "outcome": JournalOutcome.APPROVED_FILLED_CLOSED, "updated_at": exit_time})
            )

    def _to_open_position(self, position: Position) -> OpenPosition:
        signal = self.store.get_signal(position.signal_id)
        assert signal is not None, f"Position {position.position_id} references a missing signal {position.signal_id}"
        return OpenPosition(
            signal=signal, entry_time=position.entry_time, entry_price=position.entry_price,
            quantity=position.quantity, stop_price=position.stop_price, target_price=position.target_price,
        )


def _bar_to_series(bar: Bar) -> pd.Series:
    return pd.Series({"open": bar.open, "high": bar.high, "low": bar.low, "close": bar.close})
