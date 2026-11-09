"""Exercise actual compiled LangGraph transitions with scripted providers."""

from uuid import uuid4
import socket

import pytest
from langgraph.graph.state import CompiledStateGraph
from pydantic import ValidationError

from agent_smith.agent import run_agent
from agent_smith.agent.graph import GRAPH_RECURSION_LIMIT, build_graph, initial_state
from agent_smith.agent.models import AgentState
from agent_smith.agent.nodes import decide_next_step, generate_node
from agent_smith.providers.base import LLMError, LLMResponse, TokenUsage


class ScriptedProvider:
    def __init__(self, *outputs):
        self.outputs = list(outputs)
        self.prompts = []

    def ask(self, prompt):
        self.prompts.append(prompt)
        assert self.outputs, "Unexpected extra LLM call"
        output = self.outputs.pop(0)
        if isinstance(output, Exception):
            raise output
        if isinstance(output, LLMResponse):
            return output
        return LLMResponse(text=output, provider="fake", model="offline", latency_seconds=0.125)


def traverse(provider, budget=2):
    graph = build_graph(provider)
    events = list(graph.stream(initial_state("Write a Python function", budget),
        config={"recursion_limit": GRAPH_RECURSION_LIMIT}, stream_mode="updates"))
    path = [name for update in events for name in update]
    return path, events[-1]["finalize"]["result"]


def test_compiled_graph_and_success_path():
    provider = ScriptedProvider("def f():\n    return 1", "must not be used")
    graph = build_graph(provider)
    assert isinstance(graph, CompiledStateGraph)
    path, result = traverse(provider)
    assert path == ["generate", "verify", "finalize"]
    assert result.status == "unverified"
    assert result.stop_reason == "syntax_passed_functionality_unverified"
    assert result.llm_calls == len(provider.prompts) == 1
    assert result.attempts[0].verification.passed
    assert len(provider.outputs) == 1


def test_error_then_correction_follows_real_conditional_edge():
    provider = ScriptedProvider("def f(:", "def f():\n    return 1", "unused")
    path, result = traverse(provider)
    assert path == ["generate", "verify", "generate", "verify", "finalize"]
    assert result.status == "unverified"
    assert result.llm_calls == len(provider.prompts) == 2
    assert [a.iteration for a in result.attempts] == [1, 2]
    assert [a.verification.passed for a in result.attempts] == [False, True]
    assert "def f(:" in provider.prompts[1]
    assert "Invalid Python syntax" in provider.prompts[1]
    assert len(provider.outputs) == 1


def test_two_failures_exhaust_budget():
    provider = ScriptedProvider("def f(:", "def g(:", "unused")
    path, result = traverse(provider)
    assert path == ["generate", "verify", "generate", "verify", "finalize"]
    assert result.status == "failed"
    assert result.stop_reason == "budget_exhausted"
    assert result.llm_calls == len(provider.prompts) == 2
    assert len(result.attempts) == 2
    assert len(provider.outputs) == 1


def test_one_call_budget_stops_after_error():
    provider = ScriptedProvider("def f(:", "x = 1")
    path, result = traverse(provider, budget=1)
    assert path == ["generate", "verify", "finalize"]
    assert result.stop_reason == "budget_exhausted"
    assert result.llm_calls == len(provider.prompts) == 1


@pytest.mark.parametrize("first", ["", " ", "```python\n```", "```python\nx=1\n```\n```python\ny=2\n```", "This is not usable Python.", "# only a comment", LLMError("empty_response", "not propagated")])
def test_unusable_or_empty_output_can_be_corrected(first):
    provider = ScriptedProvider(first, "x = 1")
    result = run_agent("Task", provider)
    assert result.status == "unverified"
    assert result.llm_calls == len(provider.prompts) == 2
    assert not result.attempts[0].verification.passed


def test_two_empty_outputs_fail_without_claiming_code():
    provider = ScriptedProvider("", "")
    result = run_agent("Task", provider)
    assert result.status == "failed"
    assert result.code == ""
    assert result.stop_reason == "budget_exhausted"


def test_single_markdown_block_is_extracted():
    result = run_agent("Task", ScriptedProvider("```python\nx = 1\n```"))
    assert result.code == "x = 1"
    assert result.attempts[0].code == "x = 1"
    assert result.llm_calls == 1


@pytest.mark.parametrize("code", ["missing_key", "authentication", "quota", "timeout", "network", "model", "provider"])
def test_provider_errors_stop_without_syntax_retry_or_secret(code):
    private = uuid4().hex
    provider = ScriptedProvider(LLMError(code, private), "x = 1")
    path, result = traverse(provider)
    assert path == ["generate", "verify", "finalize"]
    assert result.status == "failed"
    assert result.stop_reason == ("provider_error" if code == "provider" else f"provider_{code}")
    assert result.llm_calls == len(provider.prompts) == 1
    assert "not performed" in result.attempts[0].verification.errors[0]
    assert result.attempts[0].verification.level == "structure"
    assert not result.attempts[0].verification.code_extracted
    assert private not in result.model_dump_json()


