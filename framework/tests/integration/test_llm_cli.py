"""CLI opt-in behavior using fakes, never a live API."""

from unittest.mock import Mock
from uuid import uuid4

import pytest

from agent_smith.cli import main
from agent_smith.providers import LLMError, LLMResponse
from agent_smith.providers import gemini


def test_default_cli_does_not_construct_model(monkeypatch):
    factory = Mock(side_effect=AssertionError("No default API call"))
    monkeypatch.setattr(gemini, "GeminiProvider", factory)
    assert main([]) == 0
    factory.assert_not_called()


@pytest.mark.parametrize("arguments,prompt", [
    (["--llm-smoke-test"], "Explain in two sentences what a Python IndexError is."),
    (["--prompt", "Explain a loop"], "Explain a loop"),
])
def test_explicit_live_option_uses_fake(monkeypatch, capsys, arguments, prompt):
    provider = Mock()
    provider.ask.return_value = LLMResponse(text="Answer", provider="google", model="configured", latency_seconds=0.2)
    monkeypatch.setattr(gemini, "GeminiProvider", Mock(return_value=provider))
    assert main(arguments) == 0
    provider.ask.assert_called_once_with(prompt)
    assert "Answer" in capsys.readouterr().out


def test_missing_key_is_reported_without_api(capsys):
    assert main(["--llm-smoke-test"]) == 2
    assert "SMITH_LLM_API_KEY" in capsys.readouterr().err


def test_cli_quota_error(monkeypatch, capsys):
    provider = Mock()
    provider.ask.side_effect = LLMError("quota", "Gemini quota exceeded.")
    monkeypatch.setattr(gemini, "GeminiProvider", Mock(return_value=provider))
    assert main(["--llm-smoke-test"]) == 2
    assert "quota" in capsys.readouterr().err


def test_echoed_secret_is_redacted(monkeypatch, capsys):
    private = uuid4().hex
    monkeypatch.setenv("SMITH_LLM_API_KEY", private)
    provider = Mock()
    provider.ask.return_value = LLMResponse(text=f"Echo {private}", provider="google", model="configured", latency_seconds=0)
    monkeypatch.setattr(gemini, "GeminiProvider", Mock(return_value=provider))
    assert main(["--llm-smoke-test"]) == 0
    output = capsys.readouterr().out
    assert private not in output
    assert "[REDACTED]" in output
