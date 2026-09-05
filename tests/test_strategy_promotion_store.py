from strategy.promotion_gate import evaluate_promotion
from strategy.promotion_store import PromotionGateStore

_POSITIVE = [0.05] * 30
_NEGATIVE = [-0.05] * 30


def test_record_and_get_round_trips_the_full_evaluation(tmp_path):
    store = PromotionGateStore(tmp_path / "promotion.db")
    evaluation = evaluate_promotion(
        "candidate", development_returns=_POSITIVE, validation_returns=_POSITIVE, out_of_sample_returns=_POSITIVE,
    )

    evaluation_id = store.record_evaluation(evaluation)
    fetched = store.get(evaluation_id)

    assert fetched is not None
    assert fetched.verdict == evaluation.verdict
    assert fetched.candidate_name == "candidate"
    assert fetched.development.sample_size == 30


def test_get_returns_none_for_an_unknown_evaluation_id(tmp_path):
    store = PromotionGateStore(tmp_path / "promotion.db")
    assert store.get("does-not-exist") is None


def test_history_for_candidate_never_overwrites_a_past_evaluation(tmp_path):
    # Append-only: re-evaluating the SAME candidate twice must produce
    # TWO rows, not one -- a later favorable re-evaluation must never
    # silently erase an earlier negative one (spec: "never hide negative
    # results", "never silently modify").
    store = PromotionGateStore(tmp_path / "promotion.db")
    first = evaluate_promotion(
        "candidate", development_returns=_NEGATIVE, validation_returns=_NEGATIVE, out_of_sample_returns=_NEGATIVE,
    )
    second = evaluate_promotion(
        "candidate", development_returns=_POSITIVE, validation_returns=_POSITIVE, out_of_sample_returns=_POSITIVE,
    )
    store.record_evaluation(first)
    store.record_evaluation(second)

    history = store.history_for_candidate("candidate")

    assert len(history) == 2
    assert history[0].verdict.value == "NEGATIVE"
    assert history[1].verdict.value == "PROMOTED"


def test_latest_for_candidate_returns_the_most_recent_evaluation(tmp_path):
    store = PromotionGateStore(tmp_path / "promotion.db")
    first = evaluate_promotion(
        "candidate", development_returns=_NEGATIVE, validation_returns=_NEGATIVE, out_of_sample_returns=_NEGATIVE,
    )
    second = evaluate_promotion(
        "candidate", development_returns=_POSITIVE, validation_returns=_POSITIVE, out_of_sample_returns=_POSITIVE,
    )
    store.record_evaluation(first)
    store.record_evaluation(second)

    latest = store.latest_for_candidate("candidate")

    assert latest is not None
    assert latest.verdict.value == "PROMOTED"


def test_latest_for_candidate_returns_none_when_never_evaluated(tmp_path):
    store = PromotionGateStore(tmp_path / "promotion.db")
    assert store.latest_for_candidate("never-seen") is None


def test_records_persist_across_separate_store_instances_on_the_same_db_file(tmp_path):
    db_path = tmp_path / "promotion.db"
    store1 = PromotionGateStore(db_path)
    evaluation = evaluate_promotion(
        "candidate", development_returns=_POSITIVE, validation_returns=_POSITIVE, out_of_sample_returns=_POSITIVE,
    )
    evaluation_id = store1.record_evaluation(evaluation)
    store1.close()

    store2 = PromotionGateStore(db_path)
    fetched = store2.get(evaluation_id)

    assert fetched is not None
    assert fetched.candidate_name == "candidate"


def test_different_candidates_do_not_leak_into_each_others_history(tmp_path):
    store = PromotionGateStore(tmp_path / "promotion.db")
    store.record_evaluation(evaluate_promotion(
        "candidate_a", development_returns=_POSITIVE, validation_returns=_POSITIVE, out_of_sample_returns=_POSITIVE,
    ))
    store.record_evaluation(evaluate_promotion(
        "candidate_b", development_returns=_NEGATIVE, validation_returns=_NEGATIVE, out_of_sample_returns=_NEGATIVE,
    ))

    assert len(store.history_for_candidate("candidate_a")) == 1
    assert len(store.history_for_candidate("candidate_b")) == 1
    assert store.history_for_candidate("candidate_a")[0].verdict.value == "PROMOTED"
    assert store.history_for_candidate("candidate_b")[0].verdict.value == "NEGATIVE"
