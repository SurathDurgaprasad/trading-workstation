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
