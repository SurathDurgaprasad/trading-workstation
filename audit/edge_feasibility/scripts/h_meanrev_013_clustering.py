"""H_MEANREV_013 -- candidate clustering vs. subsequent return.

Executes exactly what audit/edge_feasibility/H_MEANREV_013_CLUSTERING_PREREGISTRATION.md
pre-registered, no deviation. Isolated audit script: reads real cached market data,
reuses quant_research/mean_reversion_portfolio.py's and mean_reversion_execution_structure.py's
existing PURE functions unmodified, and independently REPLICATES (does not modify) the
accept/reject decision rule from _run_schedule so individual (not just aggregate) candidate
events can be labeled and their own forward return measured regardless of acceptance.

Never touches the live fleet. Never modifies any production file. Offline-only, run after
today's NSE session closed.
"""
import sys
from pathlib import Path

REPO_ROOT = Path(r"C:\Users\durgaprasad.surath\OneDrive - Ideabytes\Documents\Working With AI\ai_trade\TradingAgents")
sys.path.insert(0, str(REPO_ROOT))

import pandas as pd

from backtesting.cache import CachedMarketDataProvider
from backtesting.costs import CostModel
from backtesting.splits import split_periods
from live.dhan.instruments import DhanInstrumentMap
from market.data_provider import MarketDataError, get_market_data_provider
from market.indicators import compute_indicator_series
from market_data.universe import exchange_for_symbol
from quant_research.alpha_features import add_alpha_features, add_forward_return_targets
from quant_research.market_behavior import SymbolDataset
from quant_research.mean_reversion_execution_structure import compute_fixed_notional_trade
from quant_research.mean_reversion_portfolio import CandidateEntryEvent, collect_candidate_events, schedule_portfolio
from quant_research.universe_expansion import ORIGINAL_32_NSE_UNIVERSE, build_universe_groups
from learning.profitability import compute_profitability_report_from_returns, ProfitabilityVerdict

PERIOD = "10y"
INTERVAL = "1d"
BENCHMARK_SYMBOL = "^NSEI"
MAX_CONCURRENT_POSITIONS = 4
CAPITAL_PER_POSITION = 25_000.0
INITIAL_CAPITAL = 100_000.0
HOLDING_BARS = 10
COST_MODEL = CostModel.india_nse_intraday_2026()

CLUSTER_BINS = [
    ("1", lambda n: n == 1),
    ("2", lambda n: n == 2),
    ("3-4", lambda n: 3 <= n <= 4),
    ("5-9", lambda n: 5 <= n <= 9),
    ("10+", lambda n: n >= 10),
]


def build_dataset_with_real_benchmark(symbol: str, provider, benchmark_series: pd.DataFrame) -> "SymbolDataset | None":
    """Mirrors quant_research.mean_reversion_signal's own H_MEANREV_009-established
    pattern (real market_series=^NSEI pass), which market_behavior.build_symbol_dataset's
    own generic default (market_series=None) does NOT provide -- relative_strength_20
    would be all-NaN otherwise, per that module's own documented fix."""
    try:
        ohlcv = provider.fetch_ohlcv(symbol, period=PERIOD, interval=INTERVAL)
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


