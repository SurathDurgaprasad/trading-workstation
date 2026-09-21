"""DERIV_001 -- does NIFTY futures basis add incremental out-of-sample
predictive information beyond the existing OHLCV feature set?

Executes exactly what
docs/research/DERIV_001_FUTURES_BASIS_INFORMATION_CONTENT_PREREGISTRATION.md
pre-registered, no deviation. Isolated audit script: reuses market.indicators,
quant_research.alpha_features, backtesting.splits completely unmodified. The
one genuinely new piece of retrieval (Dhan's continuous NIFTY futures series)
is a small, local fetch function -- not a production module change, matching
this project's own "isolated audit script" precedent (e.g. h_meanrev_013's
own local dataset-building function).

Never touches the live fleet. Never modifies any production file. Read-only
Dhan Data API call (already-credentialed, already-subscribed), no order
placement of any kind.
"""
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(r"C:\Users\durgaprasad.surath\OneDrive - Ideabytes\Documents\Working With AI\ai_trade\TradingAgents")
sys.path.insert(0, str(REPO_ROOT))

import numpy as np
import pandas as pd
import requests
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, roc_auc_score

from backtesting.cache import CachedMarketDataProvider
from backtesting.splits import split_periods
from market.data_provider import get_market_data_provider
from market.indicators import compute_indicator_series
from quant_research.alpha_features import add_alpha_features, add_forward_return_targets

NIFTY_FUTIDX_SECURITY_ID = "68407"  # NIFTY-Sep2026-FUT at time of writing -- only used to ROUTE the
# request; Dhan's own relative expiryCode=0 selector resolves the actual historical front-month
# contract internally (verified this session: a wide date range on this ID returned a real,
# economically sensible 2019-2026 continuous series, not just this one contract's own short life).
HORIZON = 10
MIN_SAMPLE_PER_SPLIT = 100
AUC_IMPROVEMENT_THRESHOLD = 0.02


