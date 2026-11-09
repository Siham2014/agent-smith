"""Whole workflow with a fake provider; generated programs are never run."""

import ast
import json
from pathlib import Path
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from agent_smith.agent import AgentResult, AgentState, run_agent
from agent_smith.agent import runner
from agent_smith.agent.runner import generate_code
from agent_smith.config import LLMSettings
from agent_smith.llm.errors import (
    LLMAuthenticationError, LLMConfigurationError, LLMEmptyResponseError,
    LLMNetworkError, LLMProviderError, LLMRateLimitError, LLMTimeoutError,
    MissingAPIKeyError,
)
from agent_smith.llm.models import LLMResponse, TokenUsage

VALID = "def answer():\n    return 42"
INVALID = "def answer()\n    return 42"
SECRET = "synthetic-secret-only"


@pytest.mark.parametrize("task", ["", "   ", None])
def test_empty_task_rejected_before_provider(task, provider_factory) -> None:
    provider = provider_factory(VALID)
    with pytest.raises(ValidationError):
        run_agent(task, provider)
    assert provider.calls == 0


@pytest.mark.parametrize("budget", [0, -1, 3, True])
def test_invalid_budget_rejected_before_provider(budget, provider_factory) -> None:
    provider = provider_factory(VALID)
    with pytest.raises(ValidationError):
        run_agent("task", provider, max_llm_calls=budget)
    assert provider.calls == 0


def test_first_valid_generation_stops_without_second_call(provider_factory) -> None:
    provider = provider_factory(VALID, INVALID)
    result = run_agent("Return 42", provider)
    assert result.status == "unverified"
    assert result.stop_reason == "syntax_passed_functionality_unverified"
    assert result.code == VALID
    assert result.llm_calls == provider.calls == 1
    assert result.attempts[0].verification.passed
    assert result.attempts[0].verification.level == "syntax"


def test_syntax_error_then_correction_records_feedback(provider_factory) -> None:
    provider = provider_factory(INVALID, VALID)
    result = run_agent("Return 42", provider)
    assert result.status == "unverified"
    assert result.llm_calls == provider.calls == 2
    assert [attempt.iteration for attempt in result.attempts] == [1, 2]
    assert [attempt.verification.passed for attempt in result.attempts] == [False, True]
    assert [attempt.code for attempt in result.attempts] == [INVALID, VALID]
    payload = json.loads(provider.requests[1].prompt.split("\nDATA:\n")[1])
    assert payload["previous_code"] == INVALID
    assert payload["static_errors"] == result.attempts[0].verification.errors
    assert "Revise" in provider.requests[1].prompt


def test_two_errors_never_consume_a_third_output(provider_factory) -> None:
    provider = provider_factory(INVALID, INVALID, VALID)
    result = run_agent("task", provider)
    assert result.status == "failed"
    assert result.stop_reason == "budget_exhausted"
    assert result.llm_calls == provider.calls == len(result.attempts) == 2


def test_one_call_budget_prevents_revision(provider_factory) -> None:
    provider = provider_factory(INVALID, VALID)
    result = run_agent("task", provider, max_llm_calls=1)
    assert result.status == "failed"
    assert result.stop_reason == "budget_exhausted"
    assert result.llm_calls == provider.calls == 1


@pytest.mark.parametrize("first_output", [
    "", "  ", LLMEmptyResponseError(SECRET),
    "```python\nx=1\n```\n```python\ny=2\n```",
])
def test_unusable_output_can_be_revised(first_output, provider_factory) -> None:
    provider = provider_factory(first_output, VALID)
    result = run_agent("task", provider)
    assert result.status == "unverified"
    assert result.llm_calls == 2
    assert result.attempts[0].verification.code_extracted is False
    assert "Extraction error" in result.attempts[0].verification.errors[0]
    assert SECRET not in result.model_dump_json()


def test_two_empty_outputs_exhaust_budget(provider_factory) -> None:
    provider = provider_factory(LLMEmptyResponseError(SECRET), "")
    result = run_agent("task", provider)
    assert result.status == "failed"
    assert result.stop_reason == "budget_exhausted"
    assert result.llm_calls == 2


def test_markdown_python_is_extracted_without_revision(provider_factory) -> None:
    provider = provider_factory("```python\n" + VALID + "\n```")
    result = run_agent("task", provider)
    assert result.code == VALID
    assert result.llm_calls == 1
    assert result.status == "unverified"


