from datetime import datetime, timezone

from learning.models import CalibrationBucket, LearningReport, RegimePerformance, SignalQualityReport, StrategyPerformance
from learning.regime import MarketRegime


def test_strategy_performance_allows_all_none_metrics_when_nothing_resolved():
    performance = StrategyPerformance(config_version="cfg1", total=1, resolved=0, win_rate=None, average_return=None, profit_factor=None)
    assert performance.win_rate is None


def test_regime_performance_carries_a_real_market_regime_value():
    performance = RegimePerformance(regime=MarketRegime.UPTREND, total=1, resolved=1, win_rate=1.0, average_return=0.1)
    assert performance.regime == MarketRegime.UPTREND


def test_calibration_bucket_label_is_freeform_text():
    bucket = CalibrationBucket(bucket_label="Above median composite (1.50)", total=2, resolved=2, win_rate=0.5, average_return=0.01)
    assert "1.50" in bucket.bucket_label


def test_signal_quality_report_allows_zero_resolved():
    report = SignalQualityReport(resolved=0, average_favorable_excursion=None, average_adverse_excursion=None)
    assert report.resolved == 0


def test_learning_report_bundles_everything_with_notes():
    report = LearningReport(
        generated_at=datetime.now(timezone.utc), total_predictions_considered=0,
        strategy_comparison=[], regime_performance=[], confidence_calibration=[],
        signal_quality=SignalQualityReport(resolved=0, average_favorable_excursion=None, average_adverse_excursion=None),
        notes=["Experiment Tracking is not implemented this phase."],
    )
    assert report.notes
