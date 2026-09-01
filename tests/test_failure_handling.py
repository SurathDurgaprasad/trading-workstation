from pathlib import Path

import pytest

from agents.errors import AgentOutputError
from llm.errors import ModelNotAvailableError, OllamaUnavailableError
from llm.provider import check_ollama_availability
from rag.errors import RagStoreNotFoundError


def test_ollama_unavailable_raises_clear_error_not_a_stack_trace():
    # Port 1 is (practically) guaranteed to refuse the connection immediately.
    with pytest.raises(OllamaUnavailableError) as excinfo:
        check_ollama_availability(base_url="http://localhost:1", required_models=("x",))

    assert "localhost:1" in str(excinfo.value)


def test_missing_model_raises_model_not_available_error(monkeypatch):
    class _FakeModel:
        def __init__(self, name):
            self.model = name

    class _FakeListResponse:
        models = [_FakeModel("qwen2.5-coder:7b"), _FakeModel("nomic-embed-text:latest")]

    class _FakeClient:
        def __init__(self, host):
            pass

        def list(self):
            return _FakeListResponse()

    import ollama

    monkeypatch.setattr(ollama, "Client", _FakeClient)

    with pytest.raises(ModelNotAvailableError) as excinfo:
        check_ollama_availability(
            base_url="http://localhost:11434",
            required_models=("llama3.1:8b",),
        )

    assert "llama3.1:8b" in str(excinfo.value)
    assert "qwen2.5-coder:7b" in str(excinfo.value)  # tells the user what IS available


def test_model_available_accepts_bare_name_for_latest_tag(monkeypatch):
    class _FakeModel:
        def __init__(self, name):
            self.model = name

    class _FakeListResponse:
        models = [_FakeModel("nomic-embed-text:latest")]

    class _FakeClient:
        def __init__(self, host):
            pass

        def list(self):
            return _FakeListResponse()

    import ollama

    monkeypatch.setattr(ollama, "Client", _FakeClient)

    # "nomic-embed-text" (no tag) must match "nomic-embed-text:latest" on the server.
    check_ollama_availability(
        base_url="http://localhost:11434",
        required_models=("nomic-embed-text",),
    )


def test_malformed_structured_output_raises_agent_output_error_not_silent_fallback(monkeypatch):
    from agents import analyst
    from schemas.technical import TechnicalAnalysis
    from tests.conftest import FakeChatModel

    fake_llm = FakeChatModel({TechnicalAnalysis: ValueError("model returned unparseable JSON")})
    monkeypatch.setattr(analyst, "get_analyst_llm", lambda role: fake_llm)

    with pytest.raises(AgentOutputError):
        analyst.invoke_structured(
            role="technical",
            label="Technical Agent",
            prompt="irrelevant",
            schema=TechnicalAnalysis,
        )


def test_invoke_structured_retries_once_then_raises(monkeypatch):
    from agents import analyst
    from schemas.technical import TechnicalAnalysis
    from tests.conftest import FakeChatModel

    calls = {"n": 0}

    class _AlwaysFailingRunnable:
        def invoke(self, prompt):
            calls["n"] += 1
            raise ValueError("bad output")

    class _AlwaysFailingModel:
        def with_structured_output(self, schema):
            return _AlwaysFailingRunnable()

    monkeypatch.setattr(analyst, "get_analyst_llm", lambda role: _AlwaysFailingModel())

    with pytest.raises(AgentOutputError):
        analyst.invoke_structured(
            role="technical", label="Technical Agent", prompt="x", schema=TechnicalAnalysis
        )

    assert calls["n"] == analyst._MAX_ATTEMPTS  # retried, did not fail on the first try alone


def test_rag_store_not_found_gives_actionable_error(tmp_path, monkeypatch):
    from core.config import get_settings
    from rag.retriever import get_context

    settings = get_settings()
    monkeypatch.setattr(settings, "vectorstore_dir", tmp_path / "does-not-exist")

    with pytest.raises(RagStoreNotFoundError) as excinfo:
        get_context("any question")

    assert "build_vector_db.py" in str(excinfo.value)


def test_market_context_agent_fails_safely_without_a_symbol():
    from agents.market_context_agent import market_context_agent

    with pytest.raises(ValueError, match="symbol"):
        market_context_agent({"symbol": "", "question": "x", "context": ""})
