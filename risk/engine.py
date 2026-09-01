import math

from risk.account import Account
from risk.config import RiskConfig
from risk.contracts import Exposure, PositionSize, RiskDecision, RiskSummary, SignalRecord
from risk.veto import VetoReason
from strategy.signal import Side, Signal


class RiskEngine:
    """Pure deterministic Python — no LLM, no I/O, no randomness. Given a
    Signal and the current Account state, decides whether a trade may be
    taken and how large it may be. Never alters entry/stop/target; only
    ever approves, sizes, or rejects (spec §22).

    Fail-closed throughout (spec §18): every branch that cannot establish a
    safe, well-defined trade appends a veto reason rather than defaulting to
    approval. `evaluate()` collects ALL applicable veto reasons before
    returning — never stops at the first one (spec §25, "multiple vetoes").

    Two deliberately DIFFERENT recovery postures, both traced to the
    project's own blueprint (AI_Trading_Platform_Master_Blueprint.docx §6.3)
    rather than invented:

    - Consecutive losses: the blueprint reduces risk-per-trade by 50% for a
      losing streak — it never rejects outright for this rule. A hard reject
      (`consecutive_loss_hard_limit`) still exists as a secondary circuit
      breaker if losses continue even at reduced size, but it is NOT the
      blueprint's mechanism and is off by default (== 2x the soft limit).
      A permanent hard reject here — Phase 4's original behavior — was a
      genuine mismatch with the documented policy, discovered by running a
      real backtest: it left the account permanently halted with no trade
      ever able to execute to produce the win that would reset the streak.

    - Drawdown: the blueprint's "Critical" tier is explicit — "All trading
      suspended... Human intervention required." A hard, non-recovering
      reject is the CORRECT, intended behavior here, not a gap. It is left
      unchanged.
    """

    def __init__(self, config: RiskConfig | None = None):
        self.config = config or RiskConfig()

    def evaluate(self, signal: Signal, account: Account) -> RiskDecision:
        veto_reasons: list[VetoReason] = []

        structurally_valid = True
        if signal.side != Side.LONG:
            veto_reasons.append(VetoReason.INVALID_SIGNAL)
            structurally_valid = False
        if signal.reference_price <= signal.stop_price:
            veto_reasons.append(VetoReason.INVALID_STOP)
            structurally_valid = False
        if signal.target_price <= signal.reference_price:
            veto_reasons.append(VetoReason.INVALID_SIGNAL)
            structurally_valid = False

        if signal.risk_reward <= 0 or signal.risk_reward < self.config.min_risk_reward:
            veto_reasons.append(VetoReason.INVALID_RISK_REWARD)

        if account.open_positions > 0:
            veto_reasons.append(VetoReason.POSITION_ALREADY_OPEN)

        if self._daily_loss_breached(account):
            veto_reasons.append(VetoReason.MAX_DAILY_LOSS)
        if account.current_drawdown_pct >= self.config.max_drawdown_pct:
            veto_reasons.append(VetoReason.MAX_DRAWDOWN)  # intentionally no auto-recovery — blueprint §6.3

        in_loss_recovery = account.consecutive_losses >= self.config.max_consecutive_losses
        if account.consecutive_losses >= self.config.consecutive_loss_hard_limit:
            veto_reasons.append(VetoReason.CONSECUTIVE_LOSS_LIMIT)

        position_size: PositionSize | None = None
        exposure: Exposure | None = None

        requested_quantity = 0

        if structurally_valid:
            risk_per_unit = signal.reference_price - signal.stop_price  # > 0, guaranteed by structurally_valid
            effective_risk_pct = self.config.risk_per_trade_pct
            if in_loss_recovery:
                effective_risk_pct *= self.config.consecutive_loss_risk_multiplier
            risk_budget = account.equity * effective_risk_pct / 100
            quantity = math.floor(risk_budget / risk_per_unit)
            requested_quantity = max(quantity, 0)  # what sizing wanted, before any capital reduction

            if quantity < 1:
                veto_reasons.append(VetoReason.ZERO_POSITION_SIZE)

            if quantity >= 1:
                notional = quantity * signal.reference_price
                if notional > account.cash:
                    quantity = math.floor(account.cash / signal.reference_price)
                    if quantity < 1:
                        veto_reasons.append(VetoReason.INSUFFICIENT_CAPITAL)

            if quantity >= 1:
                notional = quantity * signal.reference_price
                exposure_pct = (notional / account.equity * 100) if account.equity > 0 else float("inf")
                exposure = Exposure(position_notional=notional, account_equity=account.equity, exposure_pct=exposure_pct)
                if exposure_pct > self.config.max_exposure_pct:
                    veto_reasons.append(VetoReason.MAX_EXPOSURE)

                position_size = PositionSize(
                    quantity=quantity,
                    risk_per_unit=risk_per_unit,
                    total_risk=quantity * risk_per_unit,
                    notional_value=notional,
                )

        approved = structurally_valid and position_size is not None and not veto_reasons
        risk_reduced = approved and in_loss_recovery

        risk_amount = position_size.total_risk if position_size else None
        risk_percent = (risk_amount / account.equity * 100) if (risk_amount is not None and account.equity > 0) else None

        return RiskDecision(
            approved=approved,
            position_size=position_size,
            risk_amount=risk_amount,
            risk_percent=risk_percent,
            exposure=exposure,
            veto_reasons=veto_reasons,
            explanation=self._explain(approved, veto_reasons, position_size, risk_reduced),
            risk_reduced=risk_reduced,
            account_equity=account.equity,
            current_drawdown_pct=account.current_drawdown_pct,
            daily_pnl=account.daily_pnl,
            consecutive_losses=account.consecutive_losses,
            requested_quantity=requested_quantity,
            approved_quantity=position_size.quantity if (approved and position_size) else 0,
        )

    def _daily_loss_breached(self, account: Account) -> bool:
        if account.daily_start_equity <= 0:
            return True  # cannot establish a safe reference point -> fail closed
        loss_limit = account.daily_start_equity * self.config.max_daily_loss_pct / 100
        return -account.daily_pnl >= loss_limit

    @staticmethod
    def _explain(
        approved: bool, veto_reasons: list[VetoReason], position_size: PositionSize | None, risk_reduced: bool
    ) -> str:
        if approved and position_size is not None:
            suffix = " (reduced size: consecutive-loss recovery)" if risk_reduced else ""
            return f"Approved: {position_size.quantity} units, risk {position_size.total_risk:,.2f}{suffix}."
        reasons = ", ".join(reason.value for reason in veto_reasons) or "no valid position size"
        return f"Rejected: {reasons}."


def summarize_risk(records: list[SignalRecord]) -> RiskSummary:
    approved = [r for r in records if r.decision.approved]
    rejected = [r for r in records if not r.decision.approved]

    rejections_by_reason: dict[VetoReason, int] = {reason: 0 for reason in VetoReason}
    for record in rejected:
        for reason in record.decision.veto_reasons:
            rejections_by_reason[reason] += 1
    rejections_by_reason = {reason: count for reason, count in rejections_by_reason.items() if count > 0}

    risk_amounts = [r.decision.risk_amount for r in approved if r.decision.risk_amount is not None]

    return RiskSummary(
        signals_generated=len(records),
        signals_approved=len(approved),
        signals_rejected=len(rejected),
        rejections_by_reason=rejections_by_reason,
        average_risk_amount=(sum(risk_amounts) / len(risk_amounts)) if risk_amounts else None,
        maximum_risk_amount=max(risk_amounts) if risk_amounts else None,
        signals_risk_reduced=sum(1 for r in approved if r.decision.risk_reduced),
    )
