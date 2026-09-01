"""Phase 13 §10 — a broker-shaped abstraction, rehearsing the eventual
DhanBrokerAdapter's interface without building anything broker-specific yet
(spec: "Do NOT create DhanBrokerAdapter").

MockBrokerAdapter DELEGATES entirely to the existing PaperTradingEngine —
no execution logic is duplicated. This is the audit's own explicit test:
"the PaperTradingEngine should remain the source of existing paper behavior
unless the audit proves a broker abstraction can be introduced without
duplication" — it can, because every method below is a one-line forward to
a method PaperTradingEngine/PaperStore already has.

The one real gap, stated honestly rather than faked: PaperOrder has no
CANCELLED state in the current engine (a deliberate Phase 6 scope
decision — no order type this project has ever needed to cancel). Rather
than bolt a half-supported cancellation onto paper/ to satisfy this
adapter's shape, cancel_order() raises NotImplementedError with a clear
explanation. A future DhanBrokerAdapter would need real cancellation;
building it here would mean touching paper/store.py's schema for a
capability nothing in this project currently exercises — out of scope for
this phase's "do not blindly refactor" instruction.
"""

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from backtesting.trade import Trade
from paper.engine import PaperTradingEngine
from paper.models import Position
from risk.account import Account
from strategy.signal import Signal


@runtime_checkable
class BrokerAdapter(Protocol):
    def submit_order(self, signal: Signal) -> str:
        """Returns the order's idempotent identity (Signal.stable_id())."""

    def cancel_order(self, signal_id: str) -> bool: ...

    def order_status(self, signal_id: str) -> str | None:
        """The JournalOutcome value for this signal, or None if unknown."""

    def list_fills(self) -> list[Trade]: ...

    def list_positions(self) -> list[Position]:
        """Open positions only."""

    def get_funds(self) -> Account: ...


@dataclass
class MockBrokerAdapter:
    engine: PaperTradingEngine

    def submit_order(self, signal: Signal) -> str:
        journal = self.engine.submit_signal(signal)
        return journal.signal_id

    def cancel_order(self, signal_id: str) -> bool:
        raise NotImplementedError(
            "PaperOrder has no CANCELLED state in the current engine (a deliberate Phase 6 scope decision) -- "
            "cancellation is not supported yet. This deliberately does not fake success."
        )

    def order_status(self, signal_id: str) -> str | None:
        entry = self.engine.store.find_journal_entry_by_signal_id(signal_id)
        return entry.outcome.value if entry else None

    def list_fills(self) -> list[Trade]:
        return self.engine.store.list_trades()

    def list_positions(self) -> list[Position]:
        return [p for p in self.engine.store.list_positions() if p.status.value == "OPEN"]

    def get_funds(self) -> Account:
        return self.engine.account
