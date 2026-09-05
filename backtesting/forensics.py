"""Weekend hardening, Phase 7B/7C (strategy forensics) -- the pooled
verdict in backtesting/universe.py answers "does an edge exist" (no --
NEGATIVE_PERFORMANCE, 368 trades, 95% CI entirely below zero). This
module answers the follow-up the mission explicitly demands before any
attempt at improvement: WHERE does the negative expectancy come from.

backtesting.trade.Trade does not track a position's price path between
entry and exit at all (only entry_price/exit_price) -- unlike
predictions.tracker.evaluate_prediction, which already computes MFE/MAE
for the prediction-tracking path. Rather than modifying the backtest
engine itself (an already-tested, working, unrelated-to-this-forensic-
question code path -- "do not modify anything yet, produce evidence
first" per the mission's own Phase 7C instruction), this module
RE-WALKS the same indicator_series the backtest already ran against
(deterministic, same cached data) to reconstruct each trade's own
Maximum Favorable/Adverse Excursion after the fact -- a pure, read-only
analysis, zero changes to how a trade is actually generated or filled.
"""

from dataclasses import dataclass

import pandas as pd

from backtesting.trade import ExitReason, Trade


@dataclass(frozen=True)
class TradeExcursion:
    trade: Trade
    mfe_pct: float
    """Maximum favorable excursion: the best unrealized gain (as a
    fraction of entry price) reached at any point between entry and
    exit, using each bar's high (long-only, matching this project's
    Side.LONG-only strategy universe) -- never negative by construction
    (entry_price itself is always in the window)."""
    mae_pct: float
    """Maximum adverse excursion: the worst unrealized loss (as a
    positive fraction of entry price) reached at any point between
    entry and exit, using each bar's low. Never negative by
    construction."""
    bars_held: int


def compute_trade_excursion(trade: Trade, indicator_series: pd.DataFrame) -> TradeExcursion | None:
    """None only when the trade's own [entry_time, exit_time] window has
    no matching rows in indicator_series -- should not occur for a trade
    genuinely produced by run_backtest against this exact series, but
    this function makes no assumption about its caller and never
    fabricates an excursion for data it cannot find."""
    window = indicator_series.loc[
        (indicator_series.index >= trade.entry_time) & (indicator_series.index <= trade.exit_time)
    ]
    if window.empty:
        return None

    mfe_pct = (float(window["high"].max()) - trade.entry_price) / trade.entry_price
    mae_pct = (trade.entry_price - float(window["low"].min())) / trade.entry_price

    return TradeExcursion(
        trade=trade, mfe_pct=max(0.0, mfe_pct), mae_pct=max(0.0, mae_pct), bars_held=len(window),
    )


@dataclass(frozen=True)
class ExitReasonBucket:
    exit_reason: ExitReason
    count: int
    win_rate_pct: float
    mean_net_pnl: float
    mean_r_multiple: float


def breakdown_by_exit_reason(trades: list[Trade]) -> list[ExitReasonBucket]:
    """Phase 7B: where does the negative expectancy come from -- STOP,
    TARGET, or END_OF_DATA (a position still open when the backtest's
    own data simply ran out, force-closed at the last close, per
    run_backtest's own documented behavior)? Buckets ordered by count,
    descending, for a "biggest contributor first" read."""
    groups: dict[ExitReason, list[Trade]] = {}
    for trade in trades:
        groups.setdefault(trade.exit_reason, []).append(trade)

    buckets = []
    for reason, group in groups.items():
        winners = [t for t in group if t.net_pnl > 0]
        buckets.append(ExitReasonBucket(
            exit_reason=reason,
            count=len(group),
            win_rate_pct=len(winners) / len(group) * 100.0 if group else 0.0,
            mean_net_pnl=sum(t.net_pnl for t in group) / len(group) if group else 0.0,
            mean_r_multiple=sum(t.r_multiple for t in group) / len(group) if group else 0.0,
        ))
    return sorted(buckets, key=lambda b: -b.count)


@dataclass(frozen=True)
class ExcursionSummary:
    trade_count: int
    mean_mfe_pct: float
    mean_mae_pct: float
    losers_with_large_mfe_count: int
    """Count of losing trades (net_pnl < 0) whose MFE exceeded
    `large_mfe_threshold_pct` before the trade ultimately lost -- the
    specific evidence Phase 7C asks for: "if many losing trades have
    large MFE before exit, exit logic may be the problem" (the trade WAS
    profitable at some point, then gave it back)."""
    losers_with_large_mfe_pct_of_losers: float


def summarize_excursions(
    excursions: list[TradeExcursion], *, large_mfe_threshold_pct: float = 0.5,
) -> ExcursionSummary | None:
    if not excursions:
        return None

    n = len(excursions)
    mean_mfe = sum(e.mfe_pct for e in excursions) / n
    mean_mae = sum(e.mae_pct for e in excursions) / n

    losers = [e for e in excursions if e.trade.net_pnl < 0]
    # Threshold is expressed as a fraction of the trade's OWN initial risk
    # (entry - stop, as a % of entry) so it scales with each trade's own
    # ATR-based stop distance, not one fixed number across every symbol's
    # very different volatility.
    losers_with_large_mfe = [
        e for e in losers
        if e.trade.entry_price > e.trade.stop_price
        and e.mfe_pct >= large_mfe_threshold_pct * (e.trade.entry_price - e.trade.stop_price) / e.trade.entry_price
    ]

    return ExcursionSummary(
        trade_count=n,
        mean_mfe_pct=mean_mfe,
        mean_mae_pct=mean_mae,
        losers_with_large_mfe_count=len(losers_with_large_mfe),
        losers_with_large_mfe_pct_of_losers=(len(losers_with_large_mfe) / len(losers) * 100.0) if losers else 0.0,
    )
