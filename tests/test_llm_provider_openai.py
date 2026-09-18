"""OpenAI Intelligence Integration mission: llm/provider.py's OpenAI-specific
code paths. Never makes a real network call -- ChatOpenAI's constructor
does not connect, and check_openai_availability is exercised only through
its failure branches (missing key / disabled), which fail before any
request is attempted. The one real network smoke test lives in
`python main.py ai-health --smoke-test`, run manually/deliberately (Phase 8),
not in the automated suite.
"""

import logging

import pytest

import core.config as config_module
import llm.provider as llm_provider
from core.config import LLMProvider, Settings
from llm.errors import OpenAIDisabledError, OpenAINotConfiguredError


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    # Capture the real, cache_clear()-bearing function object up front --
    # several tests in this file monkeypatch config_module.get_settings to
    # a plain lambda for the duration of the test. monkeypatch restores
    # the original attribute on its OWN teardown, but fixture teardown
    # order is not guaranteed to run this fixture's cleanup after that
    # restore (it depends on when `monkeypatch` itself was first set up
    # relative to this fixture -- conftest.py's autouse
    # _isolate_ai_call_ledger fixture also depends on `monkeypatch`,
    # which can make it set up before this one and therefore tear down
    # after it). Holding our own reference sidesteps the ordering
    # question entirely.
    real_get_settings = config_module.get_settings
    real_get_settings.cache_clear()
    yield
    real_get_settings.cache_clear()


def _openai_settings(**overrides) -> Settings:
    fields = {"llm_provider": LLMProvider.OPENAI, "openai_enabled": True, **overrides}
    return Settings(**fields)


