class AgentOutputError(RuntimeError):
    """An agent's LLM call did not produce a valid instance of its declared schema.

    Raised instead of letting a malformed or unparseable response silently
    become part of a trading decision — callers must treat this as a failed
    analysis run, not fall back to regex-parsing free text.
    """

    def __init__(self, *, role: str, label: str, cause: Exception):
        self.role = role
        self.label = label
        self.cause = cause
        super().__init__(
            f"{label} ({role}) failed to produce valid structured output: {cause}"
        )