def replicate_schedule_with_identity(datasets, events):
    """Independently REPLICATES (never imports/modifies) _run_schedule's own accept/reject
    decision rule from quant_research/mean_reversion_portfolio.py, so each individual event
    (not just an aggregate count) can be labeled. Cross-validated against the real,
    unmodified schedule_portfolio() call below for correctness."""
    open_positions = []  # list of (symbol, exit_time)
    symbols_open = set()
    cash = INITIAL_CAPITAL
    labels = {}  # id(event) -> "accepted" | "rejected_capacity" | "rejected_cash" | "rejected_symbol_open" | "rejected_no_data"

    for event in events:
        still_open = []
        for sym, exit_time, net_pnl in open_positions:
            if exit_time <= event.signal_date:
                cash += CAPITAL_PER_POSITION + net_pnl
                symbols_open.discard(sym)
            else:
                still_open.append((sym, exit_time, net_pnl))
        open_positions = still_open

        if event.symbol in symbols_open:
            labels[id(event)] = "rejected_symbol_open"
            continue
        if len(open_positions) >= MAX_CONCURRENT_POSITIONS:
            labels[id(event)] = "rejected_capacity"
            continue
        if CAPITAL_PER_POSITION > cash:
            labels[id(event)] = "rejected_cash"
            continue

        frame = datasets[event.symbol].frame
        trade = compute_fixed_notional_trade(
            frame, symbol=event.symbol, signal_idx=event.signal_idx, holding_bars=HOLDING_BARS,
            capital_per_slot=CAPITAL_PER_POSITION, cost_model=COST_MODEL,
        )
        if trade is None:
            labels[id(event)] = "rejected_no_data"
            continue

        cash -= CAPITAL_PER_POSITION
        open_positions.append((event.symbol, trade.exit_time, trade.net_pnl))
        symbols_open.add(event.symbol)
        labels[id(event)] = "accepted"

    return labels


def period_for_date(date, development_end, validation_end) -> str:
    if date <= development_end:
        return "development"
    if date <= validation_end:
        return "validation"
    return "out_of_sample"