def test_unexpected_provider_error_is_controlled():
    private = uuid4().hex
    result = run_agent("Task", ScriptedProvider(RuntimeError(private), "unused"))
    assert result.status == "failed"
    assert result.stop_reason == "provider_error"
    assert result.llm_calls == 1
    assert private not in result.model_dump_json()


def test_configuration_error_is_not_retried():
    try:
        AgentState(task=" ")
    except ValidationError as exc:
        error = exc
    provider = ScriptedProvider(error, "unused")
    result = run_agent("Task", provider)
    assert result.stop_reason == "configuration_invalid"
    assert len(provider.prompts) == 1


def test_provider_error_on_correction_preserves_first_attempt():
    provider = ScriptedProvider("def f(:", LLMError("quota", "private"))
    result = run_agent("Task", provider)
    assert result.stop_reason == "provider_quota"
    assert result.llm_calls == 2
    assert result.attempts[0].code == "def f(:"
    assert len(result.attempts) == 2
    assert result.token_usage is None


def test_metrics_sum_only_reported_counts():
    first = LLMResponse(text="def f(:", provider="fake", model="offline", latency_seconds=0.2,
        usage=TokenUsage(input_tokens=10, output_tokens=2, total_tokens=12))
    second = LLMResponse(text="x = 1", provider="fake", model="offline", latency_seconds=0.3,
        usage=TokenUsage(input_tokens=20, output_tokens=3, total_tokens=23))
    result = run_agent("Task", ScriptedProvider(first, second))
    assert result.total_latency_seconds == 0.5
    assert result.token_usage == TokenUsage(input_tokens=30, output_tokens=5, total_tokens=35)
    assert [a.latency_seconds for a in result.attempts] == [0.2, 0.3]


def test_missing_usage_never_becomes_partial_task_total():
    first = LLMResponse(text="def f(:", provider="fake", model="offline", latency_seconds=0,
        usage=TokenUsage(input_tokens=10, output_tokens=2))
    result = run_agent("Task", ScriptedProvider(first, "x = 1"))
    assert result.token_usage is None
    assert result.attempts[0].token_usage.input_tokens == 10


def test_partial_fields_aggregate_only_when_known_for_every_call():
    first = LLMResponse(text="def f(:", provider="fake", model="offline", latency_seconds=0,
        usage=TokenUsage(input_tokens=10))
    second = LLMResponse(text="x = 1", provider="fake", model="offline", latency_seconds=0,
        usage=TokenUsage(input_tokens=20))
    result = run_agent("Task", ScriptedProvider(first, second))
    assert result.token_usage.input_tokens == 30
    assert result.token_usage.output_tokens is None
    assert result.token_usage.total_tokens is None


@pytest.mark.parametrize("budget", [0, 3, True])
def test_invalid_budget_fails_before_provider_call(budget):
    provider = ScriptedProvider("unused")
    with pytest.raises(ValidationError):
        run_agent("Task", provider, max_llm_calls=budget)
    assert provider.prompts == []


def test_no_code_execution_even_for_top_level_side_effects(tmp_path):
    marker = tmp_path / "must_not_exist.txt"
    code = f"from pathlib import Path\nPath({str(marker)!r}).write_text('executed')\nraise RuntimeError('executed')"
    result = run_agent("Task", ScriptedProvider(code))
    assert result.status == "unverified"
    assert not marker.exists()


def test_socket_guard_is_active():
    with pytest.raises(AssertionError, match="Network access is forbidden"):
        socket.create_connection(("127.0.0.1", 1), timeout=0.01)


def test_reused_graph_does_not_share_history():
    provider = ScriptedProvider("x=1", "y=2")
    graph = build_graph(provider)
    first = graph.invoke(initial_state("First"))["result"]
    second = graph.invoke(initial_state("Second"))["result"]
    assert first.task == "First" and second.task == "Second"
    assert first.llm_calls == second.llm_calls == 1
    assert first.attempts[0].code == "x=1"
    assert second.attempts[0].code == "y=2"


def test_generate_guard_rejects_exhausted_state():
    provider = ScriptedProvider("x=1")
    state = initial_state("Task", 1)
    state["llm_calls"] = 1
    with pytest.raises(ValueError, match="budget"):
        generate_node(state, provider)
    assert provider.prompts == []


def test_elapsed_time_and_mermaid_are_available_offline():
    graph = build_graph(ScriptedProvider("x=1"))
    output = graph.invoke(initial_state("Task"))
    assert output["elapsed_seconds"] >= 0
    mermaid = graph.get_graph().draw_mermaid()
    for name in ["generate", "verify", "finalize"]:
        assert name in mermaid