@pytest.mark.parametrize("failure,reason", [
    (MissingAPIKeyError(SECRET), "missing_api_key"),
    (LLMConfigurationError(SECRET), "configuration_error"),
    (LLMAuthenticationError(SECRET), "authentication_error"),
    (LLMRateLimitError(SECRET), "quota_exceeded"),
    (LLMTimeoutError(SECRET), "timeout"),
    (LLMNetworkError(SECRET), "network_error"),
    (LLMProviderError(SECRET), "provider_error"),
    (RuntimeError(SECRET), "unexpected_error"),
])
def test_provider_failures_stop_without_retry_or_secret_leak(
    failure, reason, provider_factory, caplog, capsys,
) -> None:
    provider = provider_factory(failure, VALID)
    result = run_agent("task", provider)
    assert result.status == "failed"
    assert result.stop_reason == reason
    assert result.llm_calls == provider.calls == len(result.attempts) == 1
    assert result.attempts[0].error_kind == reason
    assert SECRET not in result.model_dump_json()
    assert SECRET not in caplog.text
    assert SECRET not in capsys.readouterr().out


def test_failure_on_second_call_is_counted_and_history_stays_consistent(provider_factory) -> None:
    provider = provider_factory(INVALID, LLMNetworkError(SECRET))
    result = run_agent("task", provider)
    assert result.stop_reason == "network_error"
    assert result.llm_calls == len(result.attempts) == 2
    assert result.attempts[0].code == INVALID
    assert result.attempts[1].code == result.code == ""


def test_call_count_incremented_before_external_attempt(provider_factory) -> None:
    state = AgentState(task="task")
    provider = provider_factory()
    def fail_after_inspection(request):
        assert state.llm_calls == 1
        assert state.status == "generating"
        raise LLMTimeoutError(SECRET)
    provider.generate = fail_after_inspection
    with pytest.raises(LLMTimeoutError):
        generate_code(state, provider)
    assert state.llm_calls == 1


def test_injected_provider_does_not_load_env_or_close_client(
    provider_factory, monkeypatch,
) -> None:
    load = Mock(side_effect=AssertionError("Must not read local configuration"))
    monkeypatch.setattr(runner, "AgentSettings", load)
    provider = provider_factory(VALID)
    run_agent("task", provider)
    load.assert_not_called()
    assert provider.close_calls == 0


def test_ambiguous_provider_and_settings_rejected(provider_factory) -> None:
    provider = provider_factory(VALID)
    with pytest.raises(ValueError):
        run_agent("task", provider, settings=LLMSettings())
    assert provider.calls == 0


@pytest.mark.parametrize("outputs", [[VALID], [INVALID, VALID]])
def test_default_path_reuses_phase_two_adapter_and_closes_once(
    outputs, provider_factory, monkeypatch,
) -> None:
    provider = provider_factory(*outputs)
    factory = Mock(return_value=provider)
    monkeypatch.setattr(runner, "GeminiProvider", factory)
    settings = LLMSettings(provider="google", model="fake", api_key=SECRET)
    result = run_agent("task", settings=settings)
    factory.assert_called_once_with(settings)
    assert result.status == "unverified"
    assert provider.close_calls == 1
    assert provider.calls == len(outputs)


def test_client_creation_failure_returns_zero_call_result(monkeypatch) -> None:
    monkeypatch.setattr(runner, "GeminiProvider", Mock(
        side_effect=MissingAPIKeyError(SECRET),
    ))
    result = run_agent("task", settings=LLMSettings())
    assert result.status == "failed"
    assert result.stop_reason == "missing_api_key"
    assert result.llm_calls == 0
    assert result.attempts == []
    assert SECRET not in result.model_dump_json()


@pytest.mark.parametrize("first,reason", [
    (VALID, "client_cleanup_error"),
    (LLMNetworkError(SECRET), "network_error"),
])
def test_owned_client_cleanup_error_is_controlled(
    first, reason, provider_factory, monkeypatch,
) -> None:
    provider = provider_factory(first)
    provider.close = Mock(side_effect=RuntimeError(SECRET))
    monkeypatch.setattr(runner, "GeminiProvider", Mock(return_value=provider))
    result = run_agent("task", settings=LLMSettings())
    assert result.status == "failed"
    assert result.stop_reason == reason
    assert SECRET not in result.model_dump_json()


def test_cancellation_propagates_and_owned_client_is_closed(
    provider_factory, monkeypatch,
) -> None:
    provider = provider_factory(KeyboardInterrupt())
    monkeypatch.setattr(runner, "GeminiProvider", Mock(return_value=provider))
    with pytest.raises(KeyboardInterrupt):
        run_agent("task", settings=LLMSettings())
    assert provider.close_calls == 1


