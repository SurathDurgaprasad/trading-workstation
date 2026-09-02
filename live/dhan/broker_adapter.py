"""Phase 15 §13/§14 — the disabled real-order-execution surface, plus
read-only account access, both explicitly for Dhan.

Design note (deviation from the Phase 14 report's original proposal,
correcting it against the actual repository rather than forcing the old
design -- per this phase's own instruction §2): Phase 13's
`live.broker.BrokerAdapter` Protocol returns PAPER-shaped types
(`risk.account.Account`, `paper.models.Position`) because `MockBrokerAdapter`
only ever delegated to `PaperTradingEngine`. A real Dhan account's funds/
positions do not map cleanly onto those types without either dropping real
Dhan fields or fabricating paper-only ones (`daily_start_equity`,
`consecutive_losses`, ...) that have no broker equivalent -- forcing that
fit would violate this phase's own §14 instruction to NEVER mix broker and
paper account state. So `DhanAccountReader` below does NOT claim to
implement `BrokerAdapter`; it has its own honestly-typed read methods
(returning live.dhan.rest_client's DhanFundLimit/DhanPosition/DhanHolding),
kept entirely separate from anything paper-shaped. The dashboard/CLI/MCP
render its output under its own "DHAN ACCOUNT" heading, distinct from
"PAPER ACCOUNT".
"""

from dataclasses import dataclass

from live.dhan.rest_client import DhanFundLimit, DhanHolding, DhanPosition, DhanRestClient
from strategy.signal import Signal


class RealOrderPlacementDisabledError(NotImplementedError):
    """Raised unconditionally by every order-mutating method below.

    This is a DELIBERATE safety control, not a missing-feature stub: Phase
    15 forbids real order placement/modification/cancellation outright
    (spec §13/§24). No configuration flag, environment variable, or
    subclass override anywhere in this codebase can make these methods do
    anything other than raise. Enabling real execution is out of scope for
    this phase and, if it ever happens, is a deliberate, separately-
    reviewed Phase 16 decision -- not a flag flip."""


@dataclass
class DhanAccountReader:
    """Read-only real Dhan account access -- funds, positions, holdings.
    Every method is a GET; nothing here can mutate the real account."""

    rest_client: DhanRestClient

    def get_fund_limit(self) -> DhanFundLimit:
        return self.rest_client.get_fund_limit()

    def get_positions(self) -> list[DhanPosition]:
        return self.rest_client.get_positions()

    def get_holdings(self) -> list[DhanHolding]:
        return self.rest_client.get_holdings()


@dataclass
class DisabledDhanOrderExecutor:
    """Rehearses the shape a real order-execution adapter would eventually
    need (spec §13: "you may build a disabled adapter interface"), with
    every method statically incapable of doing anything but raising.
    Deliberately NOT wired into LiveSimPipeline/PaperTradingEngine
    anywhere -- paper execution (the existing, unchanged engine) remains
    the only thing this phase's approved signals can ever reach."""

    def place_order(self, signal: Signal) -> str:
        raise RealOrderPlacementDisabledError("Real order placement is disabled in Phase 15. Paper execution is the only execution path.")

    def modify_order(self, order_id: str, **changes) -> bool:
        raise RealOrderPlacementDisabledError("Real order modification is disabled in Phase 15.")

    def cancel_order(self, order_id: str) -> bool:
        raise RealOrderPlacementDisabledError("Real order cancellation is disabled in Phase 15.")