def fetch_nifty_futures_series() -> pd.DataFrame:
    """Real, live, credentialed Dhan Data API call -- read-only, no order
    capability touched. Returns a DataFrame indexed by date with columns
    futures_close, futures_oi."""
    headers = {
        "Content-Type": "application/json",
        "access-token": os.environ["DHAN_ACCESS_TOKEN"],
        "client-id": os.environ["DHAN_CLIENT_ID"],
    }
    body = {
        "securityId": NIFTY_FUTIDX_SECURITY_ID, "exchangeSegment": "NSE_FNO", "instrument": "FUTIDX",
        "expiryCode": 0, "oi": True, "fromDate": "2016-01-01", "toDate": datetime.now().strftime("%Y-%m-%d"),
    }
    resp = requests.post("https://api.dhan.co/v2/charts/historical", headers=headers, json=body, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    dates = [datetime.fromtimestamp(t, tz=timezone.utc).date() for t in data["timestamp"]]
    frame = pd.DataFrame({"futures_close": data["close"], "futures_oi": data["open_interest"]}, index=pd.DatetimeIndex(dates))
    frame.index.name = "date"
    return frame


def main():
    import dotenv
    dotenv.load_dotenv(REPO_ROOT / ".env")

    print("=" * 100)
    print("DERIV_001 -- NIFTY futures basis information-content test")
    print("=" * 100)

    futures = fetch_nifty_futures_series()
    print(f"Futures series: {len(futures)} bars, {futures.index.min().date()} to {futures.index.max().date()}")

    provider = CachedMarketDataProvider(get_market_data_provider())
    spot_ohlcv = provider.fetch_ohlcv("^NSEI", period="10y", interval="1d")
    spot = compute_indicator_series(spot_ohlcv)
    spot = add_alpha_features(spot, market_series=None)  # zscore_close_20 does not depend on market_series; relative_strength_20 (unused here) would be all-NaN, disclosed, not used
    spot = add_forward_return_targets(spot, horizons=(5, HORIZON))
    print(f"Spot series: {len(spot)} bars, {spot.index.min().date()} to {spot.index.max().date()}")

    spot.index = pd.DatetimeIndex([pd.Timestamp(d).normalize() for d in spot.index])
    futures.index = pd.DatetimeIndex([pd.Timestamp(d).normalize() for d in futures.index])

    merged = spot.join(futures, how="inner")
    merged["futures_basis"] = (merged["futures_close"] - merged["close"]) / merged["close"]
    merged["trend_ratio"] = merged["sma_20"] / merged["sma_50"] - 1
    merged["atr_pct"] = merged["atr_14"] / merged["close"]
    print(f"Merged (spot+futures overlap) frame: {len(merged)} bars, {merged.index.min().date()} to {merged.index.max().date()}")

    baseline_features = ["trend_ratio", "rsi_14", "atr_pct", "zscore_close_20"]
    augmented_features = baseline_features + ["futures_basis"]
    merged[f"target_h{HORIZON}"] = (merged[f"fwd_return_{HORIZON}"] > 0).astype(int)

    usable = merged.dropna(subset=augmented_features + [f"target_h{HORIZON}"]).copy()
    print(f"Usable (non-NaN feature+target) rows: {len(usable)}")

    split = split_periods(usable.index[0], usable.index[-1])
    dev = usable[(usable.index >= split.development_start) & (usable.index <= split.development_end)]
    val = usable[(usable.index >= split.validation_start) & (usable.index <= split.validation_end)]
    oos = usable[(usable.index >= split.out_of_sample_start) & (usable.index <= split.out_of_sample_end)]
    print(f"development n={len(dev)}  validation n={len(val)}  out_of_sample n={len(oos)}")

    for label, sub in [("development", dev), ("validation", val), ("out_of_sample", oos)]:
        if len(sub) < MIN_SAMPLE_PER_SPLIT:
            print(f"WARNING: {label} split has n={len(sub)} < MIN_SAMPLE_PER_SPLIT={MIN_SAMPLE_PER_SPLIT}")

    baseline_model = LogisticRegression(max_iter=1000).fit(dev[baseline_features], dev[f"target_h{HORIZON}"])
    augmented_model = LogisticRegression(max_iter=1000).fit(dev[augmented_features], dev[f"target_h{HORIZON}"])

    results = {}
    print()
    print("=" * 100)
    print("RESULTS -- baseline (OHLCV-only) vs augmented (OHLCV + futures_basis)")
    print("=" * 100)
    for label, sub in [("validation", val), ("out_of_sample", oos)]:
        y_true = sub[f"target_h{HORIZON}"].values
        p_base = baseline_model.predict_proba(sub[baseline_features])[:, 1]
        p_aug = augmented_model.predict_proba(sub[augmented_features])[:, 1]
        auc_base, auc_aug = roc_auc_score(y_true, p_base), roc_auc_score(y_true, p_aug)
        brier_base, brier_aug = brier_score_loss(y_true, p_base), brier_score_loss(y_true, p_aug)
        results[label] = {"auc_base": auc_base, "auc_aug": auc_aug, "brier_base": brier_base, "brier_aug": brier_aug, "n": len(sub)}
        print(f"\n--- {label} (n={len(sub)}) ---")
        print(f"  baseline  AUC={auc_base:.4f}  Brier={brier_base:.4f}")
        print(f"  augmented AUC={auc_aug:.4f}  Brier={brier_aug:.4f}")
        print(f"  delta     AUC={auc_aug-auc_base:+.4f}  Brier={brier_aug-brier_base:+.4f} (negative delta-Brier = improvement)")

    print()
    print("=" * 100)
    print("CALIBRATION -- augmented model, out_of_sample, predicted-probability deciles vs realized frequency")
    print("=" * 100)
    p_aug_oos = augmented_model.predict_proba(oos[augmented_features])[:, 1]
    calib_df = pd.DataFrame({"p": p_aug_oos, "y": oos[f"target_h{HORIZON}"].values})
    calib_df["decile"] = pd.qcut(calib_df["p"], 10, duplicates="drop", labels=False)
    calib = calib_df.groupby("decile").agg(mean_predicted=("p", "mean"), realized_freq=("y", "mean"), n=("y", "count"))
    print(calib.to_string())

    print()
    print("=" * 100)
    print("DECISION RULE CHECK (frozen, section 9)")
    print("=" * 100)
    val_pass = results["validation"]["auc_aug"] - results["validation"]["auc_base"] >= AUC_IMPROVEMENT_THRESHOLD
    oos_pass = results["out_of_sample"]["auc_aug"] - results["out_of_sample"]["auc_base"] >= AUC_IMPROVEMENT_THRESHOLD
    brier_ok = results["validation"]["brier_aug"] <= results["validation"]["brier_base"] and results["out_of_sample"]["brier_aug"] <= results["out_of_sample"]["brier_base"]
    print(f"Validation delta-AUC >= {AUC_IMPROVEMENT_THRESHOLD}: {val_pass} (delta-AUC={results['validation']['auc_aug']-results['validation']['auc_base']:+.4f})")
    print(f"OOS delta-AUC >= {AUC_IMPROVEMENT_THRESHOLD}: {oos_pass} (delta-AUC={results['out_of_sample']['auc_aug']-results['out_of_sample']['auc_base']:+.4f})")
    print(f"Brier does not worsen on either split: {brier_ok}")
    verdict = "MEANINGFUL INCREMENTAL INFORMATION" if (val_pass and oos_pass and brier_ok) else "NO MEANINGFUL INCREMENTAL INFORMATION"
    print(f"\nVERDICT: {verdict}")

    out_path = REPO_ROOT / "audit" / "derivatives_research" / "DERIV_001_RESULTS.csv"
    usable[augmented_features + [f"fwd_return_{HORIZON}", f"target_h{HORIZON}"]].to_csv(out_path)
    print(f"\nFull feature/target data written to {out_path}")


if __name__ == "__main__":
    main()
