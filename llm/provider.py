import os
from functools import lru_cache

from langchain_core.embeddings import Embeddings
from langchain_core.language_models.chat_models import BaseChatModel

from core.config import AgentRole, LLMProvider, get_settings
from llm.errors import (
    ModelNotAvailableError,
    OllamaUnavailableError,
    OpenAIDisabledError,
    OpenAINotConfiguredError,
    OpenAIUnavailableError,
)


def get_chat_model(
    *,
    role: AgentRole | None = None,
    temperature: float | None = None,
) -> BaseChatModel:
    settings = get_settings()

    resolved_temperature = temperature
    if resolved_temperature is None and role is not None:
        resolved_temperature = settings.get_role_temperature(role)
    if resolved_temperature is None:
        resolved_temperature = settings.chat_temperature_default

    if settings.llm_provider == LLMProvider.OLLAMA:
        return _create_ollama_chat_model(
            model=settings.chat_model,
            base_url=settings.ollama_base_url,
            temperature=resolved_temperature,
        )

    if settings.llm_provider == LLMProvider.NIM:
        raise NotImplementedError(
            "NIM chat models are not implemented yet. Use llm_provider=ollama in config."
        )

    if settings.llm_provider == LLMProvider.OPENAI:
        return _create_openai_chat_model(
            model=settings.openai_model,
            temperature=resolved_temperature,
        )

    raise ValueError(f"Unsupported LLM provider: {settings.llm_provider}")


@lru_cache
def get_embeddings() -> Embeddings:
    settings = get_settings()

    if settings.llm_provider == LLMProvider.OLLAMA:
        return _create_ollama_embeddings(
            model=settings.embedding_model,
            base_url=settings.ollama_base_url,
        )

    if settings.llm_provider == LLMProvider.NIM:
        raise NotImplementedError(
            "NIM embeddings are not implemented yet. Use llm_provider=ollama in config."
        )

    if settings.llm_provider == LLMProvider.OPENAI:
        raise NotImplementedError(
            "OpenAI embeddings are not implemented yet. Use llm_provider=ollama in config."
        )

    raise ValueError(f"Unsupported LLM provider: {settings.llm_provider}")


def _create_ollama_chat_model(
    *,
    model: str,
    base_url: str,
    temperature: float,
) -> BaseChatModel:
    from langchain_ollama import ChatOllama

    settings = get_settings()
    return ChatOllama(
        model=model,
        base_url=base_url,
        temperature=temperature,
        client_kwargs={"timeout": settings.ollama_timeout_seconds},
    )


def _create_openai_chat_model(
    *,
    model: str,
    temperature: float,
) -> BaseChatModel:
    """Build a langchain_openai.ChatOpenAI instance.

    Reads OPENAI_API_KEY directly from the process environment at call
    time, never from Settings (see core/config.py's comment on the
    openai_* fields) and never logs it. Raises OpenAINotConfiguredError
    (not a bare KeyError/langchain validation error) so callers -- and
    `ai-health` -- get one clear, consistent message.
    """
    from langchain_openai import ChatOpenAI

    settings = get_settings()

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise OpenAINotConfiguredError()
    if not settings.openai_enabled:
        raise OpenAIDisabledError()

    return ChatOpenAI(
        model=model,
        api_key=api_key,
        temperature=temperature,
        timeout=settings.openai_timeout_seconds,
        max_retries=settings.openai_max_retries,
        max_completion_tokens=settings.openai_max_output_tokens,
    )


def _create_ollama_embeddings(
    *,
    model: str,
    base_url: str,
) -> Embeddings:
    from langchain_ollama import OllamaEmbeddings

    settings = get_settings()
    return OllamaEmbeddings(
        model=model,
        base_url=base_url,
        client_kwargs={"timeout": settings.ollama_timeout_seconds},
    )


def check_ollama_availability(
    *,
    base_url: str | None = None,
    required_models: tuple[str, ...] | None = None,
) -> None:
    """Fail fast with a clear error if Ollama or the configured models are missing.

    Intended to run once at startup, before the graph is invoked, so a
    misconfigured or stopped daemon produces a one-line explanation instead
    of an opaque stack trace from deep inside a LangGraph node.

    `base_url`/`required_models` default to the current settings; they are
    parameterized so tests can exercise the failure paths without needing a
    running Ollama daemon.
    """
    settings = get_settings()
    if settings.llm_provider != LLMProvider.OLLAMA:
        return

    resolved_base_url = base_url or settings.ollama_base_url
    resolved_required = required_models or (settings.chat_model, settings.embedding_model)

    import ollama

    client = ollama.Client(host=resolved_base_url)
    try:
        response = client.list()
    except Exception as exc:
        raise OllamaUnavailableError(resolved_base_url, cause=exc) from exc

    available = [model.model for model in response.models]

    for required in resolved_required:
        if not _model_available(required, available):
            raise ModelNotAvailableError(required, available)


def check_openai_availability() -> None:
    """Fail fast with a clear error if OpenAI is not configured/reachable.

    A real network call (models.list()) -- this is the connectivity/auth
    check, not a completion, so it costs no completion tokens. Intended to
    run once before a narration/explanation/health-check request, same
    role as check_ollama_availability for the Ollama path.
    """
    settings = get_settings()
    if settings.llm_provider != LLMProvider.OPENAI:
        return

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise OpenAINotConfiguredError()
    if not settings.openai_enabled:
        raise OpenAIDisabledError()

    from openai import OpenAI

    client = OpenAI(api_key=api_key, timeout=settings.openai_timeout_seconds, max_retries=settings.openai_max_retries)
    try:
        client.models.retrieve(settings.openai_model)
    except Exception as exc:
        raise OpenAIUnavailableError(cause=exc) from exc


def check_llm_availability() -> None:
    """Provider-agnostic dispatcher: checks whichever provider is currently
    configured (settings.llm_provider). Callers that used to call
    check_ollama_availability() directly should call this instead so they
    correctly follow AI_PROVIDER instead of always assuming Ollama."""
    settings = get_settings()
    if settings.llm_provider == LLMProvider.OLLAMA:
        check_ollama_availability()
    elif settings.llm_provider == LLMProvider.OPENAI:
        check_openai_availability()
    else:
        raise ValueError(f"Unsupported LLM provider: {settings.llm_provider}")


def _model_available(required: str, available: list[str]) -> bool:
    # Ollama tags default to ":latest" — accept either form ("foo" or "foo:latest").
    if required in available:
        return True
    if ":" not in required:
        return f"{required}:latest" in available
    return False
