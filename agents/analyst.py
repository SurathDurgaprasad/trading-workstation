from typing import TypeVar

from langchain_core.language_models.chat_models import BaseChatModel
from pydantic import BaseModel

from agents.errors import AgentOutputError
from core.config import AgentRole
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
) -> SchemaT:
    """Call the role's LLM and return a validated instance of `schema`.

    Retries once on a failed/invalid response (e.g. a transient malformed
    generation), then raises AgentOutputError rather than ever returning
    unstructured text or a partially-valid object.
    """
    print(f"Running {label}...")

    llm = get_analyst_llm(role).with_structured_output(schema)

    last_error: Exception | None = None
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            result = llm.invoke(prompt)
        except Exception as exc:  # noqa: BLE001 - deliberately broad: any failure here is reported, not hidden
            last_error = exc
            continue

        if isinstance(result, schema):
            return result

        last_error = TypeError(
            f"expected {schema.__name__}, got {type(result).__name__}"
        )

    assert last_error is not None
    raise AgentOutputError(role=role, label=label, cause=last_error)
