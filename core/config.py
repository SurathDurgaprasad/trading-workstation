from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

PROJECT_ROOT = Path(__file__).resolve().parent.parent

AgentRole = Literal["technical", "risk", "critic", "debate", "supervisor", "signal_explainer"]


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

    chat_temperature_default: float = 0.2
    technical_temperature: float = 0.2
    risk_temperature: float = 0.2
    critic_temperature: float = 0.2
    debate_temperature: float = 0.3
    supervisor_temperature: float = 0.1
    signal_explainer_temperature: float = 0.2

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
        }[role]


@lru_cache
def get_settings() -> Settings:
    return Settings()