def main():
    print("=" * 100)
    print("H_MEANREV_013 -- candidate clustering vs. subsequent return (offline audit script)")
    print("=" * 100)

    instrument_map = DhanInstrumentMap.from_csv(REPO_ROOT / "data" / "dhan" / "scrip-master.csv")
    groups = build_universe_groups(instrument_map)
    combined = groups["combined"]
    print(f"COMBINED universe (nominal): {len(combined)} symbols")

    provider = CachedMarketDataProvider(get_market_data_provider())

    benchmark_ohlcv = provider.fetch_ohlcv(BENCHMARK_SYMBOL, period=PERIOD, interval=INTERVAL)
    benchmark_series = compute_indicator_series(benchmark_ohlcv)

    datasets = {}
    failed = []
    for symbol in combined:
        ds = build_dataset_with_real_benchmark(symbol, provider, benchmark_series)
        if ds is not None:
            datasets[symbol] = ds
        else:
            failed.append(symbol)
    print(f"Buildable: {len(datasets)}/{len(combined)}. Failed: {failed}")

    dev_end, val_end = next(iter(datasets.values())).development_end, next(iter(datasets.values())).validation_end
    print(f"Shared calendar boundaries: development_end={dev_end}, validation_end={val_end}")

    events = collect_candidate_events(datasets)
    print(f"Total candidate events (COMBINED universe, all time): {len(events)}")

    # --- Cross-validation: independently replicated labeling vs. the real, unmodified schedule_portfolio() ---
    labels = replicate_schedule_with_identity(datasets, events)
    real_result = schedule_portfolio(
        datasets, events, max_concurrent_positions=MAX_CONCURRENT_POSITIONS, capital_per_position=CAPITAL_PER_POSITION,
        initial_capital=INITIAL_CAPITAL, holding_bars=HOLDING_BARS, cost_model=COST_MODEL,
    )
    n_accepted_replicated = sum(1 for v in labels.values() if v == "accepted")
    print(f"CROSS-CHECK: real schedule_portfolio() accepted={len(real_result.accepted_trades)}, "
          f"replicated labeling accepted={n_accepted_replicated} "
          f"({'MATCH' if n_accepted_replicated == len(real_result.accepted_trades) else 'MISMATCH -- INVESTIGATE'})")

    # --- Per-event independent forward return (as if accepted alone, regardless of real label) ---
    rows = []
    for event in events:
        frame = datasets[event.symbol].frame
        trade = compute_fixed_notional_trade(
            frame, symbol=event.symbol, signal_idx=event.signal_idx, holding_bars=HOLDING_BARS,
            capital_per_slot=CAPITAL_PER_POSITION, cost_model=COST_MODEL,
        )
        if trade is None:
            continue
        split = period_for_date(event.signal_date, dev_end, val_end)
        rows.append({
            "symbol": event.symbol, "signal_date": event.signal_date, "split": split,
            "label": labels[id(event)], "net_return": trade.net_return, "gross_return": trade.gross_return,
            "in_original_32": event.symbol in ORIGINAL_32_NSE_UNIVERSE,
        })
    df = pd.DataFrame(rows)
    print(f"Priceable candidate events (compute_fixed_notional_trade succeeded): {len(df)}")

    # --- Cluster size per day ---
    cluster_size = df.groupby("signal_date")["symbol"].transform("count")
    df["cluster_size"] = cluster_size

    def bin_for(n):
        for name, pred in CLUSTER_BINS:
            if pred(n):
                return name
        return "?"
    df["cluster_bin"] = df["cluster_size"].apply(bin_for)

    print()
    print("=" * 100)
    print("PRIMARY TABLE -- pooled forward h10 net return by cluster bin, ALL candidates (accepted+rejected)")
    print("=" * 100)
    for split in ["development", "validation", "out_of_sample"]:
        print(f"\n--- {split} ---")
        for name, _ in CLUSTER_BINS:
            sub = df[(df["split"] == split) & (df["cluster_bin"] == name)]
            n = len(sub)
            if n == 0:
                print(f"  bin={name:5s} n=0")
                continue
            report = compute_profitability_report_from_returns(sub["net_return"].tolist())
            ci = f"[{report.mean_return_ci_low*100:+.2f}%,{report.mean_return_ci_high*100:+.2f}%]" if report.mean_return_ci_low is not None else "n/a"
            mean_str = f"{report.expectancy*100:+.3f}%" if report.expectancy is not None else "n/a"
            print(f"  bin={name:5s} n={n:5d} mean={mean_str} "
                  f"CI={ci} verdict={report.verdict.value}")

    print()
    print("=" * 100)
    print("ACCEPTED vs REJECTED_CAPACITY -- same cluster bins, split by real acceptance")
    print("=" * 100)
    for split in ["development", "validation", "out_of_sample"]:
        print(f"\n--- {split} ---")
        for subset_name, subset_label in [("ACCEPTED", "accepted"), ("REJECTED (capacity)", "rejected_capacity")]:
            sub = df[(df["split"] == split) & (df["label"] == subset_label)]
            n = len(sub)
            if n == 0:
                print(f"  {subset_name:22s} n=0")
                continue
            report = compute_profitability_report_from_returns(sub["net_return"].tolist())
            mean_str = f"{report.expectancy*100:+.3f}%" if report.expectancy is not None else "n/a"
            print(f"  {subset_name:22s} n={n:5d} mean={mean_str} verdict={report.verdict.value}")

    print()
    print("=" * 100)
    print("SURVIVORSHIP-EXPOSURE QUANTIFICATION (not a fix -- per preregistration S7)")
    print("=" * 100)
    accepted = df[df["label"] == "accepted"]
    if len(accepted) > 0:
        original_share = accepted["in_original_32"].mean() * 100
        original_net_pnl_share = accepted[accepted["in_original_32"]]["net_return"].sum() / accepted["net_return"].sum() * 100 if accepted["net_return"].sum() != 0 else float("nan")
        print(f"Accepted trades in ORIGINAL-32 (point-in-time-plausible) universe: {original_share:.1f}% of trade count, "
              f"{original_net_pnl_share:.1f}% of summed net return (EXPANDED-ONLY, current-eligibility-only, makes up the rest).")

    out_path = REPO_ROOT / "audit" / "edge_feasibility" / "H_MEANREV_013_RESULTS.csv"
    df.to_csv(out_path, index=False)
    print(f"\nFull per-event results written to {out_path}")


if __name__ == "__main__":
    main()
