from datetime import date

from pydantic import BaseModel, ConfigDict, Field


class Account(BaseModel):
    """First-class deterministic account state (Phase 3 kept only a bare
    `equity: float` loop variable inside the engine — this replaces it).

    Invariant enforced throughout: `equity == cash + open_position_notional`
    at every point this model is read. Single-position only, no leverage —
    `open_position_quantity` is always 0 or a positive int.

    Mutation happens only through the methods below (open_position /
    mark_to_market / close_position / roll_to_day) so the invariant can't be
    violated by a stray direct field assignment.
    """

    model_config = ConfigDict(validate_assignment=True)

    initial_capital: float = Field(gt=0)
    cash: float
    realized_pnl: float = 0.0

    open_position_quantity: int = Field(default=0, ge=0)
    open_position_entry_price: float = 0.0
    open_position_cost_basis: float = 0.0  # cash committed at entry (quantity * entry_price)
    unrealized_pnl: float = 0.0  # mark-to-market vs. the open position's cost basis

    peak_equity: float
    daily_start_equity: float
    current_day: date | None = None

    consecutive_losses: int = Field(default=0, ge=0)
    total_trades: int = Field(default=0, ge=0)

    @property
    def open_positions(self) -> int:
        return 1 if self.open_position_quantity > 0 else 0

    @property
    def open_position_notional(self) -> float:
        return self.open_position_cost_basis + self.unrealized_pnl

    @property
    def equity(self) -> float:
        return self.cash + self.open_position_notional

    @property
    def current_drawdown_pct(self) -> float:
        if self.peak_equity <= 0:
            return 0.0
        return max(0.0, (self.peak_equity - self.equity) / self.peak_equity * 100)

    @property
    def daily_pnl(self) -> float:
        return self.equity - self.daily_start_equity

    def roll_to_day(self, day: date) -> None:
        """Reset the daily-loss reference point at the start of a new
        trading day. `day` must come from the market data's own bar
        timestamp — never the host machine's local clock (spec §23)."""
        if self.current_day != day:
            self.current_day = day
            self.daily_start_equity = self.equity

    def mark_to_market(self, current_price: float) -> None:
        """Update unrealized PnL / equity / peak using only the price of a
        bar that has already occurred — callers must never pass a future
        close (see backtesting/engine.py's chronological loop)."""
        if self.open_position_quantity > 0:
            self.unrealized_pnl = (current_price - self.open_position_entry_price) * self.open_position_quantity
        self._update_peak()

    def open_position(self, *, quantity: int, entry_price: float, entry_cost: float) -> None:
        if quantity <= 0:
            raise ValueError("quantity must be positive to open a position.")
        if self.open_position_quantity > 0:
            raise ValueError("a position is already open (single-position engine).")

        notional = quantity * entry_price
        self.cash -= notional + entry_cost
        self.open_position_quantity = quantity
        self.open_position_entry_price = entry_price
        self.open_position_cost_basis = notional
        self.unrealized_pnl = 0.0
        self._update_peak()

    def close_position(self, *, exit_price: float, exit_cost: float, net_pnl: float) -> None:
        if self.open_position_quantity == 0:
            raise ValueError("no open position to close.")

        proceeds = self.open_position_quantity * exit_price
        self.cash += proceeds - exit_cost
        self.realized_pnl += net_pnl
        self.total_trades += 1
        self.consecutive_losses = self.consecutive_losses + 1 if net_pnl < 0 else 0

        self.open_position_quantity = 0
        self.open_position_entry_price = 0.0
        self.open_position_cost_basis = 0.0
        self.unrealized_pnl = 0.0
        self._update_peak()

    def _update_peak(self) -> None:
        self.peak_equity = max(self.peak_equity, self.equity)


def new_account(initial_capital: float) -> Account:
    return Account(
        initial_capital=initial_capital,
        cash=initial_capital,
        peak_equity=initial_capital,
        daily_start_equity=initial_capital,
    )
