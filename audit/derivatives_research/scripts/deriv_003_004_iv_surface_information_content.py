"""DERIV_003/DERIV_004 -- do ATM IV level and put/call IV skew add
incremental out-of-sample predictive information beyond the OHLCV +
futures baseline?

Executes exactly what
docs/research/DERIV_003_004_IV_SURFACE_INFORMATION_CONTENT_PREREGISTRATION.md
pre-registered, no deviation. Reuses quant_research/iv_surface.py's own
tested quality-gate/feature functions unmodified. Real, live, paced,
read-only Dhan Data API calls (already-credentialed) -- no order
placement of any kind.
"""
import os
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]  # audit/<family>/scripts/this_file.py -> repo root
sys.path.insert(0, str(REPO_ROOT))

import pandas as pd
import requests
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, roc_auc_score

from backtesting.cache import CachedMarketDataProvider
from backtesting.splits import split_periods
from market.data_provider import get_market_data_provider
from market.indicators import compute_indicator_series
from quant_research.alpha_features import add_alpha_features, add_forward_return_targets
from quant_research.iv_surface import OptionRollingBar, compute_atm_iv_level, compute_put_call_iv_skew
from strategy.multiple_testing import bonferroni_corrected_z

NIFTY_FUTIDX_SECURITY_ID = "68407"
NIFTY_OPTIDX_SECURITY_ID = "13"
HORIZON = 10
MIN_SAMPLE_PER_SPLIT = 100
AUC_IMPROVEMENT_THRESHOLD = 0.02
FETCH_WINDOW_DAYS = 29  # strictly under the endpoint's own documented 30-day cap
FETCH_YEARS_BACK = 2.2
REQUEST_PACING_SECONDS = 1.0


def _headers():
    return {"Content-Type": "application/json", "access-token": os.environ["DHAN_ACCESS_TOKEN"], "client-id": os.environ["DHAN_CLIENT_ID"]}


def fetch_rolling_option_window(option_type: str, from_date: date, to_date: date) -> list[OptionRollingBar]:
    body = {
        "exchangeSegment": "NSE_FNO", "interval": "60", "securityId": NIFTY_OPTIDX_SECURITY_ID, "instrument": "OPTIDX",
        "expiryFlag": "MONTH", "expiryCode": 1, "strike": "ATM", "drvOptionType": option_type,
        "requiredData": ["open", "high", "low", "close", "iv", "volume", "strike", "oi", "spot"],
        "fromDate": from_date.strftime("%Y-%m-%d"), "toDate": to_date.strftime("%Y-%m-%d"),
    }
    resp = requests.post("https://api.dhan.co/v2/charts/rollingoption", headers=_headers(), json=body, timeout=30)
    if resp.status_code != 200:
        return []
    data = resp.json().get("data", {})
    side = data.get("ce" if option_type == "CALL" else "pe")
    if not side or not side.get("timestamp"):
        return []
    bars = []
    n = len(side["timestamp"])
    for i in range(n):
        try:
            ts = datetime.fromtimestamp(side["timestamp"][i], tz=timezone.utc)
            bars.append(OptionRollingBar(
                timestamp=ts, strike=float(side["strike"][i]), option_type="CE" if option_type == "CALL" else "PE",
                iv=float(side["iv"][i]), oi=int(side["oi"][i]), volume=int(side["volume"][i]),
                spot=float(side["spot"][i]), close=float(side["close"][i]),
            ))
        except (KeyError, IndexError, TypeError, ValueError):
            continue
    return bars


def fetch_full_iv_series(option_type: str, years_back: float) -> list[OptionRollingBar]:
    end = date.today()
    start = end - timedelta(days=int(years_back * 365.25))
    all_bars: list[OptionRollingBar] = []
    window_start = start
    n_windows = 0
    while window_start < end:
        window_end = min(window_start + timedelta(days=FETCH_WINDOW_DAYS), end)
        bars = fetch_rolling_option_window(option_type, window_start, window_end)
        all_bars.extend(bars)
        n_windows += 1
        window_start = window_end
        time.sleep(REQUEST_PACING_SECONDS)
    print(f"  {option_type}: {n_windows} windows fetched, {len(all_bars)} raw bars")
    return sorted(all_bars, key=lambda b: b.timestamp)


