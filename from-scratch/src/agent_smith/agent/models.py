"""Validated contracts for bounded generation and static revision."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from agent_smith.llm.models import TokenUsage

AgentStatus = Literal[
    "pending", "generating", "verifying", "needs_revision", "unverified", "failed",
]
FailureReason = Literal[
    "configuration_error", "missing_api_key", "authentication_error",
    "quota_exceeded", "timeout", "network_error", "provider_error",
    "unexpected_error", "client_cleanup_error",
]
StopReason = Literal[
    "syntax_passed_functionality_unverified", "budget_exhausted",
    "configuration_error", "missing_api_key", "authentication_error",
    "quota_exceeded", "timeout", "network_error", "provider_error",
    "unexpected_error", "client_cleanup_error",
]


class AgentModel(BaseModel):
    model_config = ConfigDict(hide_input_in_errors=True, extra="forbid")


class VerificationResult(AgentModel):
    passed: bool
    level: Literal["syntax", "structure"] = "syntax"
    errors: list[str] = Field(default_factory=list, max_length=5)
    code_extracted: bool

    @model_validator(mode="after")
    def consistent_outcome(self) -> "VerificationResult":
        if any(not error.strip() or len(error) > 240 for error in self.errors):
            raise ValueError("Verification messages must be bounded.")
        if self.passed and (not self.code_extracted or self.errors):
            raise ValueError("A passing check needs extracted code and no errors.")
        if not self.passed and not self.errors:
            raise ValueError("A failed check needs an observation.")
        return self


class AttemptRecord(AgentModel):
    iteration: int = Field(ge=1, le=2, strict=True)
    code: str = Field(repr=False)
    verification: VerificationResult
    latency_seconds: float = Field(ge=0, allow_inf_nan=False)
    token_usage: TokenUsage | None = None
    error_kind: FailureReason | None = None

    @model_validator(mode="after")
    def consistent_attempt(self) -> "AttemptRecord":
        if self.verification.code_extracted != bool(self.code.strip()):
            raise ValueError("Code and extraction status must agree.")
        if self.error_kind and self.verification.passed:
            raise ValueError("A failed call cannot pass verification.")
        return self


def _check_trace(calls: int, attempts: list[AttemptRecord]) -> None:
    if len(attempts) > calls:
        raise ValueError("History exceeds the number of counted calls.")
    if [attempt.iteration for attempt in attempts] != list(range(1, len(attempts) + 1)):
        raise ValueError("Attempt history must be ordered and consecutive.")


def _check_terminal(
    status: AgentStatus, reason: StopReason | None,
    code: str, calls: int, attempts: list[AttemptRecord],
) -> None:
    if len(attempts) != calls:
        raise ValueError("A final result must record every counted call.")
    if attempts and code != attempts[-1].code:
        raise ValueError("Final code must match the last attempt.")
    if status == "unverified":
        if reason != "syntax_passed_functionality_unverified":
            raise ValueError("Unverified status requires the syntax-only stop reason.")
        if not attempts or not attempts[-1].verification.passed:
            raise ValueError("Unverified status requires a passing static check.")
        if attempts[-1].verification.level != "syntax":
            raise ValueError("This phase's terminal check is syntax only.")
    elif status == "failed":
        if reason is None or reason == "syntax_passed_functionality_unverified":
            raise ValueError("Failed status requires a failure stop reason.")
        if reason == "budget_exhausted" and (
            not attempts or attempts[-1].verification.passed
        ):
            raise ValueError("Budget exhaustion needs a failed static check.")


class AgentState(AgentModel):
    """Mutable internal state, validated at creation and transition boundaries."""

    task: str = Field(min_length=1, repr=False)
    generated_code: str = Field(default="", repr=False)
    llm_calls: int = Field(default=0, ge=0, le=2, strict=True)
    max_llm_calls: int = Field(default=2, ge=1, le=2, strict=True)
    attempts: list[AttemptRecord] = Field(default_factory=list, max_length=2)
    status: AgentStatus = "pending"
    stop_reason: StopReason | None = None
    last_observation: VerificationResult | None = None
    elapsed_seconds: float = Field(default=0, ge=0, allow_inf_nan=False)
    last_error: FailureReason | None = None

    @model_validator(mode="after")
    def consistent_state(self) -> "AgentState":
        if not self.task.strip():
            raise ValueError("Task must contain non-whitespace text.")
        if self.llm_calls > self.max_llm_calls:
            raise ValueError("Call count exceeds the configured budget.")
        _check_trace(self.llm_calls, self.attempts)
        gap = self.llm_calls - len(self.attempts)
        if gap not in (0, 1) or (gap and self.status != "generating"):
            raise ValueError("Only one in-flight generation may lack a history entry.")
        if self.status == "pending" and (self.llm_calls or self.attempts):
            raise ValueError("Pending state cannot have previous calls.")
        if self.status in ("verifying", "needs_revision") and not self.attempts:
            raise ValueError("Verification and revision need a recorded attempt.")
        if self.attempts and self.last_observation != self.attempts[-1].verification:
            raise ValueError("Last observation must match the last attempt.")
        if self.status != "generating" and self.attempts and (
            self.generated_code != self.attempts[-1].code
        ):
            raise ValueError("Current code must match the last completed attempt.")
        if self.status == "needs_revision" and (
            self.llm_calls >= self.max_llm_calls
            or self.last_error is not None
            or self.last_observation is None
            or self.last_observation.passed
        ):
            raise ValueError("Revision needs a failed check and remaining budget.")
        if self.status in ("unverified", "failed"):
            _check_terminal(
                self.status, self.stop_reason, self.generated_code,
                self.llm_calls, self.attempts,
            )
            if self.stop_reason == "budget_exhausted" and self.llm_calls < self.max_llm_calls:
                raise ValueError("Budget is not exhausted.")
        elif self.stop_reason is not None:
            raise ValueError("Only terminal states have a stop reason.")
        return self


class Decision(AgentModel):
    next_step: Literal["generate", "retry", "finalize"]
    status: AgentStatus
    stop_reason: StopReason | None = None


class AgentResult(AgentModel):
    task: str = Field(min_length=1, repr=False)
    code: str = Field(repr=False)
    status: Literal["unverified", "failed"]
    stop_reason: StopReason
    llm_calls: int = Field(ge=0, le=2, strict=True)
    total_latency_seconds: float = Field(ge=0, allow_inf_nan=False)
    attempts: list[AttemptRecord] = Field(default_factory=list, max_length=2)
    token_usage: TokenUsage | None = None

    @model_validator(mode="after")
    def consistent_result(self) -> "AgentResult":
        if not self.task.strip():
            raise ValueError("Task must contain non-whitespace text.")
        _check_trace(self.llm_calls, self.attempts)
        _check_terminal(
            self.status, self.stop_reason, self.code, self.llm_calls, self.attempts,
        )
        return self
