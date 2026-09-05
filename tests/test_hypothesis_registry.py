from strategy.hypothesis_registry import HypothesisStatus, build_hypothesis_registry


def test_registry_has_unique_hypothesis_ids():
    registry = build_hypothesis_registry()
    ids = [h.hypothesis_id for h in registry]

    assert len(ids) == len(set(ids))


def test_registry_covers_both_entry_and_exit_hypothesis_families():
    registry = build_hypothesis_registry()
    ids = {h.hypothesis_id for h in registry}

    assert {"H_ENTRY_001", "H_ENTRY_002", "H_ENTRY_003", "H_ENTRY_004", "H_ENTRY_005"} <= ids
    assert {"H_EXIT_001", "H_EXIT_002", "H_EXIT_003", "H_EXIT_004"} <= ids


def test_every_hypothesis_has_all_required_fields_non_empty():
    registry = build_hypothesis_registry()

    for h in registry:
        assert h.hypothesis_id.strip()
        assert h.description.strip()
        assert h.rationale.strip()
        assert h.expected_effect.strip()
        assert h.dataset_restrictions.strip()
        assert h.experiment_design.strip()
        assert h.success_criteria.strip()
        assert h.failure_criteria.strip()
        assert h.evidence.strip()


def test_open_hypotheses_honestly_state_they_were_not_tested():
    """The core honesty check this registry exists to enforce: a status
    of OPEN must never be paired with evidence that sounds like a real
    result -- every OPEN entry's evidence must say so plainly."""
    registry = build_hypothesis_registry()

    for h in registry:
        if h.status == HypothesisStatus.OPEN:
            assert "not yet" in h.evidence.lower() or "no experiment" in h.evidence.lower()


def test_h_entry_001_is_supported_with_the_real_monte_carlo_evidence():
    registry = build_hypothesis_registry()
    h = next(h for h in registry if h.hypothesis_id == "H_ENTRY_001")

    assert h.status == HypothesisStatus.SUPPORTED
    assert "96" in h.evidence  # the real 96.0% Monte Carlo figure
    assert "-0.64%" in h.evidence


def test_h_entry_005_is_inconclusive_not_falsely_rejected_or_supported():
    registry = build_hypothesis_registry()
    h = next(h for h in registry if h.hypothesis_id == "H_ENTRY_005")

    assert h.status == HypothesisStatus.INCONCLUSIVE
    assert "283" in h.evidence  # the real dominant-bucket trade count


def test_exit_hypotheses_not_yet_run_remain_open():
    """H_EXIT_001/002/003 have now been implemented and tested (see the
    dedicated tests below); only H_EXIT_004 remains untested."""
    registry = build_hypothesis_registry()
    exit_hypotheses = [h for h in registry if h.hypothesis_id.startswith("H_EXIT_")]

    assert len(exit_hypotheses) == 4
    still_open = [h for h in exit_hypotheses if h.hypothesis_id not in ("H_EXIT_001", "H_EXIT_002", "H_EXIT_003")]
    assert len(still_open) == 1
    assert all(h.status == HypothesisStatus.OPEN for h in still_open)


def test_h_exit_001_is_rejected_with_the_real_dev_val_oos_evidence():
    """The breakeven-at-+1R experiment was actually run against the real
    41-symbol universe (backtesting/exit_experiments.py) with the same
    development/validation/out-of-sample splits as the standard engine.
    Development and out-of-sample both degraded (win rate collapsed,
    profit factor dropped); only validation showed a marginal expectancy
    improvement. Per the hypothesis's own promotion rule (ALL three
    splits must show non-degraded expectancy), this is REJECTED, not
    SUPPORTED and not swept under INCONCLUSIVE."""
    registry = build_hypothesis_registry()
    h = next(h for h in registry if h.hypothesis_id == "H_EXIT_001")

    assert h.status == HypothesisStatus.REJECTED
    assert "REJECTED" in h.evidence
    # Spot-check the real, actually-measured figures are present verbatim.
    assert "30.56%" in h.evidence
    assert "17.88%" in h.evidence
    assert "24.39%" in h.evidence


def test_h_exit_002_is_inconclusive_with_the_real_dev_val_oos_evidence():
    """The partial-profit-at-+1R experiment was run against the same real
    41-symbol universe with the same three splits. Every split flipped
    from negative to positive point-estimate expectancy and profit
    factor climbed above 1.0 -- a real, consistent, non-degraded
    directional improvement -- but every confidence interval still
    touches zero, so this falls short of a confident positive verdict.
    INCONCLUSIVE is the honest label: not REJECTED (nothing degraded)
    and not SUPPORTED (no split reached statistical significance)."""
    registry = build_hypothesis_registry()
    h = next(h for h in registry if h.hypothesis_id == "H_EXIT_002")

    assert h.status == HypothesisStatus.INCONCLUSIVE
    assert "INCONCLUSIVE" in h.evidence
    assert "1.078" in h.evidence
    assert "1.131" in h.evidence
    assert "1.330" in h.evidence


def test_h_exit_003_is_rejected_with_the_real_dev_val_oos_evidence():
    """The ATR-trailing-stop experiment was run against the same real
    41-symbol universe with the same three splits. Results were mixed
    rather than consistently improved, and validation clearly degraded
    (its verdict worsened from STATISTICALLY_MEANINGLESS to
    NEGATIVE_PERFORMANCE, profit factor dropped from 0.700 to 0.530) --
    failing the promotion rule's requirement that ALL three splits show
    non-degraded expectancy."""
    registry = build_hypothesis_registry()
    h = next(h for h in registry if h.hypothesis_id == "H_EXIT_003")

    assert h.status == HypothesisStatus.REJECTED
    assert "REJECTED" in h.evidence
    assert "0.530" in h.evidence
    assert "WORSENS" in h.evidence


def test_build_hypothesis_registry_returns_a_fresh_tuple_each_call():
    a = build_hypothesis_registry()
    b = build_hypothesis_registry()

    assert a == b
    assert a is not b
