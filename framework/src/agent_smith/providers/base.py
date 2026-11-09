"""Application contract independent of LangChain message classes."""

from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field


class TokenUsage(BaseModel):
    model_config = ConfigDict(frozen=True)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)


class LLMResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    text: str
    provider: str
    model: str
    usage: TokenUsage | None = None
    latency_seconds: float = Field(ge=0)
    finish_reason: str | None = None


ErrorCode = Literal["missing_key", "authentication", "quota", "timeout", "network", "model", "empty_response", "provider"]


class LLMError(Exception):
    """A safe public error; never includes the provider exception text."""

    def __init__(self, code: ErrorCode, message: str) -> None:
        self.code = code
        super().__init__(message)


class ChatProvider(Protocol):
    def ask(self, prompt: str) -> LLMResponse:
        """Send one user message and return an application response."""
        ...
