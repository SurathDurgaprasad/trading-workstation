"""Deterministic reconciliation checks (spec §11/§27). A failure here means
the persisted state is untrustworthy — this module NEVER attempts to
"repair" anything; it only detects and reports (spec §11: "FAIL LOUDLY. Do
NOT silently repair financial state.")."""

import math

from pydantic import BaseModel, ConfigDict

from paper.store import PaperStore

_PNL_TOLERANCE = 1e-6


class ReconciliationIssue(BaseModel):
    model_config = ConfigDict(frozen=True)
    check: str
    detail: str


class ReconciliationReport(BaseModel):
    model_config = ConfigDict(frozen=True)
    ok: bool
    issues: list[ReconciliationIssue]


def reconcile(store: PaperStore) -> ReconciliationReport:
    issues: list[ReconciliationIssue] = []

    account = store.get_account()
    if account is None:
        issues.append(ReconciliationIssue(check="account_exists", detail="No account row persisted."))
        return ReconciliationReport(ok=False, issues=issues)

    # 1. equity = cash + open-position value (spec §5/§11) — Account's own
    #    computed property already enforces this by construction; re-derive
    #    it independently here from the raw persisted fields so a bug in the
    #    property itself wouldn't hide a discrepancy.
    expected_equity = account.cash + account.open_position_cost_basis + account.unrealized_pnl
    if not math.isclose(account.equity, expected_equity, abs_tol=_PNL_TOLERANCE):
        issues.append(
            ReconciliationIssue(
                check="equity_invariant",
                detail=f"account.equity={account.equity} != cash+position_value={expected_equity}",
            )
        )

    if account.open_position_quantity < 0:
        issues.append(ReconciliationIssue(check="quantity_non_negative", detail=f"open_position_quantity={account.open_position_quantity}"))

    if account.peak_equity < account.equity - _PNL_TOLERANCE:
        issues.append(ReconciliationIssue(check="peak_equity", detail=f"peak_equity={account.peak_equity} < equity={account.equity}"))

    # 2. realized PnL agrees with the trade ledger
    trades = store.list_trades()
    trade_pnl_sum = sum(t.net_pnl for t in trades)
    if not math.isclose(account.realized_pnl, trade_pnl_sum, abs_tol=_PNL_TOLERANCE):
        issues.append(
            ReconciliationIssue(
                check="realized_pnl_matches_trades",
                detail=f"account.realized_pnl={account.realized_pnl} != sum(trade.net_pnl)={trade_pnl_sum}",
            )
        )

    if account.total_trades != len(trades):
        issues.append(
            ReconciliationIssue(
                check="trade_count_matches",
                detail=f"account.total_trades={account.total_trades} != len(trades)={len(trades)}",
            )
        )

    # 3. no orphan fills/positions/trades
    positions = store.list_positions()
    fill_ids = {f["fill_id"] for f in store._fetch_all_json("paper_fills")}
    order_ids = {o["order_id"] for o in store._fetch_all_json("paper_orders")}

    for position in positions:
        if position.entry_fill_id not in fill_ids:
            issues.append(ReconciliationIssue(check="orphan_position_entry_fill", detail=f"position {position.position_id} references missing fill {position.entry_fill_id}"))
        if position.entry_order_id not in order_ids:
            issues.append(ReconciliationIssue(check="orphan_position_entry_order", detail=f"position {position.position_id} references missing order {position.entry_order_id}"))
        if position.exit_fill_id is not None and position.exit_fill_id not in fill_ids:
            issues.append(ReconciliationIssue(check="orphan_position_exit_fill", detail=f"position {position.position_id} references missing exit fill {position.exit_fill_id}"))

    position_ids = {p.position_id for p in positions}
    for trade_id, position_id in store.list_trade_position_ids():
        if position_id not in position_ids:
            issues.append(ReconciliationIssue(check="orphan_trade", detail=f"trade {trade_id} references missing position {position_id}"))

    # 4. no duplicate signal execution (DB UNIQUE constraint already prevents
    #    this at write time; re-verify here as a defense-in-depth read check)
    journal_entries = store.list_journal_entries()
    signal_ids = [j.signal_id for j in journal_entries]
    if len(signal_ids) != len(set(signal_ids)):
        issues.append(ReconciliationIssue(check="duplicate_signal_execution", detail="Multiple journal entries share the same signal_id."))

    return ReconciliationReport(ok=not issues, issues=issues)
