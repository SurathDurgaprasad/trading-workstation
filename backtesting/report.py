from backtesting.engine import BacktestResult

_RULE = "-" * 50


def _fmt(value: float | None, *, digits: int = 2, suffix: str = "") -> str:
    if value is None:
        return "N/A (undefined)"
    return f"{value:.{digits}f}{suffix}"


def format_backtest_report(
    result: BacktestResult,
    *,
    development: BacktestResult | None = None,
    validation: BacktestResult | None = None,
    out_of_sample: BacktestResult | None = None,
) -> str:
    m = result.metrics
    lines = [
        "=" * 50,
        "BACKTEST",
        "=" * 50,
        "",
        f"Strategy: {result.strategy_name}",
        f"Symbol: {result.symbol}",
        "",
        "Period:",
        f"{result.start.date()} -> {result.end.date()}",
        "",
        f"Initial Capital: {result.initial_capital:,.2f}",
        "",
        _RULE,
        "PERFORMANCE",
        _RULE,
        "",
        f"Trades:             {m.total_trades}",
        f"Win Rate:           {_fmt(m.win_rate_pct, suffix='%')}",
        f"Profit Factor:      {_fmt(m.profit_factor)}",
        f"Net PnL:            {m.net_pnl:,.2f}",
        f"Average Trade:      {m.average_trade:,.2f}",
        f"Average Winner:     {_fmt(m.average_winner)}",
        f"Average Loser:      {_fmt(m.average_loser)}",
        f"Expectancy:         {_fmt(m.expectancy, suffix='R')}",
        f"Average R:          {_fmt(m.average_r, suffix='R')}",
        f"Largest Win:        {_fmt(m.largest_win)}",
        f"Largest Loss:       {_fmt(m.largest_loss)}",
        f"Max Drawdown:       {_fmt(m.max_drawdown_pct, suffix='%')}",
        f"Max Losing Streak:  {m.max_consecutive_losses}",
        "",
        _RULE,
        "COSTS",
        _RULE,
        "",
        f"Gross PnL:          {m.gross_pnl:,.2f}",
        f"Transaction Costs:  {m.total_costs:,.2f}",
        f"Net PnL:            {m.net_pnl:,.2f}",
        "",
        _RULE,
        "RISK",
        _RULE,
        "",
    ]

    rs = result.risk_summary
    lines += [
        f"Signals Generated:  {rs.signals_generated}",
        f"Signals Approved:   {rs.signals_approved}",
        f"Signals Rejected:   {rs.signals_rejected}",
        "",
        "Risk Rejections:",
    ]
    if rs.rejections_by_reason:
        for reason, count in sorted(rs.rejections_by_reason.items(), key=lambda kv: kv[0].value):
            lines.append(f"  {reason.value.replace('_', ' ').title():<22}{count}")
    else:
        lines.append("  (none)")
    lines += [
        "",
        f"Average Risk/Trade: {_fmt(rs.average_risk_amount)}",
        f"Maximum Risk/Trade: {_fmt(rs.maximum_risk_amount)}",
        f"Risk-Reduced Trades: {rs.signals_risk_reduced} (consecutive-loss recovery)",
        "",
        _RULE,
        "VALIDATION",
        _RULE,
        "",
    ]

    for label, sub_result in (
        ("Development", development),
        ("Validation", validation),
        ("Out-of-Sample", out_of_sample),
    ):
        if sub_result is None:
            lines.append(f"{label}:{' ' * (14 - len(label))}(not computed)")
            continue
        sm = sub_result.metrics
        lines.append(
            f"{label}:{' ' * max(1, 14 - len(label))}"
            f"{sm.total_trades} trades, win rate {_fmt(sm.win_rate_pct, suffix='%')}, "
            f"net PnL {sm.net_pnl:,.2f}, expectancy {_fmt(sm.expectancy, suffix='R')}"
        )

    lines += [
        "",
        _RULE,
        "",
        "IMPORTANT:",
        "This is historical simulation.",
        "It is not evidence of future profitability.",
        "",
    ]

    return "\n".join(lines)
