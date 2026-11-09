"""LangGraph nodes and deterministic routing, using an injected provider."""

from time import perf_counter
from typing import Literal, TypedDict

from pydantic import ValidationError

from agent_smith.agent.models import AgentResult, AgentState, AttemptRecord, VerificationResult
from agent_smith.agent.prompts import build_prompt
from agent_smith.agent.verifier import CodeExtractionError, extract_python_code, verify_code
from agent_smith.providers.base import ChatProvider, LLMError, LLMResponse, TokenUsage


class GraphState(TypedDict):
    task: str
    generated_code: str
    llm_calls: int
    max_llm_calls: int
    attempts: list[AttemptRecord]
    status: str
    stop_reason: str | None
    last_observation: str
    elapsed_seconds: float
    # Transient per-invocation data, never credentials or a provider instance.
    response: LLMResponse | None
    generation_error: str | None
    call_latency: float
    started_at: float
    result: AgentResult | None


def validated_state(state: GraphState) -> AgentState:
    return AgentState.model_validate({key: state[key] for key in AgentState.model_fields if key in state})


def generate_node(state: GraphState, provider: ChatProvider) -> dict:
    current = validated_state(state)
    if current.status not in ("pending", "needs_revision") or current.llm_calls >= current.max_llm_calls:
        raise ValueError("Generation requires an active state and available call budget")
    prompt = build_prompt(current.task, current.generated_code, current.last_observation)
    calls = current.llm_calls + 1  # Count attempted requests, including failed ones.
    start = perf_counter()
    try:
        response = provider.ask(prompt)
    except LLMError as exc:
        error = exc.code if exc.code in {"empty_response", "missing_key", "authentication", "quota", "timeout", "network", "model"} else "error"
        return dict(llm_calls=calls, response=None, generated_code="", generation_error=error,
                    call_latency=perf_counter() - start, status="pending")
    except ValidationError:
        return dict(llm_calls=calls, response=None, generated_code="", generation_error="configuration_invalid",
                    call_latency=perf_counter() - start, status="pending")
    except Exception:
        # Unexpected provider failures may contain credentials; never copy their text.
        return dict(llm_calls=calls, response=None, generated_code="", generation_error="error",
                    call_latency=perf_counter() - start, status="pending")
    return dict(llm_calls=calls, response=response, generated_code=response.text,
                generation_error=None, call_latency=response.latency_seconds, status="pending")


def verify_node(state: GraphState) -> dict:
    current = validated_state(state)
    error = state["generation_error"]
    fatal = error is not None and error != "empty_response"
    code = ""
    if fatal:
        verification = VerificationResult(passed=False, level="structure", code_extracted=False,
            errors=["Provider failure: static verification was not performed."])
    else:
        try:
            code = extract_python_code(current.generated_code)
            verification = verify_code(code)
        except CodeExtractionError as exc:
            verification = VerificationResult(passed=False, level="structure", code_extracted=False,
                errors=[str(exc)])
    response = state["response"]
    record = AttemptRecord(iteration=current.llm_calls, code=code, verification=verification,
        latency_seconds=state["call_latency"], token_usage=response.usage if response else None)
    if fatal:
        status, reason = "failed", "configuration_invalid" if error == "configuration_invalid" else f"provider_{error}"
    elif verification.passed:
        status, reason = "unverified", "syntax_passed_functionality_unverified"
    elif current.llm_calls >= current.max_llm_calls:
        status, reason = "failed", "budget_exhausted"
    else:
        status, reason = "needs_revision", None
    # Retain raw text for a correction if extraction failed; never execute it.
    proposal = code if verification.code_extracted else current.generated_code
    update = dict(generated_code=proposal, attempts=[*current.attempts, record],
        status=status, stop_reason=reason,
        last_observation="Syntax passed; functionality remains unverified." if verification.passed else "\n".join(verification.errors))
    validated_state({**state, **update})
    return update


def decide_next_step(state: GraphState) -> Literal["retry", "finish"]:
    current = validated_state(state)
    if current.status == "needs_revision" and current.llm_calls < current.max_llm_calls:
        return "retry"
    return "finish"


def aggregate_usage(attempts: list[AttemptRecord]) -> TokenUsage | None:
    # A task total is known only if every attempted request reported that counter.
    if not attempts:
        return None
    totals = {}
    for field in ("input_tokens", "output_tokens", "total_tokens"):
        values = [getattr(a.token_usage, field) if a.token_usage is not None else None for a in attempts]
        totals[field] = sum(values) if all(v is not None for v in values) else None
    return TokenUsage(**totals) if any(v is not None for v in totals.values()) else None


def finalize_node(state: GraphState) -> dict:
    current = validated_state(state)
    if current.status not in ("unverified", "failed"):
        raise ValueError("Cannot finalize a nonterminal state")
    result = AgentResult(task=current.task, code=current.attempts[-1].code if current.attempts else "",
        status=current.status, stop_reason=current.stop_reason, llm_calls=current.llm_calls,
        total_latency_seconds=sum(a.latency_seconds for a in current.attempts),
        attempts=current.attempts, token_usage=aggregate_usage(current.attempts))
    return dict(result=result, elapsed_seconds=perf_counter() - state["started_at"])
