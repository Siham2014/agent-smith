"""Explicit agent mode uses the real graph and an injected fake provider."""

from unittest.mock import Mock
from uuid import uuid4

import pytest

from agent_smith.cli import main
from agent_smith.providers import LLMError, LLMResponse
from agent_smith.providers import gemini


def fake_response(text):
    return LLMResponse(text=text, provider="fake", model="offline", latency_seconds=0.1)


def test_agent_cli_reports_result_with_fake_provider(monkeypatch, capsys):
    provider = Mock()
    provider.ask.return_value = fake_response("def maximum(a,b,c):\n    return max(a,b,c)")
    factory = Mock(return_value=provider)
    monkeypatch.setattr(gemini, "GeminiProvider", factory)
    assert main(["--agent-task", "Write maximum"]) == 0
    out = capsys.readouterr().out
    for expected in ["def maximum", "Status: unverified", "syntax_passed_functionality_unverified", "LLM calls: 1", "Total latency: 0.100"]:
        assert expected in out
    factory.assert_called_once()
    provider.ask.assert_called_once()


def test_agent_cli_failure_exit_code(monkeypatch, capsys):
    provider = Mock()
    provider.ask.side_effect = [fake_response("def f(:"), fake_response("def g(:")]
    monkeypatch.setattr(gemini, "GeminiProvider", Mock(return_value=provider))
    assert main(["--agent-task", "Task"]) == 2
    out = capsys.readouterr().out
    assert "budget_exhausted" in out
    assert "LLM calls: 2" in out
    assert provider.ask.call_count == 2


def test_missing_key_is_controlled(capsys):
    assert main(["--agent-task", "Task"]) == 2
    assert "initialization failed" in capsys.readouterr().err


def test_agent_errors_never_echo_provider_secret(monkeypatch, capsys):
    private = uuid4().hex
    provider = Mock()
    provider.ask.side_effect = LLMError("authentication", private)
    monkeypatch.setattr(gemini, "GeminiProvider", Mock(return_value=provider))
    assert main(["--agent-task", "Task"]) == 2
    output = capsys.readouterr()
    assert private not in output.out + output.err
    assert "provider_authentication" in output.out


def test_agent_code_output_redacts_exact_key(monkeypatch, capsys):
    private = uuid4().hex
    monkeypatch.setenv("SMITH_LLM_API_KEY", private)
    provider = Mock()
    provider.ask.return_value = fake_response(f"value = '{private}'")
    monkeypatch.setattr(gemini, "GeminiProvider", Mock(return_value=provider))
    assert main(["--agent-task", "Task"]) == 0
    output = capsys.readouterr().out
    assert private not in output
    assert "[REDACTED]" in output


def test_blank_task_does_not_construct_provider(monkeypatch):
    factory = Mock()
    monkeypatch.setattr(gemini, "GeminiProvider", factory)
    assert main(["--agent-task", "  "]) == 2
    factory.assert_not_called()


def test_invalid_config_prevents_agent_initialization(monkeypatch, capsys):
    monkeypatch.setenv("SMITH_LLM_TIMEOUT_SECONDS", "0")
    factory = Mock()
    monkeypatch.setattr(gemini, "GeminiProvider", factory)
    assert main(["--agent-task", "Task"]) == 2
    assert "Invalid configuration" in capsys.readouterr().err
    factory.assert_not_called()


def test_agent_mode_excludes_one_shot_mode():
    with pytest.raises(SystemExit) as caught:
        main(["--agent-task", "Task", "--prompt", "Question"])
    assert caught.value.code == 2
