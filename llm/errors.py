class OllamaUnavailableError(RuntimeError):
    """The configured Ollama daemon could not be reached."""

    def __init__(self, base_url: str, cause: Exception | None = None):
        self.base_url = base_url
        self.cause = cause
        super().__init__(
            f"Ollama is not reachable at {base_url}. "
            f"Start it (e.g. `ollama serve`, or launch the Ollama app) and retry."
        )


class ModelNotAvailableError(RuntimeError):
    """A configured model is not pulled on the local Ollama daemon."""

    def __init__(self, model: str, available_models: list[str]):
        self.model = model
        self.available_models = available_models
        available = ", ".join(available_models) or "(none)"
        super().__init__(
            f"Model '{model}' is not available on the local Ollama daemon. "
            f"Available models: {available}. "
            f"Pull it with `ollama pull {model}`, or change core/config.py."
        )


class OpenAINotConfiguredError(RuntimeError):
    """OPENAI_API_KEY is not set in the process environment.

    Deliberately never includes the key value (there is none to include --
    this fires precisely because it's absent) and callers must not log the
    environment beyond this message.
    """

    def __init__(self):
        super().__init__(
            "OPENAI_API_KEY is not set in the process environment. "
            "Set it (e.g. in .env, never committed) and retry."
        )


class OpenAIDisabledError(RuntimeError):
    """OPENAI_ENABLED is not true, so no OpenAI call was attempted."""

    def __init__(self):
        super().__init__(
            "OPENAI_ENABLED is not set to a true value, so the OpenAI provider is "
            "administratively disabled. Set OPENAI_ENABLED=true to allow real calls."
        )


class OpenAIUnavailableError(RuntimeError):
    """A real call to the OpenAI API failed (network, auth, quota, etc.).

    Adversarial hardening pass (2026-09-18): an audit found this message
    previously embedded `str(cause)` verbatim -- the underlying SDK/
    transport exception's own text, which reaches a real console print
    path (`main.py`'s `ai-health` command). `llm/budget.py`'s own ledger
    deliberately records only `error_class`, never `str(exc)`, exactly
    because "a raised HTTP error can otherwise leak an Authorization
    header value into str(exc)" -- this class previously did not follow
    its own project's stated precaution. Defense-in-depth, same posture
    as live/dhan/market_data_source.py's `_redact_secret` (no evidence of
    an actual leak in the pinned SDK version -- still a hard invariant
    enforced at the code level, not assumed of third-party exception
    text): the configured OPENAI_API_KEY value, if it appears anywhere in
    `str(cause)`, is masked before ever reaching this exception's own
    message."""

    def __init__(self, cause: Exception | None = None):
        import os

        self.cause = cause
        detail = str(cause) if cause is not None else None
        if detail:
            api_key = os.environ.get("OPENAI_API_KEY")
            if api_key and api_key in detail:
                detail = detail.replace(api_key, "***")
        super().__init__(f"OpenAI API call failed: {detail}" if detail is not None else "OpenAI API call failed.")


class AIBudgetExceededError(RuntimeError):
    """A configured LLM call budget (rate or count limit) was exceeded.

    This is a deliberate, safe refusal -- not a failure -- so the deterministic
    trading path must treat it exactly like any other 'AI unavailable' case
    and continue without the advisory output.
    """

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(f"AI call budget exceeded: {reason}")
