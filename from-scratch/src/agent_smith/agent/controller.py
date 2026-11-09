"""Pure deterministic transitions; no network, clock or mutation."""

from .models import AgentState, Decision


def decide_next_step(state: AgentState) -> Decision:
    state = AgentState.model_validate(state.model_dump())
    if state.status in ("unverified", "failed"):
        return Decision(
            next_step="finalize", status=state.status, stop_reason=state.stop_reason,
        )
    if state.status == "generating":
        raise ValueError("A generation must finish before a decision is made.")
    if state.last_error:
        return Decision(
            next_step="finalize", status="failed", stop_reason=state.last_error,
        )
    if state.last_observation and state.last_observation.passed:
        return Decision(
            next_step="finalize", status="unverified",
            stop_reason="syntax_passed_functionality_unverified",
        )
    if state.llm_calls >= state.max_llm_calls:
        return Decision(
            next_step="finalize", status="failed", stop_reason="budget_exhausted",
        )
    if state.status == "pending":
        return Decision(next_step="generate", status="generating")
    return Decision(next_step="retry", status="needs_revision")
