"""Step 3 (only reached because Step 2 survived): does the point-in-time
-corrected H_MEANREV_010 result survive realistic portfolio construction?

Per the user's own sequencing (Path 1): "If it survives [the frozen
replay], then we investigate whether the effect survives realistic
portfolio constraints." Reuses quant_research/mean_reversion_portfolio.py's
own H_MEANREV_011 simulator (schedule_portfolio) COMPLETELY UNMODIFIED --
same MAX_CONCURRENT_POSITIONS=4, CAPITAL_PER_POSITION=25,000,
INITIAL_CAPITAL=100,000 the original H_MEANREV_011 preregistration froze.
The ONLY change: the candidate event list is pre-filtered by point-in-time
eligibility (the same snapshot-based check
h_meanrev_010_point_in_time_replay.py already used) before being handed
to schedule_portfolio -- no change to the scheduler's own accept/reject
logic, concurrency cap, or capital allocation.
"""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]  # audit/<family>/scripts/this_file.py -> repo root
sys.path.insert(0, str(REPO_ROOT))

import pandas as pd

from backtesting.cache import CachedMarketDataProvider
from backtesting.costs import CostModel
from backtesting.splits import split_periods
from learning.profitability import compute_profitability_report_from_returns
from market.data_provider import MarketDataError, get_market_data_provider
from market.indicators import compute_indicator_series
from market_data.universe import exchange_for_symbol
from quant_research.alpha_features import add_alpha_features, add_forward_return_targets
from quant_research.market_behavior import SymbolDataset
from quant_research.mean_reversion_portfolio import collect_candidate_events, schedule_portfolio

PERIOD = "10y"
MAX_CONCURRENT_POSITIONS = 4
CAPITAL_PER_POSITION = 25_000.0
INITIAL_CAPITAL = 100_000.0
HOLDING_BARS = 10
COST_MODEL = CostModel.india_nse_intraday_2026()

SNAPSHOTS_PATH = REPO_ROOT / "audit" / "edge_feasibility" / "POINT_IN_TIME_SNAPSHOTS.csv"
OUT_CSV = REPO_ROOT / "audit" / "edge_feasibility" / "H_MEANREV_010_POINT_IN_TIME_PORTFOLIO_TRADES.csv"


def build_dataset_with_real_benchmark(symbol: str, provider, benchmark_series: pd.DataFrame) -> "SymbolDataset | None":
    """Mirrors H_MEANREV_013's own established, already-proven pattern
    (audit/edge_feasibility/scripts/h_meanrev_013_clustering.py): market_
    behavior.build_symbol_dataset's own generic default (market_series=
    None) leaves relative_strength_20 all-NaN, which would make
    _oversold_2std_relative_weak (which requires relative_strength_20 <
    a real threshold) never fire -- a real benchmark series must be
    passed explicitly."""
    try:
        ohlcv = provider.fetch_ohlcv(symbol, period=PERIOD, interval="1d")
        frame = compute_indicator_series(ohlcv)
    except (MarketDataError, ValueError):
        return None
    if len(frame) < 60:
        return None
    frame = add_alpha_features(frame, market_series=benchmark_series)
    frame = add_forward_return_targets(frame, horizons=(HOLDING_BARS,))

    raw_market = exchange_for_symbol(symbol)
    market = "NSE" if raw_market in ("NSE", "BSE") else "US"

    development_end = validation_end = None
    if len(frame) >= 2:
        split = split_periods(frame.index[0], frame.index[-1])
        development_end, validation_end = split.development_end, split.validation_end

    return SymbolDataset(symbol=symbol, market=market, raw_market=raw_market, frame=frame, development_end=development_end, validation_end=validation_end)


def is_eligible(symbol, as_of, snapshot_dates, sets_by_date) -> bool:
    applicable = None
    for d in snapshot_dates:
        if d <= as_of:
            applicable = d
        else:
            break
    if applicable is None:
        return False
    return symbol in sets_by_date[applicable]


