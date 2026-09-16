import time
from typing import TypeVar

from langchain_core.language_models.chat_models import BaseChatModel
from pydantic import BaseModel

from agents.errors import AgentOutputError
from core.config import AgentRole, LLMProvider, get_settings
from llm import budget
from llm.provider import get_chat_model

SchemaT = TypeVar("SchemaT", bound=BaseModel)

_MAX_ATTEMPTS = 2

_llms: dict[AgentRole, BaseChatModel] = {}


def get_analyst_llm(role: AgentRole) -> BaseChatModel:
    if role not in _llms:
        _llms[role] = get_chat_model(role=role)
    return _llms[role]


def invoke_structured(
    *,
    role: AgentRole,
    label: str,
    prompt: str,
    schema: type[SchemaT],
    trigger: str = "manual",
) -> SchemaT:
    """Call the role's LLM and return a validated instance of `schema`.

    Retries once on a failed/invalid response (e.g. a transient malformed
    generation), then raises AgentOutputError rather than ever returning
    unstructured text or a partially-valid object.

    When the active provider is OpenAI, every attempt passes through
    llm.budget.check_budget first (Phase 4 cost control) and every attempt
    -- success or failure -- is recorded to the audit ledger. Ollama has no
    metered cost, so the budget gate is a no-op for it (Ollama calls are
    still recorded, with model/role/latency, for observability parity).
    """
    print(f"Running {label}...")

    settings = get_settings()
    model_name = settings.openai_model if settings.llm_provider == LLMProvider.OPENAI else settings.chat_model
    llm = get_analyst_llm(role).with_structured_output(schema)

    last_error: Exception | None = None
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        if settings.llm_provider == LLMProvider.OPENAI:
            try:
                budget.check_budget(input_chars=len(prompt))
            except Exception as exc:
                budget.record_call(
                    role=role, model=model_name, trigger=trigger, status="BUDGET_REJECTED",
                    input_chars=len(prompt), error_class=type(exc).__name__,
                )
                raise

        start = time.monotonic()
        try:
            result = llm.invoke(prompt)
        except Exception as exc:  # noqa: BLE001 - deliberately broad: any failure here is reported, not hidden
            budget.record_call(
                role=role,
                model=model_name,
                trigger=trigger,
                status="FAILURE",
                latency_ms=(time.monotonic() - start) * 1000,
                input_chars=len(prompt),
                error_class=type(exc).__name__,
            )
            last_error = exc
            continue

        latency_ms = (time.monotonic() - start) * 1000
        if isinstance(result, schema):
            budget.record_call(
                role=role, model=model_name, trigger=trigger, status="SUCCESS",
                latency_ms=latency_ms, input_chars=len(prompt),
            )
            return result

        budget.record_call(
            role=role, model=model_name, trigger=trigger, status="FAILURE",
            latency_ms=latency_ms, input_chars=len(prompt), error_class="TypeError",
        )
        last_error = TypeError(
            f"expected {schema.__name__}, got {type(result).__name__}"
        )

    assert last_error is not None
    raise AgentOutputError(role=role, label=label, cause=last_error)
