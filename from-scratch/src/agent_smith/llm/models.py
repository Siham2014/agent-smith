"""Small request/response contract independent of Google's SDK."""

from pydantic import BaseModel, ConfigDict, Field


class LLMRequest(BaseModel):
    model_config = ConfigDict(
        str_strip_whitespace=True, hide_input_in_errors=True, frozen=True,
    )
    prompt: str = Field(min_length=1, repr=False)


class TokenUsage(BaseModel):
    """None means unknown; zero means the API explicitly reported zero."""

    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)
    reasoning_tokens: int | None = Field(default=None, ge=0)
    cached_tokens: int | None = Field(default=None, ge=0)


class LLMResponse(BaseModel):
    text: str
    provider: str
    model: str
    usage: TokenUsage = Field(default_factory=TokenUsage)
    latency_seconds: float = Field(ge=0, allow_inf_nan=False)
    finish_reason: str | None = None
