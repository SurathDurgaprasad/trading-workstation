"""Strategy science, Phase 9 (multiple testing control). This session
has run MANY simultaneous statistical tests against the SAME 41-symbol
dataset (H_ENTRY_001-005, H_EXIT_001-004 -- 9 hypotheses recorded in
strategy/hypothesis_registry.py, each with its own development/
validation/out-of-sample split). Running many tests against one
dataset without correction inflates the chance that AT LEAST ONE result
looks "significant" purely by chance, even with a real, underlying
negative or non-existent edge -- the classic multiple-comparisons /
data-mining risk this phase exists to guard against.

Two generic, reusable pieces:
  1. bonferroni_corrected_z: the standard, conservative multiple-
     testing correction, computed via the STDLIB's own
     statistics.NormalDist -- no new dependency. (scipy is present in
     this environment only as an incidental transitive dependency of
     an unrelated package; it is never imported directly by this
     project's own code, and this module does not start relying on it
     either -- statistics.NormalDist().inv_cdf(0.975) already returns
     the exact 1.9599... this project's own learning.profitability
     module has hardcoded as _CONFIDENCE_Z, confirming the stdlib
     function is the correct, already-implicitly-relied-upon standard.)
  2. apply_multiple_testing_correction: re-evaluates a named family of
     return-list "tests" using learning.profitability.
     compute_profitability_report_from_returns's own `z` parameter
     (reused verbatim, never a second competing implementation) at
     BOTH the standard 95% confidence level and the Bonferroni-
     corrected level for the given family size, flagging any test
     whose verdict differs between the two. A result that survives
     correction is real, simultaneous-testing-robust evidence; one
     that only looked significant BEFORE correction is exactly the
     false-positive risk this phase exists to catch.
"""

from statistics import NormalDist

from pydantic import BaseModel, ConfigDict

from learning.profitability import ProfitabilityReport, ProfitabilityVerdict, compute_profitability_report_from_returns


def bonferroni_corrected_z(family_size: int, *, alpha: float = 0.05) -> float:
    """The z-score for a (1 - alpha/family_size) two-sided confidence
    level -- the standard, conservative Bonferroni correction for
    running `family_size` simultaneous tests at an overall alpha.
    family_size=1 returns the exact same z as the uncorrected default
    (1.9599...), matching learning.profitability's own hardcoded
    _CONFIDENCE_Z."""
    if family_size < 1:
        raise ValueError("family_size must be at least 1.")
    if not (0 < alpha < 1):
        raise ValueError("alpha must be in (0, 1).")
    corrected_alpha = alpha / family_size
    return NormalDist().inv_cdf(1 - corrected_alpha / 2)


class MultipleTestingResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    uncorrected: ProfitabilityReport
    corrected: ProfitabilityReport

    @property
    def verdict_changed(self) -> bool:
        return self.uncorrected.verdict != self.corrected.verdict


class MultipleTestingAudit(BaseModel):
    model_config = ConfigDict(frozen=True)

    family_size: int
    alpha: float
    corrected_z: float
    results: list[MultipleTestingResult]

    @property
    def any_verdict_survives_correction_as_positive(self) -> bool:
        """True if at least one test's CORRECTED verdict is still
        POSITIVE_PERFORMANCE -- real, simultaneous-testing-robust
        evidence of an edge. False means every uncorrected positive
        result (if any) was exactly the false-positive risk this
        module exists to catch, or -- as in this project's own real
        usage -- nothing looked positive even before correction."""
        return any(r.corrected.verdict == ProfitabilityVerdict.POSITIVE_PERFORMANCE for r in self.results)

    @property
    def any_verdict_flipped_by_correction(self) -> bool:
        return any(r.verdict_changed for r in self.results)


def apply_multiple_testing_correction(
    named_returns: dict[str, list[float]], *, alpha: float = 0.05,
) -> MultipleTestingAudit:
    """named_returns: {test_name: per-trade returns for that test}.
    family_size = len(named_returns) -- the number of SIMULTANEOUS
    tests being corrected for. Deliberately the caller's own
    responsibility to define honestly: this module has no way to know
    how many tests were "really" run against a given dataset (that
    depends on what the caller considers one comparison), so it never
    guesses or infers a family size on its own."""
    if not named_returns:
        return MultipleTestingAudit(family_size=0, alpha=alpha, corrected_z=bonferroni_corrected_z(1, alpha=alpha), results=[])

    family_size = len(named_returns)
    corrected_z = bonferroni_corrected_z(family_size, alpha=alpha)

    results = [
        MultipleTestingResult(
            name=name,
            uncorrected=compute_profitability_report_from_returns(returns),
            corrected=compute_profitability_report_from_returns(returns, z=corrected_z),
        )
        for name, returns in named_returns.items()
    ]

    return MultipleTestingAudit(family_size=family_size, alpha=alpha, corrected_z=corrected_z, results=results)
