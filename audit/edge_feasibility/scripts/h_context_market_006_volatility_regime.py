"""H_CONTEXT_MARKET_006 -- does NIFTY's own volatility regime explain the
market-divergence era sign reversal H_CONTEXT_MARKET_005 found?

Executes exactly what
docs/research/H_CONTEXT_MARKET_006_VOLATILITY_REGIME_PREREGISTRATION.md
pre-registered, no deviation. Isolated audit script: reuses
quant_research/context_experiments.py and quant_research/market_behavior.py
completely unmodified. Offline-only, no production code touched, no
live-fleet dependency.
"""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]  # audit/<family>/scripts/this_file.py -> repo root
sys.path.insert(0, str(REPO_ROOT))

import math

from quant_research.context_experiments import (
    attach_external_regime,
    baseline_buy_condition,
    build_benchmark_regime_series,
    build_benchmark_volatility_series,
)
from quant_research.market_behavior import _period_mask, build_universe_datasets, measure_condition
from quant_research.universe_expansion import ORIGINAL_32_NSE_UNIVERSE
from strategy.multiple_testing import bonferroni_corrected_z

PERIOD = "10y"
HORIZONS = (5, 10)
BUCKETS = ["HIGH_VOLATILITY", "NORMAL_VOLATILITY", "LOW_VOLATILITY"]
SPLITS = ["development", "validation", "out_of_sample"]
MIN_SAMPLE = 30
Z_UNCORRECTED = 1.9599639845400545
Z_FAMILY3 = bonferroni_corrected_z(3)


def collect_raw_returns(datasets, *, bucket: str, split: str, horizon: int) -> list[float]:
    """Mirrors measure_condition's own internal filtering exactly (same
    _period_mask, same market_filter="NSE", same condition predicate),
    but returns the raw per-observation list instead of only a summary --
    needed to additionally compute a Bonferroni-corrected CI alongside
    the standard one, which ForwardReturnSummary does not expose."""
    values: list[float] = []
    for dataset in datasets.values():
        if dataset.market != "NSE":
            continue
        frame = dataset.frame
        sliced = frame.loc[_period_mask(dataset, split)]
        if sliced.empty:
            continue
        mask = sliced.apply(
            lambda row: bool(
                baseline_buy_condition(row)
                and row.get("market_trend_regime") == "TRENDING_DOWN"
                and row.get("nifty_volatility_regime") == bucket
            ),
            axis=1,
        )
        matched = sliced.loc[mask.fillna(False)]
        col = f"fwd_return_{horizon}"
        if col in matched.columns:
            values.extend(matched[col].dropna().tolist())
    return values


def corrected_ci(values: list[float], z: float) -> tuple[float, float] | None:
    n = len(values)
    if n < 2:
        return None
    mean = sum(values) / n
    variance = sum((v - mean) ** 2 for v in values) / (n - 1)
    std_err = math.sqrt(variance / n)
    return (mean - z * std_err, mean + z * std_err)


def main():
    print("=" * 100)
    print("H_CONTEXT_MARKET_006 -- NIFTY volatility-regime interaction with the market-divergence effect")
    print("=" * 100)

    symbols = list(ORIGINAL_32_NSE_UNIVERSE)
    datasets = build_universe_datasets(symbols, period=PERIOD)
    print(f"Buildable: {len(datasets)}/{len(symbols)} (ORIGINAL_32_NSE_UNIVERSE, frozen, unchanged)")

    trend_series = build_benchmark_regime_series("^NSEI", period=PERIOD)
    vol_series = build_benchmark_volatility_series("^NSEI", period=PERIOD)
    assert trend_series is not None and vol_series is not None, "NIFTY benchmark series must be fetchable -- hard stop, not a silent skip."
    attach_external_regime(datasets, regime_series=trend_series, column_name="market_trend_regime")
    attach_external_regime(datasets, regime_series=vol_series, column_name="nifty_volatility_regime")
    print(f"NIFTY trend-regime labels: {trend_series.value_counts().to_dict()}")
    print(f"NIFTY volatility-regime labels: {vol_series.value_counts().to_dict()}")

    # --- Control: reproduce H_CONTEXT_MARKET_002's own unconditioned-by-volatility numbers, as a cross-check ---
    print()
    print("-" * 100)
    print("CROSS-CHECK: H_CONTEXT_MARKET_002's own condition (BUY + NIFTY_DOWN), no volatility bucketing")
    print("-" * 100)
    for split in SPLITS:
        summary = measure_condition(
            datasets, condition_name="market_002_control", horizons=HORIZONS, period=split, market_filter="NSE",
            condition_fn=lambda row: bool(baseline_buy_condition(row) and row.get("market_trend_regime") == "TRENDING_DOWN"),
        )
        for h in HORIZONS:
            s = summary[h]
            ci = f"[{s.mean_ci_low*100:+.3f}%,{s.mean_ci_high*100:+.3f}%]" if s.mean_ci_low is not None else "n/a"
            print(f"  {split:15s} h{h:<3d} n={s.sample_size:5d} mean={s.mean_return*100 if s.mean_return is not None else float('nan'):+.3f}% CI={ci}")

    # --- Primary test: bucketed by NIFTY volatility regime ---
    print()
    print("=" * 100)
    print("PRIMARY TABLE -- H_CONTEXT_MARKET_002's condition, bucketed by NIFTY's own volatility regime")
    print("=" * 100)
    results = {}
    for split in SPLITS:
        print(f"\n--- {split} ---")
        for bucket in BUCKETS:
            for h in HORIZONS:
                values = collect_raw_returns(datasets, bucket=bucket, split=split, horizon=h)
                n = len(values)
                results[(split, bucket, h)] = values
                if n < MIN_SAMPLE:
                    print(f"  bucket={bucket:17s} h{h:<3d} n={n:5d} -- INSUFFICIENT_DATA (< {MIN_SAMPLE})")
                    continue
                mean = sum(values) / n
                unc = corrected_ci(values, Z_UNCORRECTED)
                fam3 = corrected_ci(values, Z_FAMILY3)
                print(
                    f"  bucket={bucket:17s} h{h:<3d} n={n:5d} mean={mean*100:+.3f}% "
                    f"uncorrected_CI=[{unc[0]*100:+.3f}%,{unc[1]*100:+.3f}%] "
                    f"family3_CI=[{fam3[0]*100:+.3f}%,{fam3[1]*100:+.3f}%]"
                )

    print()
    print("=" * 100)
    print("Raw sample counts per cell (for the INSUFFICIENT_DATA / decision-rule check)")
    print("=" * 100)
    for (split, bucket, h), values in results.items():
        print(f"  {split:15s} {bucket:17s} h{h:<3d} n={len(values)}")


if __name__ == "__main__":
    main()