def test_metrics_and_elapsed_time_are_measured_separately(provider_factory) -> None:
    clock = iter([10.0, 10.1, 10.3, 11.0])
    provider = provider_factory(INVALID, VALID)
    result = run_agent("task", provider, clock=lambda: next(clock))
    assert result.total_latency_seconds == 1.0
    assert sum(attempt.latency_seconds for attempt in result.attempts) == pytest.approx(0.2)
    assert result.token_usage.model_dump() == dict(
        input_tokens=4, output_tokens=6, total_tokens=10,
        reasoning_tokens=None, cached_tokens=None,
    )


def test_failed_call_latency_is_measured_without_fabricated_tokens(provider_factory) -> None:
    clock = iter([10.0, 10.1, 10.4, 11.0])
    result = run_agent(
        "task", provider_factory(LLMTimeoutError(SECRET)), clock=lambda: next(clock),
    )
    assert result.total_latency_seconds == 1.0
    assert result.attempts[0].latency_seconds == pytest.approx(0.3)
    assert result.attempts[0].token_usage is None
    assert result.token_usage is None


def test_missing_token_metadata_stays_unknown(provider_factory) -> None:
    no_usage = LLMResponse(text=VALID, provider="fake", model="fake", latency_seconds=0)
    result = run_agent("task", provider_factory(no_usage))
    assert result.token_usage is None
    assert result.attempts[0].token_usage is None


def test_partial_tokens_only_aggregate_complete_fields(provider_factory) -> None:
    first = LLMResponse(
        text=INVALID, provider="fake", model="fake", latency_seconds=0,
        usage=TokenUsage(input_tokens=2, cached_tokens=0),
    )
    second = LLMResponse(
        text=VALID, provider="fake", model="fake", latency_seconds=0,
        usage=TokenUsage(input_tokens=3, output_tokens=4, cached_tokens=0),
    )
    result = run_agent("task", provider_factory(first, second))
    assert result.token_usage.input_tokens == 5
    assert result.token_usage.output_tokens is None
    assert result.token_usage.total_tokens is None
    assert result.token_usage.cached_tokens == 0


def test_failed_call_does_not_make_partial_tokens_look_complete(provider_factory) -> None:
    result = run_agent("task", provider_factory(INVALID, LLMNetworkError(SECRET)))
    assert result.attempts[0].token_usage.total_tokens == 5
    assert result.token_usage is None


def test_generated_code_is_never_executed(provider_factory, tmp_path: Path) -> None:
    marker = tmp_path / "must-not-exist"
    source = (
        "from pathlib import Path\n"
        f"Path({str(marker)!r}).write_text('executed')\n"
        "raise RuntimeError('must not execute')"
    )
    result = run_agent("task", provider_factory(source))
    assert result.status == "unverified"
    assert not marker.exists()


def test_syntax_valid_does_not_mean_functionally_correct(provider_factory) -> None:
    result = run_agent("Return 42", provider_factory("def answer():\n    return 1 / 0"))
    assert result.status == "unverified"
    assert result.stop_reason == "syntax_passed_functionality_unverified"
    assert result.llm_calls == 1


def test_no_execution_primitives_in_agent_source() -> None:
    root = Path(runner.__file__).parent
    for path in root.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id not in {"exec", "eval", "compile", "__import__"}
            if isinstance(node, ast.Import):
                assert all(alias.name != "subprocess" for alias in node.names)


def test_result_round_trips_with_validated_history(provider_factory) -> None:
    result = run_agent("task", provider_factory(INVALID, VALID))
    assert AgentResult.model_validate_json(result.model_dump_json()) == result


def test_invalid_normalized_provider_response_stops_safely(provider_factory) -> None:
    malformed = LLMResponse(
        text=VALID, provider="fake", model="fake", latency_seconds=0,
    )
    malformed.latency_seconds = -1
    provider = provider_factory(malformed, VALID)
    result = run_agent("task", provider)
    assert result.status == "failed"
    assert result.stop_reason == "provider_error"
    assert result.llm_calls == provider.calls == 1


def test_unexpected_static_failure_returns_a_controlled_result(
    provider_factory, monkeypatch,
) -> None:
    def fail(state):
        raise RuntimeError(SECRET)
    monkeypatch.setattr(runner, "verify_code", fail)
    provider = provider_factory(VALID, VALID)
    result = run_agent("task", provider)
    assert result.status == "failed"
    assert result.stop_reason == "unexpected_error"
    assert result.llm_calls == provider.calls == 1
    assert result.attempts[0].verification.code_extracted
    assert SECRET not in result.model_dump_json()
