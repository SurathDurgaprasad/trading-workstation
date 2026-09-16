import os
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

PROJECT_ROOT = Path(__file__).resolve().parent.parent

AgentRole = Literal[
    "technical", "risk", "critic", "debate", "supervisor",
    "signal_explainer", "research_summarizer", "decision_narrator", "decision_reviewer",
]


class LLMProvider(str, Enum):
    OLLAMA = "ollama"
    NIM = "nim"
    OPENAI = "openai"


class Settings(BaseModel):
    llm_provider: LLMProvider = LLMProvider.OLLAMA

    # NOTE: "llama3.1:8b" (the original default) is not pulled in this
    # environment. "qwen2.5-coder:7b" is used instead — it is already
    # installed locally and is this project's own #1 preferred model per
    # .cursor/skills/local-llm-standards/SKILL.md. See the Phase 1/2
    # implementation report for details.
    chat_model: str = "qwen2.5-coder:7b"
    embedding_model: str = "nomic-embed-text"
    ollama_base_url: str = "http://localhost:11434"
    # 3 of the 5 graph nodes (technical/risk/critic) call Ollama concurrently
    # and share one local daemon/GPU, so per-call latency is not just
    # single-inference time under load — 60s proved too tight in practice.
    ollama_timeout_seconds: float = 180.0

    # OpenAI provider settings. Deliberately does NOT include the API key --
    # llm/provider.py reads OPENAI_API_KEY from the process environment at
    # the moment a real OpenAI call is about to be made, never at import
    # time or into this cached Settings singleton, matching the existing
    # live/dhan/config.py convention for the same reason (never store a
    # secret in a long-lived object that could be logged/dumped/repr'd).
    openai_model: str = "gpt-4o-mini"
    openai_timeout_seconds: float = 30.0
    openai_max_retries: int = 2
    openai_max_output_tokens: int = 1024
    openai_enabled: bool = False

    chat_temperature_default: float = 0.2
    technical_temperature: float = 0.2
    risk_temperature: float = 0.2
    critic_temperature: float = 0.2
    debate_temperature: float = 0.3
    supervisor_temperature: float = 0.1
    signal_explainer_temperature: float = 0.2
    research_summarizer_temperature: float = 0.2
    decision_narrator_temperature: float = 0.2
    decision_reviewer_temperature: float = 0.2

    vectorstore_dir: Path = Field(default=PROJECT_ROOT / "vectorstore")
    documents_dir: Path = Field(default=PROJECT_ROOT / "documents")
    retrieval_top_k: int = 5

    log_level: str = "INFO"

    @property
    def strategy_document(self) -> Path:
        return self.documents_dir / "strategy.pdf"

    def get_role_temperature(self, role: AgentRole) -> float:
        return {
            "technical": self.technical_temperature,
            "risk": self.risk_temperature,
            "critic": self.critic_temperature,
            "debate": self.debate_temperature,
            "supervisor": self.supervisor_temperature,
            "signal_explainer": self.signal_explainer_temperature,
            "research_summarizer": self.research_summarizer_temperature,
            "decision_narrator": self.decision_narrator_temperature,
            "decision_reviewer": self.decision_reviewer_temperature,
        }[role]


def _env_overrides() -> dict:
    """Read the small, explicit set of env vars this project supports for
    provider selection and OpenAI tuning (never the API key itself -- see
    the comment on the openai_* fields above). Everything else in Settings
    stays a hardcoded default, matching the existing project convention;
    this is deliberately NOT a blanket pydantic-settings env-to-field
    mapping, since most Settings fields (role temperatures, retrieval_top_k,
    etc.) were never meant to be environment-configurable and a blanket
    mapping would silently change that for all of them at once.
    """
    overrides: dict = {}

    provider_env = os.environ.get("AI_PROVIDER")
    if provider_env:
        overrides["llm_provider"] = LLMProvider(provider_env.strip().lower())

    if os.environ.get("OPENAI_MODEL"):
        overrides["openai_model"] = os.environ["OPENAI_MODEL"]

    if os.environ.get("OPENAI_TIMEOUT"):
        overrides["openai_timeout_seconds"] = float(os.environ["OPENAI_TIMEOUT"])

    if os.environ.get("OPENAI_MAX_RETRIES"):
        overrides["openai_max_retries"] = int(os.environ["OPENAI_MAX_RETRIES"])

    if os.environ.get("OPENAI_MAX_OUTPUT_TOKENS"):
        overrides["openai_max_output_tokens"] = int(os.environ["OPENAI_MAX_OUTPUT_TOKENS"])

    if os.environ.get("OPENAI_ENABLED"):
        overrides["openai_enabled"] = os.environ["OPENAI_ENABLED"].strip().lower() in ("1", "true", "yes", "on")

    return overrides


@lru_cache
def get_settings() -> Settings:
    return Settings(**_env_overrides())
