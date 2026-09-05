import random

import pytest

from learning.profitability import ProfitabilityVerdict
from strategy.multiple_testing import apply_multiple_testing_correction, bonferroni_corrected_z

# --- bonferroni_corrected_z --------------------------------------------------


def test_family_size_one_matches_the_uncorrected_default_z():
    assert bonferroni_corrected_z(1) == pytest.approx(1.9599639845400536)


def test_family_size_nine_matches_the_known_bonferroni_value():
    # This session's own real family size (H_ENTRY_001-005 + H_EXIT_001-004
    # recorded in strategy/hypothesis_registry.py).
    assert bonferroni_corrected_z(9) == pytest.approx(2.7729212946086624)


def test_larger_family_size_produces_a_larger_corrected_z():
    z_small = bonferroni_corrected_z(2)
    z_large = bonferroni_corrected_z(20)
    assert z_large > z_small > bonferroni_corrected_z(1)


def test_rejects_family_size_below_one():
    with pytest.raises(ValueError):
        bonferroni_corrected_z(0)


def test_rejects_invalid_alpha():
    with pytest.raises(ValueError):
        bonferroni_corrected_z(5, alpha=1.5)
    with pytest.raises(ValueError):
        bonferroni_corrected_z(5, alpha=0.0)


# --- apply_multiple_testing_correction ---------------------------------------


def _borderline_positive_returns() -> list[float]:
    rng = random.Random(7)
    return [0.008 + rng.gauss(0, 0.03) for _ in range(40)]


def _clearly_negative_returns() -> list[float]:
    return [-0.05] * 40


def test_a_borderline_positive_result_flips_to_meaningless_in_a_family_of_nine():
    named_returns = {f"test_{i}": (_borderline_positive_returns() if i == 0 else _clearly_negative_returns()) for i in range(9)}
    audit = apply_multiple_testing_correction(named_returns)

    assert audit.family_size == 9
    borderline_result = next(r for r in audit.results if r.name == "test_0")
    assert borderline_result.uncorrected.verdict == ProfitabilityVerdict.POSITIVE_PERFORMANCE
    assert borderline_result.corrected.verdict == ProfitabilityVerdict.STATISTICALLY_MEANINGLESS
    assert borderline_result.verdict_changed is True


def test_clearly_negative_results_are_unaffected_by_correction():
    named_returns = {"test_a": _clearly_negative_returns(), "test_b": _clearly_negative_returns()}
    audit = apply_multiple_testing_correction(named_returns)

    for result in audit.results:
        assert result.uncorrected.verdict == ProfitabilityVerdict.NEGATIVE_PERFORMANCE
        assert result.corrected.verdict == ProfitabilityVerdict.NEGATIVE_PERFORMANCE
        assert result.verdict_changed is False


def test_any_verdict_survives_correction_as_positive_is_false_when_nothing_is_positive():
    named_returns = {"test_a": _clearly_negative_returns(), "test_b": _clearly_negative_returns()}
    audit = apply_multiple_testing_correction(named_returns)
    assert audit.any_verdict_survives_correction_as_positive is False


def test_any_verdict_flipped_by_correction_reflects_the_borderline_case():
    named_returns = {f"test_{i}": (_borderline_positive_returns() if i == 0 else _clearly_negative_returns()) for i in range(9)}
    audit = apply_multiple_testing_correction(named_returns)
    assert audit.any_verdict_flipped_by_correction is True


def test_empty_named_returns_produces_an_empty_audit():
    audit = apply_multiple_testing_correction({})
    assert audit.family_size == 0
    assert audit.results == []
    assert audit.any_verdict_survives_correction_as_positive is False
    assert audit.any_verdict_flipped_by_correction is False
