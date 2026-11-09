"""State/history invariants and bounded diagnostics."""

import pytest
from pydantic import ValidationError

from agent_smith.agent import AgentResult, AgentState, AttemptRecord, VerificationResult
from agent_smith.agent.runner import finalize_result


def observation() -> VerificationResult:
    return VerificationResult(passed=True, code_extracted=True)


def attempt(iteration=1) -> AttemptRecord:
    return AttemptRecord(
        iteration=iteration, code="x = 1", verification=observation(), latency_seconds=0,
    )


@pytest.mark.parametrize("values", [
    {"llm_calls": -1}, {"max_llm_calls": 0}, {"max_llm_calls": 3},
    {"llm_calls": 2, "max_llm_calls": 1},
    {"llm_calls": 1},
    {"attempts": [attempt()]},
    {"llm_calls": 1, "attempts": [attempt(2)], "status": "verifying"},
    {"llm_calls": 1, "attempts": [attempt()], "status": "verifying",
     "last_observation": observation(), "generated_code": "different"},
    {"status": "needs_revision"},
    {"elapsed_seconds": -1}, {"elapsed_seconds": float("inf")},
    {"status": "pending", "stop_reason": "budget_exhausted"},
])
def test_invalid_state_invariants(values) -> None:
    with pytest.raises(ValidationError):
        AgentState(task="task", **values)


def test_last_observation_must_match_history() -> None:
    with pytest.raises(ValidationError):
        AgentState(task="task", llm_calls=1, status="verifying", attempts=[attempt()])


def test_mutable_collections_are_not_shared_between_states() -> None:
    first = AgentState(task="first")
    second = AgentState(task="second")
    first.attempts.append(attempt())
    assert second.attempts == []


@pytest.mark.parametrize("values", [
    {"passed": True, "code_extracted": False},
    {"passed": True, "code_extracted": True, "errors": ["error"]},
    {"passed": False, "code_extracted": False},
    {"passed": False, "code_extracted": False, "errors": ["x" * 241]},
    {"passed": False, "code_extracted": False, "errors": [""]},
])
def test_verification_contract_is_consistent(values) -> None:
    with pytest.raises(ValidationError):
        VerificationResult(**values)


def test_passing_attempt_needs_nonempty_code() -> None:
    with pytest.raises(ValidationError):
        AttemptRecord(
            iteration=1, code="", verification=observation(), latency_seconds=0,
        )


def test_unverified_result_needs_evidence_and_matching_code() -> None:
    values = dict(
        task="task", code="x = 1", status="unverified",
        stop_reason="syntax_passed_functionality_unverified",
        llm_calls=1, total_latency_seconds=0,
    )
    with pytest.raises(ValidationError):
        AgentResult(**values)
    assert AgentResult(**values, attempts=[attempt()]).status == "unverified"
    with pytest.raises(ValidationError):
        AgentResult(**{**values, "code": "different"}, attempts=[attempt()])


def test_finalize_rejects_nonterminal_state() -> None:
    with pytest.raises(ValueError):
        finalize_result(AgentState(task="task"))


def test_error_rendering_does_not_include_invalid_task_input() -> None:
    with pytest.raises(ValidationError) as caught:
        AgentState(task={"synthetic-secret": "not a task"})
    assert "synthetic-secret" not in str(caught.value)
