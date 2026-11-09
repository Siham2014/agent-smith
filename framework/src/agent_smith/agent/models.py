"""Validated application boundaries, independent of the graph runtime."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from agent_smith.providers.base import TokenUsage

Status = Literal["pending", "needs_revision", "unverified", "failed"]
StopReason = Literal[
    "syntax_passed_functionality_unverified", "budget_exhausted",
    "provider_missing_key", "provider_authentication", "provider_quota",
    "provider_timeout", "provider_network", "provider_model", "provider_error",
    "configuration_invalid",
]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)


class VerificationResult(Contract):
    passed: bool
    level: Literal["syntax", "structure"]
    errors: list[str] = Field(default_factory=list)
    code_extracted: bool

    @model_validator(mode="after")
    def consistent_verification(self) -> "VerificationResult":
        if self.passed and (self.errors or not self.code_extracted):
            raise ValueError("A passing verification requires extracted code and no errors")
        if not self.passed and not self.errors:
            raise ValueError("A failing verification requires an observation")
        return self


class AttemptRecord(Contract):
    iteration: int = Field(ge=1, le=2, strict=True)
    code: str
    verification: VerificationResult
    latency_seconds: float = Field(ge=0, allow_inf_nan=False)
    token_usage: TokenUsage | None = None


class AgentState(Contract):
    task: str = Field(min_length=1)
    generated_code: str = ""
    llm_calls: int = Field(default=0, ge=0, le=2, strict=True)
    max_llm_calls: int = Field(default=2, ge=1, le=2, strict=True)
    attempts: list[AttemptRecord] = Field(default_factory=list)
    status: Status = "pending"
    stop_reason: StopReason | None = None
    last_observation: str = ""
    elapsed_seconds: float = Field(default=0, ge=0, allow_inf_nan=False)

    @field_validator("task")
    @classmethod
    def nonblank_task(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Task must not be blank")
        return value

    @model_validator(mode="after")
    def consistent_state(self) -> "AgentState":
        if self.llm_calls > self.max_llm_calls or len(self.attempts) > self.llm_calls:
            raise ValueError("Calls/history must respect the task budget")
        if [a.iteration for a in self.attempts] != list(range(1, len(self.attempts) + 1)):
            raise ValueError("Attempt history must be sequential")
        if self.status in ("failed", "unverified"):
            if self.stop_reason is None or len(self.attempts) != self.llm_calls:
                raise ValueError("A terminal state needs a stop reason and complete history")
        elif self.stop_reason is not None:
            raise ValueError("A nonterminal state must not have a stop reason")
        if self.status == "unverified":
            if self.stop_reason != "syntax_passed_functionality_unverified" or not self.attempts or not self.attempts[-1].verification.passed:
                raise ValueError("Unverified means syntax passed, not functional success")
        if self.status == "failed" and self.stop_reason == "syntax_passed_functionality_unverified":
            raise ValueError("Failed state cannot claim syntax passed")
        if self.stop_reason == "budget_exhausted":
            if self.llm_calls != self.max_llm_calls or not self.attempts or self.attempts[-1].verification.passed:
                raise ValueError("Budget exhaustion requires a failed last attempt and exhausted calls")
        if self.status == "needs_revision":
            if not self.attempts or self.attempts[-1].verification.passed or self.llm_calls >= self.max_llm_calls:
                raise ValueError("Revision requires a failed attempt and available budget")
        return self


class AgentResult(Contract):
    task: str = Field(min_length=1)
    code: str
    status: Literal["unverified", "failed"]
    stop_reason: StopReason
    llm_calls: int = Field(ge=0, le=2, strict=True)
    total_latency_seconds: float = Field(ge=0, allow_inf_nan=False)
    attempts: list[AttemptRecord] = Field(default_factory=list)
    token_usage: TokenUsage | None = None

    @model_validator(mode="after")
    def consistent_result(self) -> "AgentResult":
        AgentState(
            task=self.task, generated_code=self.code, status=self.status,
            stop_reason=self.stop_reason, llm_calls=self.llm_calls,
            max_llm_calls=max(1, self.llm_calls), attempts=self.attempts,
        )
        if self.total_latency_seconds != sum(a.latency_seconds for a in self.attempts):
            raise ValueError("Total latency must equal recorded call latencies")
        return self
