"""AlphaCodium-Lite experimental variant: bounded Python orchestration."""

from collections.abc import Callable
from time import perf_counter

from pydantic import ValidationError

from agent_smith.config import AgentSettings, LLMSettings
from agent_smith.llm.errors import (
    LLMAuthenticationError, LLMConfigurationError, LLMEmptyResponseError,
    LLMNetworkError, LLMProviderError, LLMRateLimitError, LLMTimeoutError,
    MissingAPIKeyError,
)
from agent_smith.llm.gemini import GeminiProvider
from agent_smith.llm.models import LLMRequest, LLMResponse, TokenUsage
from agent_smith.llm.provider import LLMProvider

from .controller import decide_next_step
from .models import AgentResult, AgentState, AttemptRecord, FailureReason, VerificationResult
from .prompts import build_prompt
from .verifier import CodeExtractionError, extract_python_code, verify_code


def _failure_reason(error: Exception) -> FailureReason:
    if isinstance(error, MissingAPIKeyError):
        return "missing_api_key"
    if isinstance(error, (LLMConfigurationError, ValidationError)):
        return "configuration_error"
    if isinstance(error, LLMAuthenticationError):
        return "authentication_error"
    if isinstance(error, LLMRateLimitError):
        return "quota_exceeded"
    if isinstance(error, LLMTimeoutError):
        return "timeout"
    if isinstance(error, LLMNetworkError):
        return "network_error"
    if isinstance(error, LLMProviderError):
        return "provider_error"
    return "unexpected_error"


def _failed_observation(message: str) -> VerificationResult:
    return VerificationResult(passed=False, code_extracted=False, errors=[message])


def generate_code(state: AgentState, provider: LLMProvider) -> LLMResponse:
    """Count the attempt before calling the existing Phase 2 provider."""
    AgentState.model_validate(state.model_dump())
    if state.status not in ("pending", "needs_revision"):
        raise ValueError("Generation requires a pending or revision state.")
    if state.llm_calls >= state.max_llm_calls:
        raise ValueError("Generation budget exhausted.")
    request = LLMRequest(prompt=build_prompt(state))
    state.status = "generating"
    state.llm_calls += 1
    state.generated_code = ""
    # An exception leaves the increment visible to the orchestrator.
    return provider.generate(request)


def _aggregate_usage(attempts: list[AttemptRecord]) -> TokenUsage | None:
    if not attempts:
        return None
    totals: dict[str, int | None] = {}
    for field in TokenUsage.model_fields:
        values = [
            getattr(attempt.token_usage, field) if attempt.token_usage else None
            for attempt in attempts
        ]
        totals[field] = sum(values) if all(value is not None for value in values) else None
    return TokenUsage(**totals) if any(value is not None for value in totals.values()) else None


def finalize_result(state: AgentState) -> AgentResult:
    """Validate terminal history and only aggregate complete token measurements."""
    state = AgentState.model_validate(state.model_dump())
    if state.status not in ("unverified", "failed"):
        raise ValueError("Only a terminal state can be finalized.")
    return AgentResult(
        task=state.task, code=state.generated_code, status=state.status,
        stop_reason=state.stop_reason, llm_calls=state.llm_calls,
        total_latency_seconds=state.elapsed_seconds,
        attempts=[attempt.model_copy(deep=True) for attempt in state.attempts],
        token_usage=_aggregate_usage(state.attempts),
    )


def run_agent(
    task: str, provider: LLMProvider | None = None, *,
    max_llm_calls: int = 2, settings: LLMSettings | None = None,
    clock: Callable[[], float] = perf_counter,
) -> AgentResult:
    """Run at most two generations. Injected providers remain caller-owned.

    Invalid task/budget raises ValidationError before any client is constructed.
    Controlled provider failures become failed results. Cancellation propagates.
    """
    state = AgentState(task=task, max_llm_calls=max_llm_calls)
    if provider is not None and settings is not None:
        raise ValueError("Pass an injected provider or Gemini settings, not both.")
    started = clock()
    owned_provider = provider is None
    try:
        if provider is None:
            resolved = settings if settings is not None else AgentSettings().llm
            provider = GeminiProvider(resolved)
        for _ in range(state.max_llm_calls):
            call_started = clock()
            latency = 0.0
            usage = None
            try:
                response = generate_code(state, provider)
                # Validate the injected boundary too, without trusting fake objects.
                try:
                    response = LLMResponse.model_validate(response.model_dump())
                except (ValidationError, AttributeError):
                    raise LLMProviderError("Invalid normalized provider response.") from None
                latency = response.latency_seconds
                if any(value is not None for value in response.usage.model_dump().values()):
                    usage = response.usage
                try:
                    state.generated_code = extract_python_code(response.text)
                except CodeExtractionError as error:
                    observation = _failed_observation(str(error))
                else:
                    observation = verify_code(state)
            except LLMEmptyResponseError:
                latency = max(0.0, clock() - call_started)
                observation = _failed_observation("Extraction error: provider returned no usable text.")
            except Exception as error:
                latency = max(0.0, clock() - call_started)
                state.last_error = _failure_reason(error)
                observation = VerificationResult(
                    passed=False, code_extracted=bool(state.generated_code),
                    errors=[f"Generation stopped: {state.last_error}. No transport retry."],
                )
            state.last_observation = observation
            state.attempts.append(AttemptRecord(
                iteration=state.llm_calls, code=state.generated_code,
                verification=observation, latency_seconds=latency,
                token_usage=usage, error_kind=state.last_error,
            ))
            state.status = "verifying"
            decision = decide_next_step(state)
            state.status = decision.status
            state.stop_reason = decision.stop_reason
            if decision.next_step == "finalize":
                break
    except Exception as error:
        # Configuration/client creation failures occur before any counted call.
        state.status = "failed"
        state.last_error = _failure_reason(error)
        state.stop_reason = state.last_error
        if not state.attempts:
            state.last_observation = _failed_observation(
                f"Agent stopped: {state.last_error}."
            )
    finally:
        if owned_provider and provider is not None:
            try:
                provider.close()
            except Exception:
                if state.status != "failed":
                    state.status = "failed"
                    state.last_error = "client_cleanup_error"
                    state.stop_reason = state.last_error
        state.elapsed_seconds = max(0.0, clock() - started)
    return finalize_result(state)
