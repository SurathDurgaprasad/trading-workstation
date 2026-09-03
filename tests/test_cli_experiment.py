"""Phase 37 -- `main.py experiment start|end|list|compare` CLI. No real
network anywhere in this file: experiment registration only reads the
CURRENT default config's own deterministic version_id() (a pure, local
computation), and compare only reads already-persisted stores."""

from datetime import datetime, timezone

import pytest

from decision_engine.models import Decision, DecisionLabel, RiskContext
from decision_engine.store import DecisionStore
from main import parse_args, run_experiment_command
from market_intelligence.models import CandidateScore
from predictions.models import PredictionEvaluation, PredictionOutcomeState, PredictionRecord
from predictions.store import PredictionStore


def _run(argv, db_path):
    args = parse_args(["experiment", *argv, "--db", str(db_path)])
    run_experiment_command(args)
    return args


# --- argparse ------------------------------------------------------------------


def test_experiment_requires_a_subcommand():
    with pytest.raises(SystemExit):
        parse_args(["experiment"])


def test_experiment_start_requires_name_and_config_type():
    with pytest.raises(SystemExit):
        parse_args(["experiment", "start"])


def test_experiment_start_rejects_an_unknown_config_type():
    with pytest.raises(SystemExit):
        parse_args(["experiment", "start", "--name", "x", "--config-type", "nonsense"])


def test_experiment_list_defaults():
    args = parse_args(["experiment", "list"])
    assert args.limit == 50


# --- start / list / end -----------------------------------------------------------


def test_experiment_start_registers_and_prints_the_real_config_version(tmp_path, capsys):
    from decision_engine.config import DecisionConfig

    db_path = tmp_path / "experiments.db"
    _run(["start", "--name", "baseline rule", "--config-type", "decision_engine", "--description", "testing defaults"], db_path)

    output = capsys.readouterr().out
    assert "EXPERIMENT REGISTERED" in output
    assert "baseline rule" in output
    assert DecisionConfig().version_id() in output  # the REAL, unmodified config's own hash -- never fabricated


def test_experiment_start_scanner_config_type(tmp_path, capsys):
    from market_intelligence.config import ScannerConfig

    db_path = tmp_path / "experiments.db"
    _run(["start", "--name", "scanner test", "--config-type", "scanner"], db_path)
    output = capsys.readouterr().out
    assert ScannerConfig().version_id() in output


def test_experiment_start_risk_config_type(tmp_path, capsys):
    from risk.config import RiskConfig

    db_path = tmp_path / "experiments.db"
    _run(["start", "--name", "risk test", "--config-type", "risk"], db_path)
    output = capsys.readouterr().out
    assert RiskConfig().version_id() in output


def test_experiment_list_shows_ongoing_status(tmp_path, capsys):
    db_path = tmp_path / "experiments.db"
    _run(["start", "--name", "exp1", "--config-type", "decision_engine"], db_path)
    capsys.readouterr()

    _run(["list"], db_path)
    output = capsys.readouterr().out
    assert "ONGOING" in output
    assert "exp1" in output


def test_experiment_list_empty_registry(tmp_path, capsys):
    db_path = tmp_path / "experiments.db"
    _run(["list"], db_path)
    output = capsys.readouterr().out
    assert "No experiments registered yet" in output


def test_experiment_end_updates_status_to_ended(tmp_path, capsys):
    db_path = tmp_path / "experiments.db"
    _run(["start", "--name", "exp1", "--config-type", "decision_engine"], db_path)
    start_output = capsys.readouterr().out
    experiment_id = next(line for line in start_output.splitlines() if line.startswith("Experiment ID:")).split()[-1]

    _run(["end", "--experiment-id", experiment_id, "--note", "concluded"], db_path)
    capsys.readouterr()

    _run(["list"], db_path)
    output = capsys.readouterr().out
    assert "ENDED" in output


def test_experiment_end_unknown_id_fails_cleanly(tmp_path, capsys):
    db_path = tmp_path / "experiments.db"
    with pytest.raises(SystemExit):
        _run(["end", "--experiment-id", "does-not-exist"], db_path)
    assert "no experiment found" in capsys.readouterr().err


def test_experiment_end_twice_fails_cleanly(tmp_path, capsys):
    db_path = tmp_path / "experiments.db"
    _run(["start", "--name", "exp1", "--config-type", "decision_engine"], db_path)
    start_output = capsys.readouterr().out
    experiment_id = next(line for line in start_output.splitlines() if line.startswith("Experiment ID:")).split()[-1]

    _run(["end", "--experiment-id", experiment_id], db_path)
    capsys.readouterr()

    with pytest.raises(SystemExit):
        _run(["end", "--experiment-id", experiment_id], db_path)
    assert "already ended" in capsys.readouterr().err