def daily_last_value(series: pd.Series) -> pd.Series:
    """Downsamples an intraday series to one value per trading day -- the
    LAST valid (already quality-gated) reading of that day, matching how
    'close' is used as the representative daily value throughout this
    project's existing OHLCV pipeline."""
    if series.empty:
        return series
    df = series.to_frame("value")
    df["trade_date"] = df.index.date
    daily = df.groupby("trade_date")["value"].last()
    daily.index = pd.DatetimeIndex(daily.index)
    return daily


def fetch_nifty_futures_series() -> pd.DataFrame:
    body = {
        "securityId": NIFTY_FUTIDX_SECURITY_ID, "exchangeSegment": "NSE_FNO", "instrument": "FUTIDX",
        "expiryCode": 0, "oi": True, "fromDate": "2016-01-01", "toDate": datetime.now().strftime("%Y-%m-%d"),
    }
    resp = requests.post("https://api.dhan.co/v2/charts/historical", headers=_headers(), json=body, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    dates = [datetime.fromtimestamp(t, tz=timezone.utc).date() for t in data["timestamp"]]
    frame = pd.DataFrame({"futures_close": data["close"], "futures_oi": data["open_interest"]}, index=pd.DatetimeIndex(dates))
    frame.index.name = "date"
    return frame


def evaluate(label: str, baseline_model, augmented_model, baseline_features, augmented_features, sub: pd.DataFrame, target_col: str) -> dict:
    y_true = sub[target_col].values
    p_base = baseline_model.predict_proba(sub[baseline_features])[:, 1]
    p_aug = augmented_model.predict_proba(sub[augmented_features])[:, 1]
    auc_base, auc_aug = roc_auc_score(y_true, p_base), roc_auc_score(y_true, p_aug)
    brier_base, brier_aug = brier_score_loss(y_true, p_base), brier_score_loss(y_true, p_aug)
    print(f"  {label} (n={len(sub)}): baseline AUC={auc_base:.4f} Brier={brier_base:.4f}  |  "
          f"augmented AUC={auc_aug:.4f} Brier={brier_aug:.4f}  |  delta AUC={auc_aug-auc_base:+.4f} delta Brier={brier_aug-brier_base:+.4f}")
    return {"auc_base": auc_base, "auc_aug": auc_aug, "brier_base": brier_base, "brier_aug": brier_aug}


def main():
    import dotenv
    dotenv.load_dotenv(REPO_ROOT / ".env")

    print("=" * 100)
    print("DERIV_003/004 -- NIFTY ATM IV level & put/call IV skew information-content test")
    print("=" * 100)

    print("\nFetching NIFTY ATM CALL/PUT rolling-option IV data (paced, ~29-day windows)...")
    call_bars = fetch_full_iv_series("CALL", FETCH_YEARS_BACK)
    put_bars = fetch_full_iv_series("PUT", FETCH_YEARS_BACK)

    atm_iv_level_hourly = compute_atm_iv_level(call_bars)
    put_call_skew_hourly = compute_put_call_iv_skew(call_bars, put_bars)
    print(f"\nAfter Phase 2/3 quality gate: atm_iv_level hourly bars={len(atm_iv_level_hourly)}, put_call_iv_skew hourly bars={len(put_call_skew_hourly)}")

    atm_iv_level = daily_last_value(atm_iv_level_hourly)
    put_call_iv_skew = daily_last_value(put_call_skew_hourly)
    print(f"Daily (last-valid-hourly-reading): atm_iv_level={len(atm_iv_level)} days, put_call_iv_skew={len(put_call_iv_skew)} days")

    print("\nFetching NIFTY futures (already-continuous series) and spot...")
    futures = fetch_nifty_futures_series()
    provider = CachedMarketDataProvider(get_market_data_provider())
    spot_ohlcv = provider.fetch_ohlcv("^NSEI", period="10y", interval="1d")
    spot = compute_indicator_series(spot_ohlcv)
    spot = add_alpha_features(spot, market_series=None)
    spot = add_forward_return_targets(spot, horizons=(5, HORIZON))
    spot.index = pd.DatetimeIndex([pd.Timestamp(d).normalize() for d in spot.index])
    futures.index = pd.DatetimeIndex([pd.Timestamp(d).normalize() for d in futures.index])

    merged = spot.join(futures, how="inner")
    merged["futures_basis"] = (merged["futures_close"] - merged["close"]) / merged["close"]
    merged["futures_oi_change_pct"] = merged["futures_oi"].pct_change()
    merged["trend_ratio"] = merged["sma_20"] / merged["sma_50"] - 1
    merged["atr_pct"] = merged["atr_14"] / merged["close"]
    merged["atm_iv_level"] = atm_iv_level
    merged["put_call_iv_skew"] = put_call_iv_skew
    merged[f"target_h{HORIZON}"] = (merged[f"fwd_return_{HORIZON}"] > 0).astype(int)
    print(f"\nFull merged frame (spot+futures+options overlap): {len(merged)} rows, {merged.index.min().date()} to {merged.index.max().date()}")

    baseline_features = ["trend_ratio", "rsi_14", "atr_pct", "zscore_close_20", "futures_basis", "futures_oi_change_pct"]
    target_col = f"target_h{HORIZON}"

    results_all = {}
    for name, aug_col in [("DERIV_003 (atm_iv_level)", "atm_iv_level"), ("DERIV_004 (put_call_iv_skew)", "put_call_iv_skew")]:
        augmented_features = baseline_features + [aug_col]
        usable = merged.dropna(subset=augmented_features + [target_col]).copy()
        print()
        print("=" * 100)
        print(f"{name} -- usable rows: {len(usable)}")
        print("=" * 100)
        if len(usable) < 3 * MIN_SAMPLE_PER_SPLIT:
            print(f"  INSUFFICIENT total sample (need >= {3*MIN_SAMPLE_PER_SPLIT} for a 60/20/20 split each >= {MIN_SAMPLE_PER_SPLIT}) -- skipping model fit, recording as a data-adequacy limitation.")
            results_all[name] = None
            continue

        split = split_periods(usable.index[0], usable.index[-1])
        dev = usable[(usable.index >= split.development_start) & (usable.index <= split.development_end)]
        val = usable[(usable.index >= split.validation_start) & (usable.index <= split.validation_end)]
        oos = usable[(usable.index >= split.out_of_sample_start) & (usable.index <= split.out_of_sample_end)]
        print(f"  development n={len(dev)}  validation n={len(val)}  out_of_sample n={len(oos)}")
        for label, sub in [("development", dev), ("validation", val), ("out_of_sample", oos)]:
            if len(sub) < MIN_SAMPLE_PER_SPLIT:
                print(f"  WARNING: {label} split has n={len(sub)} < MIN_SAMPLE_PER_SPLIT={MIN_SAMPLE_PER_SPLIT}")

        baseline_model = LogisticRegression(max_iter=1000).fit(dev[baseline_features], dev[target_col])
        augmented_model = LogisticRegression(max_iter=1000).fit(dev[augmented_features], dev[target_col])

        split_results = {}
        for label, sub in [("validation", val), ("out_of_sample", oos)]:
            split_results[label] = evaluate(label, baseline_model, augmented_model, baseline_features, augmented_features, sub, target_col)
        results_all[name] = split_results

        out_path = REPO_ROOT / "audit" / "derivatives_research" / f"{name.split()[0]}_RESULTS.csv"
        usable[augmented_features + [f"fwd_return_{HORIZON}", target_col]].to_csv(out_path)
        print(f"  Written to {out_path}")

    print()
    print("=" * 100)
    print("DECISION RULE CHECK (frozen, section 7)")
    print("=" * 100)
    for name, res in results_all.items():
        if res is None:
            print(f"{name}: INSUFFICIENT DATA -- cannot evaluate the decision rule.")
            continue
        val_pass = res["validation"]["auc_aug"] - res["validation"]["auc_base"] >= AUC_IMPROVEMENT_THRESHOLD
        oos_pass = res["out_of_sample"]["auc_aug"] - res["out_of_sample"]["auc_base"] >= AUC_IMPROVEMENT_THRESHOLD
        brier_ok = res["validation"]["brier_aug"] <= res["validation"]["brier_base"] and res["out_of_sample"]["brier_aug"] <= res["out_of_sample"]["brier_base"]
        verdict = "MEANINGFUL INCREMENTAL INFORMATION" if (val_pass and oos_pass and brier_ok) else "NO MEANINGFUL INCREMENTAL INFORMATION"
        print(f"{name}: val delta-AUC={res['validation']['auc_aug']-res['validation']['auc_base']:+.4f} "
              f"oos delta-AUC={res['out_of_sample']['auc_aug']-res['out_of_sample']['auc_base']:+.4f} "
              f"brier_ok={brier_ok} -> {verdict}")

    z2 = bonferroni_corrected_z(2)
    z4 = bonferroni_corrected_z(4)
    print(f"\nFamily-size context: family_size=2 (this pass) z={z2:.4f}; family_size=4 (whole derivatives program) z={z4:.4f} (disclosure only, not a re-decision).")


if __name__ == "__main__":
    main()
