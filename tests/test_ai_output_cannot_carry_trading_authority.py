"""OpenAI Intelligence Integration mission, Phase 12/13: adversarial proof
that no AI-facing output schema can carry trading authority, and that the
budget/ledger layer degrades safely under failure and concurrency.

Structural (type-level) guarantees are proven here by inspecting the
Pydantic field sets directly -- not by trusting a docstring's claim or a
prompt instruction the model could ignore. A field name check is a weaker
proof than "the type has no such field" only in the sense that a future
developer could still ADD a dangerous field; this test turns that into an
explicit, loud failure the moment it happens, rather than a silent gap.
"""

import threading

import pytest
from pydantic import BaseModel

from agents.errors import AgentOutputError
from decision_engine.models import DecisionNarrative, DecisionReview
from research.models import ResearchSummary
from schemas.explanation import SignalExplanation

# Any field whose name suggests it could carry executable trading
# authority -- order placement, sizing, price levels, or safety-control
# state. Checked against every LLM-output schema's field names.
_FORBIDDEN_FIELD_SUBSTRINGS = (
    "quantity", "qty", "price", "stop", "target", "entry", "exit",
    "approve", "approved", "execute", "order", "side", "size", "action",
    "buy", "sell", "kill_switch", "override", "risk_amount", "position",
)

_LLM_OUTPUT_SCHEMAS = [SignalExplanation, DecisionNarrative, DecisionReview, ResearchSummary]


@pytest.mark.parametrize("schema", _LLM_OUTPUT_SCHEMAS, ids=lambda s: s.__name__)
def test_llm_output_schema_has_no_field_resembling_trading_authority(schema: type[BaseModel]):
    field_names = set(schema.model_fields.keys())
    violations = {
        field for field in field_names
        if any(forbidden in field.lower() for forbidden in _FORBIDDEN_FIELD_SUBSTRINGS)
    }
    assert not violations, (
        f"{schema.__name__} has a field that could be read as trading authority: {violations}. "
        f"All fields: {field_names}"
    )


@pytest.mark.parametrize("schema", _LLM_OUTPUT_SCHEMAS, ids=lambda s: s.__name__)
def test_llm_output_schema_rejects_an_injected_trading_authority_field(schema: type[BaseModel]):
    # A "hallucinated"/adversarial model response that tries to smuggle in
    # extra fields (e.g. {"approved": true, "quantity": 999, ...} alongside
    # the legitimate ones) must not silently succeed with those extra keys
    # attached -- pydantic's default (non-"extra=allow") behavior ignores
    # unknown keys during validation, so build a minimal valid payload for
    # the real fields, inject a poison key, and assert the constructed
    # instance has no such attribute regardless.
    valid_kwargs = {}
    for name, field in schema.model_fields.items():
        if field.annotation is str:
            valid_kwargs[name] = "x"
        elif field.annotation is float:
            valid_kwargs[name] = 0.5
        elif field.annotation == list[str]:
            valid_kwargs[name] = []
        else:
            pytest.skip(f"{schema.__name__}.{name} has an unhandled annotation for this synthetic payload")

    poisoned = {**valid_kwargs, "approved": True, "quantity": 999, "execute_trade": True}
    instance = schema(**poisoned)

    assert not hasattr(instance, "approved")
    assert not hasattr(instance, "quantity")
    assert not hasattr(instance, "execute_trade")


def test_invoke_structured_never_returns_a_non_schema_object_even_after_a_malformed_response(monkeypatch):
    # A model that returns garbage (wrong type, not just a wrong VALUE)
    # for both retry attempts must surface as AgentOutputError, never as
    # a bare dict/string/None reaching a caller that might misinterpret
    # it as approval.
    import agents.analyst as analyst_module

    class _GarbageRunnable:
        def invoke(self, prompt):
            return {"not": "a schema instance"}

    class _FakeLLM:
        def with_structured_output(self, schema):
            return _GarbageRunnable()

    monkeypatch.setattr(analyst_module, "get_analyst_llm", lambda role: _FakeLLM())

    with pytest.raises(AgentOutputError):
        analyst_module.invoke_structured(
            role="signal_explainer", label="Signal Explainer", prompt="irrelevant", schema=SignalExplanation,
        )


def test_invoke_structured_degrades_safely_on_a_simulated_429_quota_error(monkeypatch):
    # Simulates the OpenAI SDK's real exception shape for a rate-limit/
    # quota failure without a real network call -- invoke_structured must
    # treat it exactly like any other failure (retry once, then a typed
    # AgentOutputError), never propagate a raw SDK exception that a caller
    # might not already be catching.
    import agents.analyst as analyst_module

    class _QuotaError(Exception):
        pass

    class _FailingRunnable:
        def invoke(self, prompt):
            raise _QuotaError("429 Too Many Requests: insufficient_quota")

    class _FakeLLM:
        def with_structured_output(self, schema):
            return _FailingRunnable()

    monkeypatch.setattr(analyst_module, "get_analyst_llm", lambda role: _FakeLLM())

    with pytest.raises(AgentOutputError) as excinfo:
        analyst_module.invoke_structured(
            role="signal_explainer", label="Signal Explainer", prompt="irrelevant", schema=SignalExplanation,
        )
    assert isinstance(excinfo.value.cause, _QuotaError)


def test_concurrent_ai_requests_never_exceed_the_session_budget(tmp_path, monkeypatch):
    # Real-thread concurrency test (same pattern as
    # tests/test_core_health.py's disk-probe race regression) -- N threads
    # all calling check_budget simultaneously must never let more than
    # max_calls_per_session actually pass the gate, proving the lock
    # around _session_call_count is not just cosmetic.
    import llm.budget as budget_module

    budget_module._reset_session_count_for_tests()
    limits = budget_module.BudgetLimits(max_calls_per_session=5, max_calls_per_hour=1000, min_interval_seconds=0.0)
    db_path = tmp_path / "concurrent_ledger.db"

    allowed = []
    rejected = []
    lock = threading.Lock()

    def worker():
        try:
            budget_module.check_budget(input_chars=10, db_path=db_path, limits=limits)
            with lock:
                allowed.append(1)
        except budget_module.AIBudgetExceededError:
            with lock:
                rejected.append(1)

    threads = [threading.Thread(target=worker) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(allowed) == 5, f"expected exactly 5 calls to pass the session budget gate, got {len(allowed)}"
    assert len(rejected) == 15

    budget_module._reset_session_count_for_tests()
