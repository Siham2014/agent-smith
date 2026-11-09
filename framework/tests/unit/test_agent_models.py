"""Validate public contracts and business-budget invariants."""

import pytest
from pydantic import ValidationError

from agent_smith.agent.models import AgentResult, AgentState, AttemptRecord, VerificationResult


def failed_attempt(iteration=1):
    return AttemptRecord(iteration=iteration, code="bad", latency_seconds=0.1,
        verification=VerificationResult(passed=False, level="syntax", errors=["Invalid syntax"], code_extracted=True))


@pytest.mark.parametrize("budget", [0, -1, 3, 100, True, 1.5, "2"])
def test_rejects_invalid_budget(budget):
    with pytest.raises(ValidationError):
        AgentState(task="Task", max_llm_calls=budget)


@pytest.mark.parametrize("fields", [
    {"task": " "}, {"task": "Task", "llm_calls": 3},
    {"task": "Task", "max_llm_calls": 1, "llm_calls": 2},
    {"task": "Task", "status": "success"},
    {"task": "Task", "status": "unverified", "stop_reason": "syntax_passed_functionality_unverified"},
    {"task": "Task", "status": "pending", "stop_reason": "budget_exhausted"},
    {"task": "Task", "elapsed_seconds": float("nan")},
    {"task": "Task", "llm_calls": 1, "attempts": [failed_attempt(2)]},
    {"task": "Task", "llm_calls": 1, "attempts": [failed_attempt()], "status": "failed", "stop_reason": "budget_exhausted"},
    {"task": "Task", "status": "needs_revision"},
])
def test_rejects_inconsistent_state(fields):
    with pytest.raises(ValidationError):
        AgentState(**fields)


def test_default_collections_are_independent():
    first = AgentState(task="First")
    second = AgentState(task="Second")
    first.attempts.append(failed_attempt())
    assert second.attempts == []


@pytest.mark.parametrize("fields", [
    dict(passed=True, level="syntax", code_extracted=False),
    dict(passed=True, level="syntax", code_extracted=True, errors=["error"]),
    dict(passed=False, level="syntax", code_extracted=True),
])
def test_verification_consistency(fields):
    with pytest.raises(ValidationError):
        VerificationResult(**fields)


def test_result_rejects_invented_latency():
    with pytest.raises(ValidationError):
        AgentResult(task="Task", code="bad", status="failed", stop_reason="budget_exhausted",
            llm_calls=1, attempts=[failed_attempt()], total_latency_seconds=99)
