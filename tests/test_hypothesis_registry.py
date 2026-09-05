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


def test_exit_hypotheses_are_all_open_pending_actual_implementation():
    registry = build_hypothesis_registry()
    exit_hypotheses = [h for h in registry if h.hypothesis_id.startswith("H_EXIT_")]

    assert len(exit_hypotheses) == 4
    assert all(h.status == HypothesisStatus.OPEN for h in exit_hypotheses)


def test_build_hypothesis_registry_returns_a_fresh_tuple_each_call():
    a = build_hypothesis_registry()
    b = build_hypothesis_registry()

    assert a == b
    assert a is not b
