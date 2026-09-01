from pydantic import BaseModel, ConfigDict, Field

from strategy.signal import Side


class CostModel(BaseModel):
    """Configurable, symbol-agnostic transaction cost + slippage model.

    The defaults are a conservative generic placeholder (flat brokerage +
    a few bps of slippage), not a claim of real-world accuracy for any
    specific market — this backtester has been exercised against a US
    symbol (AAPL) via Yahoo Finance, where Indian STT/GST/stamp duty do not
    apply. Use `CostModel.india_nse_intraday_2026()` when backtesting an NSE
    symbol instead of assuming the default fits every market.
    """

    model_config = ConfigDict(frozen=True)

    brokerage_per_fill: float = Field(default=20.0, ge=0, description="Flat currency cost, charged on entry AND exit each.")
    fees_pct: float = Field(default=0.0, ge=0, description="Exchange/other fees, percent of notional, per fill.")
    taxes_pct: float = Field(default=0.0, ge=0, description="STT/GST/stamp-duty-style taxes, percent of notional, per fill.")
    entry_slippage_bps: float = Field(default=5.0, ge=0)
    exit_slippage_bps: float = Field(default=5.0, ge=0)

    @classmethod
    def india_nse_intraday_2026(cls) -> "CostModel":
        """Reference preset from AI_Trading_Platform_Master_Blueprint.docx §2.2
        (2026 rates). Combines STT (0.025%), NSE exchange charges (~0.00375%),
        and the ₹20 flat Dhan brokerage into one round-trip-average model —
        this is a documented simplification, not a replica of the blueprint's
        buy/sell-side-asymmetric cost table. GST and stamp duty are omitted
        for the same reason (they are small relative to STT/brokerage at this
        level of approximation); revisit before relying on this for real P&L.
        """
        return cls(
            brokerage_per_fill=20.0,
            fees_pct=0.00375,
            taxes_pct=0.025,
            entry_slippage_bps=5.0,
            exit_slippage_bps=10.0,  # blueprint's "0.05% baseline" MPP slippage estimate
        )

    def cost_for_fill(self, *, notional: float) -> float:
        return self.brokerage_per_fill + notional * (self.fees_pct + self.taxes_pct) / 100

    def slippage_adjusted_price(self, *, price: float, side: Side, is_entry: bool) -> float:
        if side != Side.LONG:
            raise NotImplementedError("Only Side.LONG is implemented (see strategy/baseline.py).")

        bps = self.entry_slippage_bps if is_entry else self.exit_slippage_bps
        adjustment = price * bps / 10_000
        # Long entry: pay slightly more (buy at a worse price).
        # Long exit: receive slightly less (sell at a worse price).
        return price + adjustment if is_entry else price - adjustment
