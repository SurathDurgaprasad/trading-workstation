from datetime import datetime

from pydantic import BaseModel, ConfigDict


class EquityPoint(BaseModel):
    model_config = ConfigDict(frozen=True)

    timestamp: datetime
    equity: float
    drawdown_pct: float  # 0.0 at a new peak; positive = percent below the running peak


def build_equity_curve(
    *, start_time: datetime, initial_capital: float, trade_equities: list[tuple[datetime, float]]
) -> list[EquityPoint]:
    """One point per completed trade (plus the starting point), per spec
    §15 — this is not an intrabar mark-to-market curve."""
    points = [EquityPoint(timestamp=start_time, equity=initial_capital, drawdown_pct=0.0)]

    peak = initial_capital
    for timestamp, equity in trade_equities:
        peak = max(peak, equity)
        drawdown_pct = 0.0 if peak <= 0 else max(0.0, (peak - equity) / peak * 100)
        points.append(EquityPoint(timestamp=timestamp, equity=equity, drawdown_pct=drawdown_pct))

    return points