# --- compare -----------------------------------------------------------------


def _candidate() -> CandidateScore:
    return CandidateScore(
        symbol="AAPL", as_of=datetime(2024, 1, 1), last_close=100.0, avg_daily_value=1_000_000.0, volume_ratio=1.1,
        trend_score=1.0, momentum_score=0.5, breakout_score=0.01, relative_strength_score=0.02,
        sector_strength_score=None, composite_score=1.5, explanation=["fake"],
    )


def test_experiment_compare_shows_real_stats_within_the_window(tmp_path, capsys):
    from decision_engine.config import DecisionConfig

    db_path = tmp_path / "experiments.db"
    _run(["start", "--name", "exp1", "--config-type", "decision_engine"], db_path)
    capsys.readouterr()

    config_version = DecisionConfig().version_id()
    decision_db = tmp_path / "decisions.db"
    predictions_db = tmp_path / "predictions.db"

    decision_store = DecisionStore(decision_db)
    decision_store.save_decision(Decision(
        decision_id="dec-1", symbol="AAPL", as_of=datetime(2024, 6, 1, tzinfo=timezone.utc), label=DecisionLabel.BUY,
        rationale=["fake"], config_version=config_version, scanner_evidence=_candidate(), research_evidence=None,
        market_context=None, risk_context=RiskContext.unknown(), narrative=None, narrative_unavailable_reason=None,
    ))
    decision_store.close()

    prediction_store = PredictionStore(predictions_db)
    prediction_store.save_prediction(PredictionRecord(
        prediction_id="pred-1", decision_id="dec-1", symbol="AAPL", created_at=datetime.now(timezone.utc),
        label=DecisionLabel.BUY, entry_price=100.0, stop_price=95.0, target_price=110.0,
        entry_time=datetime(2024, 6, 1), horizon_bars=20, interval="1d",
    ))
    prediction_store.save_evaluation(PredictionEvaluation(
        evaluation_id="eval-1", prediction_id="pred-1", evaluated_at=datetime.now(timezone.utc),
        outcome=PredictionOutcomeState.TARGET_HIT, bars_observed=5, exit_time=None, exit_price=110.0,
        actual_return=0.10, max_favorable_excursion=0.10, max_adverse_excursion=0.0, detail="test",
    ))
    prediction_store.close()

    args = parse_args(["experiment", "compare", "--db", str(db_path), "--predictions-db", str(predictions_db), "--decision-db", str(decision_db)])
    run_experiment_command(args)

    output = capsys.readouterr().out
    assert "Total:          1   Resolved: 1" in output
    assert "Win rate:       +100.00%" in output
    assert "Avg return:     +10.00%" in output


def test_experiment_compare_unevaluated_prediction_shows_zero_total(tmp_path, capsys):
    """An unevaluated prediction (e.g. from a --skip-evaluate shadow-run)
    is correctly excluded -- matches `learn`'s own established
    "requires an evaluation" convention, not a bug."""
    from decision_engine.config import DecisionConfig

    db_path = tmp_path / "experiments.db"
    _run(["start", "--name", "exp1", "--config-type", "decision_engine"], db_path)
    capsys.readouterr()

    predictions_db = tmp_path / "predictions.db"
    prediction_store = PredictionStore(predictions_db)
    prediction_store.save_prediction(PredictionRecord(
        prediction_id="pred-1", decision_id="dec-1", symbol="AAPL", created_at=datetime.now(timezone.utc),
        label=DecisionLabel.BUY, entry_price=100.0, stop_price=95.0, target_price=110.0,
        entry_time=datetime(2024, 6, 1), horizon_bars=20, interval="1d",
    ))
    prediction_store.close()

    args = parse_args(["experiment", "compare", "--db", str(db_path), "--predictions-db", str(predictions_db)])
    run_experiment_command(args)

    output = capsys.readouterr().out
    assert "Total:          0   Resolved: 0" in output


def test_experiment_compare_empty_registry(tmp_path, capsys):
    db_path = tmp_path / "experiments.db"
    args = parse_args(["experiment", "compare", "--db", str(db_path)])
    run_experiment_command(args)
    assert "No experiments registered yet" in capsys.readouterr().out
