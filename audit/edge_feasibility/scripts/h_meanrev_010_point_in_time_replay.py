"""Step 2 of the H_MEANREV_010 point-in-time replay (Path 1 of the user's
own capital-allocation mission, 2026-09-21).

Reuses H_MEANREV_010's own frozen primitives completely unmodified:
quant_research.mean_reversion_signal._oversold_2std_relative_weak (entry),
quant_research.mean_reversion_execution_structure.compute_fixed_notional_trade
(sizing/costs, capital_per_slot=100,000, the same explicitly-disclosed
single-symbol-at-a-time simplification the original entry used),
backtesting.costs.CostModel.india_nse_intraday_2026() (costs),
backtesting.splits.split_periods (dev/val/oos boundaries),
quant_research.alpha_features.add_alpha_features (relative_strength_20).

The ONLY methodological change from the original H_MEANREV_010 Candidate
2 run: a candidate signal is now additionally gated by whether its own
symbol was ACTUALLY F&O-eligible, AS OF ITS OWN SIGNAL DATE, per the
real, dated snapshots build_point_in_time_snapshots.py retrieved and
quant_research/security_identity_map.py's identity resolution --
replacing the original's single, current-snapshot-applied-to-all-10-years
universe. No entry/exit/cost/sizing logic is touched.

Universe: the CANONICAL symbols appearing in POINT_IN_TIME_SNAPSHOTS.csv,
i.e. every symbol that was F&O-eligible at ANY point across the 11
sampled anchor dates -- not ORIGINAL_32_NSE_UNIVERSE (H_MEANREV_010's own
combined universe was built from COMBINED = ORIGINAL_32 union
EXPANDED_ONLY; this replay instead lets point-in-time evidence itself
determine membership, since the whole point of this exercise is to stop
assuming ORIGINAL_32's own always-eligible premise and instead test it).
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
from quant_research.alpha_features import add_alpha_features
from quant_research.mean_reversion_execution_structure import compute_fixed_notional_trade
from quant_research.mean_reversion_signal import _oversold_2std_relative_weak

PERIOD = "10y"
INTERVAL = "1d"
BENCHMARK_SYMBOL = "^NSEI"
CAPITAL_PER_SLOT = 100_000.0
HOLDING_BARS = 10
COST_MODEL = CostModel.india_nse_intraday_2026()

SNAPSHOTS_PATH = REPO_ROOT / "audit" / "edge_feasibility" / "POINT_IN_TIME_SNAPSHOTS.csv"
OUT_CSV = REPO_ROOT / "audit" / "edge_feasibility" / "H_MEANREV_010_POINT_IN_TIME_TRADES.csv"


def build_eligibility_index(snapshots: pd.DataFrame) -> dict[str, list[tuple[pd.Timestamp, set[str]]]]:
    """canonical_symbol -> list of (snapshot_date, symbols_present_at_that_snapshot),
    sorted by date. `symbols_present_at_that_snapshot` is stored once
    (shared) per snapshot date, not per symbol, to make membership lookup
    a simple "is symbol in this snapshot's own set" check."""
    by_date: dict[pd.Timestamp, set[str]] = {}
    for snap_date, group in snapshots.groupby("actual_snapshot_date"):
        by_date[pd.Timestamp(snap_date)] = set(group["canonical_symbol"])
    ordered_dates = sorted(by_date)
    index: dict[str, list[tuple[pd.Timestamp, set[str]]]] = {}
    for symbol in snapshots["canonical_symbol"].unique():
        index[symbol] = [(d, by_date[d]) for d in ordered_dates]
    return index


def is_eligible(symbol: str, as_of: pd.Timestamp, snapshot_dates: list[pd.Timestamp], sets_by_date: dict[pd.Timestamp, set[str]]) -> bool:
    """Step-function lookup: eligible iff `symbol` was present in the
    LATEST snapshot at or before `as_of`. False (never fabricated True)
    if `as_of` precedes every snapshot -- no evidence, no assumption."""
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
    print("H_MEANREV_010 POINT-IN-TIME REPLAY -- frozen signal/exit/costs, corrected universe membership")
    print("=" * 100)

    snapshots = pd.read_csv(SNAPSHOTS_PATH, parse_dates=["anchor_date", "actual_snapshot_date"])
    snapshot_dates = sorted(pd.Timestamp(d) for d in snapshots["actual_snapshot_date"].unique())
    sets_by_date = {d: set(g["canonical_symbol"]) for d, g in snapshots.groupby("actual_snapshot_date")}
    sets_by_date = {pd.Timestamp(k): v for k, v in sets_by_date.items()}
    universe = sorted(snapshots["canonical_symbol"].unique())
    print(f"Point-in-time universe (ever-eligible across {len(snapshot_dates)} snapshots): {len(universe)} canonical symbols")

    provider = CachedMarketDataProvider(get_market_data_provider())
    benchmark_ohlcv = provider.fetch_ohlcv(BENCHMARK_SYMBOL, period=PERIOD, interval=INTERVAL)
    benchmark_series = compute_indicator_series(benchmark_ohlcv)

    rows = []
    failed_symbols: dict[str, str] = {}
    buildable = 0
    for symbol in universe:
        try:
            ohlcv = provider.fetch_ohlcv(symbol, period=PERIOD, interval=INTERVAL)
            indicator_series = add_alpha_features(compute_indicator_series(ohlcv), market_series=benchmark_series)
        except (MarketDataError, ValueError) as exc:
            failed_symbols[symbol] = str(exc)
            continue
        if len(indicator_series) < 2:
            failed_symbols[symbol] = f"too short after indicator computation ({len(indicator_series)} rows)"
            continue
        try:
            split = split_periods(indicator_series.index[0], indicator_series.index[-1])
        except ValueError as exc:
            failed_symbols[symbol] = f"split_periods failed: {exc}"
            continue
        buildable += 1
        periods = {
            "development": (split.development_start, split.development_end),
            "validation": (split.validation_start, split.validation_end),
            "out_of_sample": (split.out_of_sample_start, split.out_of_sample_end),
        }

        # Mirrors run_universe_fixed_notional_time_exit_experiment's own loop EXACTLY
        # (period-sliced frame, i += max_holding_bars on an accepted trade, i += 1
        # otherwise) -- the ONLY addition is the point-in-time eligibility check,
        # inserted where the original's own "trade is None" branch already lives, so
        # an ineligible signal is treated identically to "no signal fired here."
        for period_label, (start, end) in periods.items():
            sliced = indicator_series.loc[(indicator_series.index >= start) & (indicator_series.index <= end)]
            if sliced.empty:
                continue

            n = len(sliced)
            i = 0
            while i < n:
                row = sliced.iloc[i]
                if _oversold_2std_relative_weak(row):
                    ts = sliced.index[i]
                    if is_eligible(symbol, ts, snapshot_dates, sets_by_date):
                        trade = compute_fixed_notional_trade(
                            sliced, symbol=symbol, signal_idx=i, holding_bars=HOLDING_BARS,
                            capital_per_slot=CAPITAL_PER_SLOT, cost_model=COST_MODEL,
                        )
                        if trade is not None:
                            rows.append({
                                "symbol": symbol, "split": period_label, "entry_time": trade.entry_time, "exit_time": trade.exit_time,
                                "net_return": trade.net_return, "gross_return": trade.gross_return, "net_pnl": trade.net_pnl,
                                "entry_notional": trade.entry_notional, "quantity": trade.quantity,
                            })
                            i += HOLDING_BARS
                            continue
                i += 1

    print(f"Buildable: {buildable}/{len(universe)}. Failed: {len(failed_symbols)} ({list(failed_symbols)[:10]}{'...' if len(failed_symbols) > 10 else ''})")

    df = pd.DataFrame(rows)
    df.to_csv(OUT_CSV, index=False)
    print(f"\nTotal trades (point-in-time-gated): {len(df)}")
    print(f"Written to {OUT_CSV}")

    print()
    print("=" * 100)
    print("RESULTS BY SPLIT")
    print("=" * 100)
    for split in ["development", "validation", "out_of_sample"]:
        sub = df[df["split"] == split]
        n = len(sub)
        if n == 0:
            print(f"{split}: n=0")
            continue
        net_returns = sub["net_return"].tolist()
        report = compute_profitability_report_from_returns(net_returns)
        gross_mean = sub["gross_return"].mean()
        win_rate = (sub["net_return"] > 0).mean()
        distinct_symbols = sub["symbol"].nunique()
        worst, best = sub["net_return"].min(), sub["net_return"].max()
        median_return = sub["net_return"].median()
        wins_sum = sub.loc[sub["net_pnl"] > 0, "net_pnl"].sum()
        losses_sum = -sub.loc[sub["net_pnl"] < 0, "net_pnl"].sum()
        profit_factor = (wins_sum / losses_sum) if losses_sum > 0 else float("inf")
        print(f"\n--- {split} ---")
        print(f"n={n} distinct_symbols={distinct_symbols}")
        print(f"net mean={report.expectancy*100:+.3f}% median={median_return*100:+.3f}% "
              f"CI=[{report.mean_return_ci_low*100:+.3f}%,{report.mean_return_ci_high*100:+.3f}%] verdict={report.verdict.value}")
        print(f"gross mean={gross_mean*100:+.3f}%")
        print(f"win_rate={win_rate*100:.1f}% profit_factor={profit_factor:.3f}")
        print(f"worst_trade={worst*100:+.3f}% best_trade={best*100:+.3f}%")
        print(f"mean_entry_notional={sub['entry_notional'].mean():,.0f}")

    print()
    print("=" * 100)
    print("COMPARISON AGAINST ORIGINAL H_MEANREV_010 CANDIDATE 2")
    print("=" * 100)
    original = {
        "development": {"n": 2897, "net_mean": 0.0008, "ci": (-0.0027, 0.0044)},
        "validation": {"n": 688, "net_mean": 0.0151, "ci": (0.0094, 0.0208)},
        "out_of_sample": {"n": 840, "net_mean": 0.0098, "ci": (0.0052, 0.0144)},
    }
    for split, orig in original.items():
        sub = df[df["split"] == split]
        n_new = len(sub)
        mean_new = sub["net_return"].mean() if n_new else float("nan")
        print(f"{split}: original n={orig['n']} mean={orig['net_mean']*100:+.3f}% CI=[{orig['ci'][0]*100:+.2f}%,{orig['ci'][1]*100:+.2f}%] "
              f"  |  point-in-time n={n_new} mean={mean_new*100:+.3f}%")


if __name__ == "__main__":
    main()
