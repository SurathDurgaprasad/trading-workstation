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
    """A real call to the OpenAI API failed (network, auth, quota, etc.)."""

    def __init__(self, cause: Exception | None = None):
        self.cause = cause
        super().__init__(f"OpenAI API call failed: {cause}" if cause is not None else "OpenAI API call failed.")


class AIBudgetExceededError(RuntimeError):
    """A configured LLM call budget (rate or count limit) was exceeded.

    This is a deliberate, safe refusal -- not a failure -- so the deterministic
    trading path must treat it exactly like any other 'AI unavailable' case
    and continue without the advisory output.
    """

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(f"AI call budget exceeded: {reason}")
