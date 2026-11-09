"""Decisions depend on state only, without a provider."""

import pytest

from agent_smith.agent.controller import decide_next_step
from agent_smith.agent.models import (
    AgentState, AttemptRecord, VerificationResult,
)


def checked_state(passed=False, calls=1, budget=2, error=None) -> AgentState:
    observation = VerificationResult(
        passed=passed, code_extracted=error is None,
        errors=[] if passed else ["Static error."],
    )
    code = "x = 1" if error is None else ""
    attempts = [
        AttemptRecord(
            iteration=i, code=code, verification=observation,
            latency_seconds=0, error_kind=error,
        )
        for i in range(1, calls + 1)
    ]
    return AgentState(
        task="task", generated_code=code, llm_calls=calls,
        max_llm_calls=budget, attempts=attempts, status="verifying",
        last_observation=observation, last_error=error,
    )


def test_pending_state_requests_generation() -> None:
    decision = decide_next_step(AgentState(task="task"))
    assert decision.next_step == "generate"
    assert decision.status == "generating"
    assert decision.stop_reason is None


@pytest.mark.parametrize("budget", [1, 2])
def test_static_pass_finalizes_even_at_budget_limit(budget) -> None:
    state = checked_state(passed=True, budget=budget)
    decision = decide_next_step(state)
    assert decision.next_step == "finalize"
    assert decision.status == "unverified"
    assert decision.stop_reason == "syntax_passed_functionality_unverified"


def test_static_failure_requests_revision_when_budget_remains() -> None:
    decision = decide_next_step(checked_state())
    assert decision.next_step == "retry"
    assert decision.status == "needs_revision"


@pytest.mark.parametrize("calls,budget", [(1, 1), (2, 2)])
def test_exhausted_budget_finalizes_failure(calls, budget) -> None:
    decision = decide_next_step(checked_state(calls=calls, budget=budget))
    assert decision.next_step == "finalize"
    assert decision.status == "failed"
    assert decision.stop_reason == "budget_exhausted"


@pytest.mark.parametrize("reason", [
    "configuration_error", "missing_api_key", "authentication_error",
    "quota_exceeded", "timeout", "network_error", "provider_error",
    "unexpected_error",
])
def test_fatal_error_stops_even_with_remaining_budget(reason) -> None:
    decision = decide_next_step(checked_state(error=reason))
    assert decision.next_step == "finalize"
    assert decision.status == "failed"
    assert decision.stop_reason == reason


def test_decision_is_deterministic_and_does_not_mutate_state() -> None:
    state = checked_state()
    before = state.model_dump()
    assert decide_next_step(state) == decide_next_step(state)
    assert state.model_dump() == before


def test_terminal_decision_is_stable() -> None:
    state = checked_state(passed=True)
    state.status = "unverified"
    state.stop_reason = "syntax_passed_functionality_unverified"
    decision = decide_next_step(state)
    assert decision.next_step == "finalize"
    assert decision.status == "unverified"


def test_inflight_generation_cannot_be_decided() -> None:
    with pytest.raises(ValueError, match="finish"):
        decide_next_step(AgentState(task="task", status="generating", llm_calls=1))
