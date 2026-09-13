"""ml_research/run_experiment.py -- executes the frozen ML_PHASE1_v1
experiment end to end: fetch -> features -> labels -> join -> walk-forward
-> fit -> evaluate -> compare against the deterministic benchmark ->
persist artifacts. Standalone script, not wired into main.py's CLI
(consistent with quant_research/'s own architectural isolation --
PHASE_1_IMPLEMENTATION_SPEC.md Section 2, out of scope: "Wiring the
model's output into decision_engine/, paper/, or any live command").

Run: venv/Scripts/python.exe -m ml_research.run_experiment
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import pandas as pd

from backtesting.cache import CachedMarketDataProvider
from market.data_provider import get_market_data_provider
from market_intelligence.nse_sector_map import NSE_SECTOR_MAP
from quant_research.universe_expansion import ORIGINAL_32_NSE_UNIVERSE

from ml_research import baseline_model, dataset, evaluation, expected_value, features, labels, walk_forward

EXPERIMENT_VERSION = "ML_PHASE1_v1"
INTERVAL = "5m"
PERIOD = "60d"
BENCHMARK_SYMBOL = "^NSEI"
UNIVERSE_VERSION = "ORIGINAL_32_NSE_UNIVERSE"
N_TEST_SESSIONS = 12
N_FOLDS = 4
VALIDATION_SESSIONS_PER_FOLD = 7
EMBARGO_SESSIONS = 1

DATA_ROOT = PROJECT_ROOT / "data" / "ml_research"
ARTIFACTS_PATH = DATA_ROOT / "phase1_results.json"


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def fetch_all(symbols: list[str]) -> tuple[dict[str, pd.DataFrame], pd.Series]:
    provider = CachedMarketDataProvider(get_market_data_provider())
    benchmark_ohlcv = provider.fetch_ohlcv(BENCHMARK_SYMBOL, period=PERIOD, interval=INTERVAL)
    benchmark_frame = benchmark_ohlcv.to_dataframe()
    benchmark_close = benchmark_frame["Close"]
    log(f"Benchmark {BENCHMARK_SYMBOL}: {len(benchmark_close)} bars")

    symbol_frames: dict[str, pd.DataFrame] = {}
    for i, symbol in enumerate(symbols):
        ohlcv = provider.fetch_ohlcv(symbol, period=PERIOD, interval=INTERVAL)
        bars = features.build_symbol_bars(symbol, ohlcv)
        frame = features.add_features(bars, benchmark_close=benchmark_close)
        symbol_frames[symbol] = frame
        if (i + 1) % 8 == 0:
            log(f"  built features for {i + 1}/{len(symbols)} symbols")
    log(f"Built per-symbol feature frames for {len(symbol_frames)} symbols")
    return symbol_frames, benchmark_close


def build_dataset(symbol_frames: dict[str, pd.DataFrame]) -> tuple[pd.DataFrame, pd.DataFrame]:
    symbol_frames = features.add_sector_strength_score(symbol_frames, NSE_SECTOR_MAP)
    symbol_frames = {sym: features.add_composite_score(f) for sym, f in symbol_frames.items()}

    feature_version = features.feature_version()
    data_version = "yfinance_5m_60d_" + time.strftime("%Y%m%d")

    all_features = []
    all_labels = []
    for symbol, frame in symbol_frames.items():
        # The index is named "Date" (OHLCV.to_dataframe()'s own convention,
        # inherited through compute_indicator_series) -- rename the AXIS
        # explicitly so this doesn't depend on the index happening to be
        # unnamed (reset_index() only produces a literal "index" column
        # for an unnamed index).
        frame = frame.rename_axis("timestamp").reset_index()
        frame["feature_version"] = feature_version
        frame["data_version"] = data_version
        all_features.append(frame)

        label_rows = labels.build_labels_for_symbol(symbol, symbol_frames[symbol])
        all_labels.append(labels.labels_to_frame(label_rows))

    features_frame = pd.concat(all_features, ignore_index=True)
    labels_frame = pd.concat(all_labels, ignore_index=True)
    log(f"Concatenated: {len(features_frame)} feature rows, {len(labels_frame)} label rows across {len(symbol_frames)} symbols")
    return features_frame, labels_frame


def persist_datasets(features_frame: pd.DataFrame, labels_frame: pd.DataFrame) -> None:
    features_dir = DATA_ROOT / "features" / f"experiment_version={EXPERIMENT_VERSION}"
    labels_dir = DATA_ROOT / "labels" / f"experiment_version={EXPERIMENT_VERSION}"
    features_dir.mkdir(parents=True, exist_ok=True)
    labels_dir.mkdir(parents=True, exist_ok=True)
    features_frame.to_parquet(features_dir / "features.parquet", index=False)
    labels_frame.to_parquet(labels_dir / "labels.parquet", index=False)
    log(f"Persisted features -> {features_dir / 'features.parquet'} ({len(features_frame)} rows)")
    log(f"Persisted labels -> {labels_dir / 'labels.parquet'} ({len(labels_frame)} rows)")


def split_by_sessions(merged: pd.DataFrame, sessions: tuple) -> pd.DataFrame:
    return merged[merged["session_date"].isin(sessions)]


def run_fold(merged: pd.DataFrame, fold, feature_columns: tuple[str, ...]) -> dict:
    train = split_by_sessions(merged, fold.train_sessions)
    validate = split_by_sessions(merged, fold.validate_sessions)

    fitted = baseline_model.fit_fold(train, feature_columns, fold_index=fold.fold_index)
    validate = validate.copy()
    validate["p_target"] = baseline_model.predict_proba(fitted, validate)

    disc = evaluation.compute_discrimination_metrics(validate["label_target_first"], validate["p_target"])
    ev_model = expected_value.compute_expected_value(validate.dropna(subset=["p_target"]), p_target_col="p_target")
    ev_rule = expected_value.deterministic_rule_expected_value(validate)

    return {
        "fold_index": fold.fold_index,
        "n_train_rows": fitted.n_train_rows,
        "n_train_rows_complete_case": fitted.n_train_rows_complete_case,
        "n_validate_rows": len(validate),
        "coefficients": fitted.coefficients,
        "intercept": fitted.intercept,
        "discrimination": disc,
        "model_expected_net_returns": ev_model["expected_net_return"].dropna().tolist(),
        "deterministic_net_returns_where_traded": ev_rule.loc[ev_rule["deterministic_would_trade"], "deterministic_net_return"].tolist(),
        "deterministic_trade_count": int(ev_rule["deterministic_would_trade"].sum()),
    }


def main() -> None:
    symbols = list(ORIGINAL_32_NSE_UNIVERSE)
    log(f"Universe: {UNIVERSE_VERSION}, {len(symbols)} symbols")

    symbol_frames, benchmark_close = fetch_all(symbols)
    features_frame, labels_frame = build_dataset(symbol_frames)
    persist_datasets(features_frame, labels_frame)

    merged = dataset.join_features_and_labels(features_frame, labels_frame)
    log(f"Joined dataset: {len(merged)} rows (join-safety assertion passed)")

    meta = dataset.dataset_metadata(
        merged, experiment_version=EXPERIMENT_VERSION, feature_version=features.feature_version(),
        label_version=labels.label_version(), universe_version=UNIVERSE_VERSION,
    )
    log(f"Dataset metadata: {meta}")

    all_sessions = sorted(merged["session_date"].unique().tolist())
    log(f"Distinct sessions in joined dataset: {len(all_sessions)}")

    plan = walk_forward.build_walk_forward_plan(
        all_sessions, n_test_sessions=N_TEST_SESSIONS, n_folds=N_FOLDS,
        validation_sessions_per_fold=VALIDATION_SESSIONS_PER_FOLD, embargo_sessions=EMBARGO_SESSIONS,
    )
    log(f"Walk-forward plan: {len(plan.folds)} folds, pool={len(plan.walk_forward_pool_sessions)} sessions, test={len(plan.test_sessions)} sessions")

    fold_results = []
    for fold in plan.folds:
        log(f"Running fold {fold.fold_index}: train={len(fold.train_sessions)} sessions, embargo={len(fold.embargo_sessions)}, validate={len(fold.validate_sessions)}")
        result = run_fold(merged, fold, dataset.FEATURE_COLUMNS)
        fold_results.append(result)
        d = result["discrimination"]
        log(f"  fold {fold.fold_index}: n_validate={result['n_validate_rows']} roc_auc={d.roc_auc} brier={d.brier_score:.4f} n_model_ev_rows={len(result['model_expected_net_returns'])}")

    # Final refit on the FULL walk-forward pool, evaluated once on the held-out test window.
    log("Fitting final model on the full walk-forward pool for the held-out test evaluation...")
    pool_train = split_by_sessions(merged, plan.walk_forward_pool_sessions)
    test_frame = split_by_sessions(merged, plan.test_sessions).copy()
    final_fitted = baseline_model.fit_fold(pool_train, dataset.FEATURE_COLUMNS, fold_index=0)
    test_frame["p_target"] = baseline_model.predict_proba(final_fitted, test_frame)
    test_disc = evaluation.compute_discrimination_metrics(test_frame["label_target_first"], test_frame["p_target"])
    test_ev_model = expected_value.compute_expected_value(test_frame.dropna(subset=["p_target"]), p_target_col="p_target")
    test_ev_rule = expected_value.deterministic_rule_expected_value(test_frame)
    test_calibration = evaluation.calibration_table(test_frame["label_target_first"], test_frame["p_target"])
    log(f"Held-out test: n={len(test_frame)} roc_auc={test_disc.roc_auc} brier={test_disc.brier_score:.4f}")

    # development = folds 1-2 pooled, validation = folds 3-4 pooled, out_of_sample = held-out test.
    development_model = fold_results[0]["model_expected_net_returns"] + fold_results[1]["model_expected_net_returns"]
    validation_model = fold_results[2]["model_expected_net_returns"] + fold_results[3]["model_expected_net_returns"]
    out_of_sample_model = test_ev_model["expected_net_return"].dropna().tolist()

    development_rule = fold_results[0]["deterministic_net_returns_where_traded"] + fold_results[1]["deterministic_net_returns_where_traded"]
    validation_rule = fold_results[2]["deterministic_net_returns_where_traded"] + fold_results[3]["deterministic_net_returns_where_traded"]
    out_of_sample_rule = test_ev_rule.loc[test_ev_rule["deterministic_would_trade"], "deterministic_net_return"].tolist()

    log(f"Model split sizes: dev={len(development_model)} val={len(validation_model)} oos={len(out_of_sample_model)}")
    log(f"Rule split sizes:  dev={len(development_rule)} val={len(validation_rule)} oos={len(out_of_sample_rule)}")

    model_promotion = evaluation.evaluate_economic_significance(
        "ML_PHASE1_v1_logistic_regression",
        development_returns=development_model, validation_returns=validation_model, out_of_sample_returns=out_of_sample_model,
    )
    rule_promotion = evaluation.evaluate_economic_significance(
        "ML_PHASE1_v1_deterministic_benchmark",
        development_returns=development_rule, validation_returns=validation_rule, out_of_sample_returns=out_of_sample_rule,
    )

    log(f"MODEL promotion verdict: {model_promotion.verdict}")
    log(f"RULE  promotion verdict: {rule_promotion.verdict}")

    results = {
        "meta": meta,
        "walk_forward_plan": {
            "pool_sessions": [str(s) for s in plan.walk_forward_pool_sessions],
            "test_sessions": [str(s) for s in plan.test_sessions],
            "folds": [
                {
                    "fold_index": f.fold_index, "train_sessions": [str(s) for s in f.train_sessions],
                    "embargo_sessions": [str(s) for s in f.embargo_sessions],
                    "validate_sessions": [str(s) for s in f.validate_sessions],
                }
                for f in plan.folds
            ],
        },
        "fold_results": [
            {
                "fold_index": r["fold_index"], "n_train_rows": r["n_train_rows"],
                "n_train_rows_complete_case": r["n_train_rows_complete_case"], "n_validate_rows": r["n_validate_rows"],
                "coefficients": r["coefficients"], "intercept": r["intercept"],
                "roc_auc": r["discrimination"].roc_auc, "pr_auc": r["discrimination"].pr_auc,
                "log_loss": r["discrimination"].log_loss, "brier_score": r["discrimination"].brier_score,
                "positive_rate": r["discrimination"].positive_rate,
                "deterministic_trade_count": r["deterministic_trade_count"],
            }
            for r in fold_results
        ],
        "held_out_test": {
            "n": test_disc.n, "roc_auc": test_disc.roc_auc, "pr_auc": test_disc.pr_auc,
            "log_loss": test_disc.log_loss, "brier_score": test_disc.brier_score, "positive_rate": test_disc.positive_rate,
            "calibration_table": test_calibration.assign(bucket=lambda d: d["bucket"].astype(str)).to_dict(orient="records"),
            "deterministic_trade_count": int(test_ev_rule["deterministic_would_trade"].sum()),
            "model_mean_expected_net_return": float(np.mean(out_of_sample_model)) if out_of_sample_model else None,
            "rule_mean_net_return": float(np.mean(out_of_sample_rule)) if out_of_sample_rule else None,
        },
        "promotion": {
            "model": {
                "verdict": str(model_promotion.verdict), "rationale": model_promotion.rationale,
                "development": {"expectancy": model_promotion.development.expectancy, "sample_size": model_promotion.development.sample_size, "verdict": str(model_promotion.development.verdict), "mean_return_ci_low": model_promotion.development.mean_return_ci_low, "mean_return_ci_high": model_promotion.development.mean_return_ci_high},
                "validation": {"expectancy": model_promotion.validation.expectancy, "sample_size": model_promotion.validation.sample_size, "verdict": str(model_promotion.validation.verdict), "mean_return_ci_low": model_promotion.validation.mean_return_ci_low, "mean_return_ci_high": model_promotion.validation.mean_return_ci_high},
                "out_of_sample": {"expectancy": model_promotion.out_of_sample.expectancy, "sample_size": model_promotion.out_of_sample.sample_size, "verdict": str(model_promotion.out_of_sample.verdict), "mean_return_ci_low": model_promotion.out_of_sample.mean_return_ci_low, "mean_return_ci_high": model_promotion.out_of_sample.mean_return_ci_high},
            },
            "deterministic_rule": {
                "verdict": str(rule_promotion.verdict), "rationale": rule_promotion.rationale,
                "development": {"expectancy": rule_promotion.development.expectancy, "sample_size": rule_promotion.development.sample_size, "verdict": str(rule_promotion.development.verdict), "mean_return_ci_low": rule_promotion.development.mean_return_ci_low, "mean_return_ci_high": rule_promotion.development.mean_return_ci_high},
                "validation": {"expectancy": rule_promotion.validation.expectancy, "sample_size": rule_promotion.validation.sample_size, "verdict": str(rule_promotion.validation.verdict), "mean_return_ci_low": rule_promotion.validation.mean_return_ci_low, "mean_return_ci_high": rule_promotion.validation.mean_return_ci_high},
                "out_of_sample": {"expectancy": rule_promotion.out_of_sample.expectancy, "sample_size": rule_promotion.out_of_sample.sample_size, "verdict": str(rule_promotion.out_of_sample.verdict), "mean_return_ci_low": rule_promotion.out_of_sample.mean_return_ci_low, "mean_return_ci_high": rule_promotion.out_of_sample.mean_return_ci_high},
            },
        },
        "cost_model_disclosure": "CostModel.india_nse_intraday_2026() -- GST, stamp duty, and SEBI charges are NOT included in this preset.",
        "sector_strength_score_coverage": f"{sum(1 for s in symbols if s in NSE_SECTOR_MAP)}/{len(symbols)} symbols tagged via NSE_SECTOR_MAP; untagged symbols have sector_strength_score=NaN, complete-case-dropped by the model.",
    }

    ARTIFACTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACTS_PATH.write_text(json.dumps(results, indent=2, default=str))
    log(f"Wrote results to {ARTIFACTS_PATH}")


if __name__ == "__main__":
    main()