def test_create_openai_chat_model_raises_when_api_key_missing(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(config_module, "get_settings", lambda: _openai_settings())
    monkeypatch.setattr(llm_provider, "get_settings", config_module.get_settings)

    with pytest.raises(OpenAINotConfiguredError):
        llm_provider._create_openai_chat_model(model="gpt-4o-mini", temperature=0.2)


def test_create_openai_chat_model_raises_when_disabled_even_with_a_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-a-real-key")
    monkeypatch.setattr(config_module, "get_settings", lambda: _openai_settings(openai_enabled=False))
    monkeypatch.setattr(llm_provider, "get_settings", config_module.get_settings)

    with pytest.raises(OpenAIDisabledError):
        llm_provider._create_openai_chat_model(model="gpt-4o-mini", temperature=0.2)


def test_create_openai_chat_model_builds_a_chat_openai_when_configured(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-a-real-key")
    monkeypatch.setattr(config_module, "get_settings", lambda: _openai_settings())
    monkeypatch.setattr(llm_provider, "get_settings", config_module.get_settings)

    from langchain_openai import ChatOpenAI

    model = llm_provider._create_openai_chat_model(model="gpt-4o-mini", temperature=0.2)
    assert isinstance(model, ChatOpenAI)
    assert model.model_name == "gpt-4o-mini"


def test_check_openai_availability_raises_when_api_key_missing(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(config_module, "get_settings", lambda: _openai_settings())
    monkeypatch.setattr(llm_provider, "get_settings", config_module.get_settings)

    with pytest.raises(OpenAINotConfiguredError):
        llm_provider.check_openai_availability()


def test_check_openai_availability_is_a_noop_when_provider_is_not_openai(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(config_module, "get_settings", lambda: Settings(llm_provider=LLMProvider.OLLAMA))
    monkeypatch.setattr(llm_provider, "get_settings", config_module.get_settings)

    llm_provider.check_openai_availability()  # must not raise -- provider isn't active


def test_check_llm_availability_dispatches_to_openai_when_configured(monkeypatch):
    calls = []
    monkeypatch.setattr(config_module, "get_settings", lambda: _openai_settings())
    monkeypatch.setattr(llm_provider, "get_settings", config_module.get_settings)
    monkeypatch.setattr(llm_provider, "check_openai_availability", lambda: calls.append("openai"))
    monkeypatch.setattr(llm_provider, "check_ollama_availability", lambda **kw: calls.append("ollama"))

    llm_provider.check_llm_availability()

    assert calls == ["openai"]


def test_check_llm_availability_dispatches_to_ollama_by_default(monkeypatch):
    calls = []
    monkeypatch.setattr(config_module, "get_settings", lambda: Settings())
    monkeypatch.setattr(llm_provider, "get_settings", config_module.get_settings)
    monkeypatch.setattr(llm_provider, "check_openai_availability", lambda: calls.append("openai"))
    monkeypatch.setattr(llm_provider, "check_ollama_availability", lambda **kw: calls.append("ollama"))

    llm_provider.check_llm_availability()

    assert calls == ["ollama"]


def test_ai_provider_env_var_selects_openai(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "openai")
    config_module.get_settings.cache_clear()
    try:
        assert config_module.get_settings().llm_provider == LLMProvider.OPENAI
    finally:
        config_module.get_settings.cache_clear()


def test_ai_provider_env_var_unset_defaults_to_ollama(monkeypatch):
    monkeypatch.delenv("AI_PROVIDER", raising=False)
    config_module.get_settings.cache_clear()
    try:
        assert config_module.get_settings().llm_provider == LLMProvider.OLLAMA
    finally:
        config_module.get_settings.cache_clear()


def test_openai_api_key_is_never_logged_by_the_availability_check(monkeypatch, caplog):
    # The one real secret in this whole path -- prove that even a failing
    # check never puts the key value into a log record. Uses a
    # recognizable fake value so a leak would be unambiguous if it
    # occurred.
    fake_key = "sk-THIS-VALUE-MUST-NEVER-APPEAR-IN-ANY-LOG-abcdef123456"
    monkeypatch.setenv("OPENAI_API_KEY", fake_key)
    monkeypatch.setattr(config_module, "get_settings", lambda: _openai_settings(openai_enabled=False))
    monkeypatch.setattr(llm_provider, "get_settings", config_module.get_settings)

    with caplog.at_level(logging.DEBUG):
        with pytest.raises(OpenAIDisabledError):
            llm_provider.check_openai_availability()

    for record in caplog.records:
        assert fake_key not in record.getMessage()


def test_openai_unavailable_error_redacts_the_api_key_from_the_underlying_cause(monkeypatch):
    """Adversarial hardening pass (2026-09-18): the OTHER real leak path
    the above test doesn't cover -- OpenAIUnavailableError previously
    embedded str(cause) verbatim, and that message reaches a real
    console print (main.py's `ai-health` command), untested until now.
    Uses a recognizable fake key so a leak would be unambiguous."""
    from llm.errors import OpenAIUnavailableError

    fake_key = "sk-THIS-VALUE-MUST-NEVER-APPEAR-IN-ANY-ERROR-MESSAGE-abcdef123456"
    monkeypatch.setenv("OPENAI_API_KEY", fake_key)

    # A real SDK exception's __str__ can embed request/header details --
    # simulated here since the real key value should never actually
    # reach a live OpenAI call in a test.
    cause = RuntimeError(f"401 Unauthorized: Authorization: Bearer {fake_key}")
    error = OpenAIUnavailableError(cause=cause)

    assert fake_key not in str(error)
    assert "***" in str(error)
    assert error.cause is cause  # the real exception object itself is still preserved for programmatic inspection


def test_openai_unavailable_error_with_no_matching_key_in_env_still_reports_the_cause():
    """When the cause genuinely doesn't contain a live key (the common
    case -- a plain network timeout, say), the message must still be
    informative, not silently blanked."""
    from llm.errors import OpenAIUnavailableError

    error = OpenAIUnavailableError(cause=RuntimeError("Connection timed out"))
    assert "Connection timed out" in str(error)
