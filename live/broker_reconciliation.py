"""Phase 13 §9 — rehearses the eventual "local state vs. real broker state"
check using the existing paper.reconciliation.ReconciliationIssue /
ReconciliationReport SHAPES (reused directly, not duplicated) but a NEW
comparison: EXPECTED STATE (our own PaperTradingEngine) against LOCAL
ACCOUNT STATE as reported by a BrokerAdapter (a MockBrokerAdapter for this
phase; a real DhanBrokerAdapter in a future phase, same function,
unchanged).

Positions/trades are matched by CONTENT (symbol, price, quantity, exit
reason) rather than by our internal IDs — a real broker has no knowledge
of, and no reason to agree with, our internal position_id/trade_id scheme.
This is deliberately a stricter, more realistic matching strategy than
paper/reconciliation.py's own internal-consistency checks, which CAN use
internal IDs because both sides of that comparison come from the same
store.

Never repairs anything — only detects and reports, the same posture
paper/reconciliation.py already established.
"""

from paper.engine import PaperTradingEngine
from paper.reconciliation import ReconciliationIssue, ReconciliationReport

_PNL_TOLERANCE = 1e-6


def reconcile_against_broker(engine: PaperTradingEngine, broker) -> ReconciliationReport:
    issues: list[ReconciliationIssue] = []

    local_positions = {p.symbol: p for p in engine.store.list_positions() if p.status.value == "OPEN"}
    broker_positions = {p.symbol: p for p in broker.list_positions()}

    for symbol, local_pos in local_positions.items():
        broker_pos = broker_positions.get(symbol)
        if broker_pos is None:
            issues.append(ReconciliationIssue(check="missing_position_at_broker", detail=f"{symbol}: open locally (qty={local_pos.quantity}) but broker reports no position"))
            continue
        if broker_pos.quantity != local_pos.quantity:
            issues.append(ReconciliationIssue(check="quantity_mismatch", detail=f"{symbol}: local qty={local_pos.quantity} broker qty={broker_pos.quantity}"))
        if abs(broker_pos.entry_price - local_pos.entry_price) > _PNL_TOLERANCE:
            issues.append(ReconciliationIssue(check="price_mismatch", detail=f"{symbol}: local entry={local_pos.entry_price} broker entry={broker_pos.entry_price}"))

    for symbol in broker_positions:
        if symbol not in local_positions:
            issues.append(ReconciliationIssue(check="unexpected_position_at_broker", detail=f"{symbol}: broker reports an open position we have no local record of"))

    local_funds = engine.account
    broker_funds = broker.get_funds()
    if abs(local_funds.cash - broker_funds.cash) > _PNL_TOLERANCE:
        issues.append(ReconciliationIssue(check="cash_mismatch", detail=f"local cash={local_funds.cash} broker cash={broker_funds.cash}"))

    def trade_key(t):
        return (t.symbol, round(t.entry_price, 4), round(t.exit_price, 4), t.quantity, t.exit_reason.value)

    local_trade_keys = [trade_key(t) for t in engine.store.list_trades()]
    broker_trade_keys = [trade_key(t) for t in broker.list_fills()]

    local_counts: dict = {}
    for k in local_trade_keys:
        local_counts[k] = local_counts.get(k, 0) + 1
    broker_counts: dict = {}
    for k in broker_trade_keys:
        broker_counts[k] = broker_counts.get(k, 0) + 1

    for k, count in local_counts.items():
        broker_count = broker_counts.get(k, 0)
        if broker_count < count:
            issues.append(ReconciliationIssue(check="trade_missing_at_broker", detail=f"trade {k} recorded locally {count}x but broker reports it {broker_count}x"))
    for k, count in broker_counts.items():
        local_count = local_counts.get(k, 0)
        if count > local_count:
            issues.append(ReconciliationIssue(check="duplicate_trade_at_broker", detail=f"trade {k} reported by broker {count}x but recorded locally only {local_count}x"))

    return ReconciliationReport(ok=not issues, issues=issues)
