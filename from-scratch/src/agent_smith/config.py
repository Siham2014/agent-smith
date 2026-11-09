"""Application configuration models."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMSettings(BaseModel):
    """Provider configuration; completeness is checked before creating a client."""

    model_config = ConfigDict(str_strip_whitespace=True, hide_input_in_errors=True)

    provider: str | None = Field(default=None, min_length=1)
    model: str | None = Field(default=None, min_length=1)
    api_key: SecretStr | None = None
    timeout_seconds: float = Field(default=30, ge=0.001, le=600, allow_inf_nan=False)
    max_output_tokens: int | None = Field(default=None, gt=0)


class AgentSettings(BaseSettings):
    """Settings loaded from the environment and an optional local .env file."""

    model_config = SettingsConfigDict(
        env_prefix="AGENT_SMITH_",
        env_nested_delimiter="__",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    max_iterations: int = Field(default=5, ge=1)
    llm: LLMSettings = Field(default_factory=LLMSettings)