def main():
    print("=" * 100)
    print("H_MEANREV_010/011 POINT-IN-TIME PORTFOLIO REALISM -- frozen H_MEANREV_011 scheduler, corrected universe")
    print("=" * 100)

    snapshots = pd.read_csv(SNAPSHOTS_PATH, parse_dates=["anchor_date", "actual_snapshot_date"])
    snapshot_dates = sorted(pd.Timestamp(d) for d in snapshots["actual_snapshot_date"].unique())
    sets_by_date = {pd.Timestamp(d): set(g["canonical_symbol"]) for d, g in snapshots.groupby("actual_snapshot_date")}
    universe = sorted(snapshots["canonical_symbol"].unique())

    provider = CachedMarketDataProvider(get_market_data_provider())
    benchmark_ohlcv = provider.fetch_ohlcv("^NSEI", period=PERIOD, interval="1d")
    benchmark_series = compute_indicator_series(benchmark_ohlcv)

    datasets = {}
    for symbol in universe:
        ds = build_dataset_with_real_benchmark(symbol, provider, benchmark_series)
        if ds is not None:
            datasets[symbol] = ds
    print(f"Buildable: {len(datasets)}/{len(universe)}")

    all_events = collect_candidate_events(datasets)
    print(f"Total raw candidate events (unfiltered): {len(all_events)}")

    eligible_events = [e for e in all_events if is_eligible(e.symbol, e.signal_date, snapshot_dates, sets_by_date)]
    print(f"Point-in-time-eligible candidate events: {len(eligible_events)} ({len(all_events) - len(eligible_events)} excluded)")

    result = schedule_portfolio(
        datasets, eligible_events, max_concurrent_positions=MAX_CONCURRENT_POSITIONS,
        capital_per_position=CAPITAL_PER_POSITION, initial_capital=INITIAL_CAPITAL,
        holding_bars=HOLDING_BARS, cost_model=COST_MODEL,
    )
    print(f"Accepted trades: {len(result.accepted_trades)}")
    print(f"Rejected -- capacity: {result.rejected_capacity_count}, cash: {result.rejected_cash_count}, symbol-already-open: {result.rejected_symbol_already_open_count}")

    rows = []
    for trade in result.accepted_trades:
        # Determine split via each trade's own dataset development_end/validation_end
        ds = datasets.get(trade.symbol)
        if ds is None or ds.development_end is None:
            split_label = "unknown"
        elif trade.entry_time <= ds.development_end:
            split_label = "development"
        elif trade.entry_time <= ds.validation_end:
            split_label = "validation"
        else:
            split_label = "out_of_sample"
        rows.append({
            "symbol": trade.symbol, "split": split_label, "entry_time": trade.entry_time, "exit_time": trade.exit_time,
            "net_return": trade.net_return, "gross_return": trade.gross_return, "net_pnl": trade.net_pnl,
            "entry_notional": trade.entry_notional,
        })
    df = pd.DataFrame(rows, columns=["symbol", "split", "entry_time", "exit_time", "net_return", "gross_return", "net_pnl", "entry_notional"])
    df.to_csv(OUT_CSV, index=False)
    print(f"Written to {OUT_CSV}")

    print()
    print("=" * 100)
    print("RESULTS BY SPLIT (portfolio-constrained, point-in-time-corrected)")
    print("=" * 100)
    for split in ["development", "validation", "out_of_sample"]:
        sub = df[df["split"] == split]
        n = len(sub)
        if n == 0:
            print(f"{split}: n=0")
            continue
        report = compute_profitability_report_from_returns(sub["net_return"].tolist())
        win_rate = (sub["net_return"] > 0).mean()
        distinct_symbols = sub["symbol"].nunique()
        print(f"\n--- {split} ---")
        print(f"n={n} distinct_symbols={distinct_symbols} win_rate={win_rate*100:.1f}%")
        print(f"net mean={report.expectancy*100:+.3f}% CI=[{report.mean_return_ci_low*100:+.3f}%,{report.mean_return_ci_high*100:+.3f}%] verdict={report.verdict.value}")
        print(f"worst_trade={sub['net_return'].min()*100:+.3f}% best_trade={sub['net_return'].max()*100:+.3f}%")

    print()
    print("=" * 100)
    print("COMPARISON AGAINST ORIGINAL H_MEANREV_011 (current-universe, no point-in-time correction)")
    print("=" * 100)
    original = {
        "development": {"n": 555, "net_mean": 0.0010, "ci": (-0.0064, 0.0084)},
        "validation": {"n": 111, "net_mean": -0.0051, "ci": (-0.0205, 0.0102)},
        "out_of_sample": {"n": 105, "net_mean": -0.0042, "ci": (-0.0180, 0.0096)},
    }
    for split, orig in original.items():
        sub = df[df["split"] == split]
        n_new = len(sub)
        mean_new = sub["net_return"].mean() if n_new else float("nan")
        print(f"{split}: original n={orig['n']} mean={orig['net_mean']*100:+.3f}%  |  point-in-time n={n_new} mean={mean_new*100:+.3f}%")


if __name__ == "__main__":
    main()
