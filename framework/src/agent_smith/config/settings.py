"""Validated startup settings; loading never executes generated code."""

from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment variables override the optional UTF-8 dotenv file.

    Extra dotenv entries are rejected to catch misspelled settings. Unrelated
    operating-system environment variables are ignored by BaseSettings.
    """

    model_config = SettingsConfigDict(
        env_prefix="SMITH_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="forbid",
        frozen=True,
        hide_input_in_errors=True,
    )

    environment: Literal["development", "test", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    llm_provider: Literal["google"] = "google"
    llm_model: str = Field(default="gemini-3.1-flash-lite", min_length=1)
    llm_api_key: SecretStr | None = Field(default=None, repr=False, exclude=True)
    llm_timeout_seconds: float = Field(default=30, gt=0, le=300, allow_inf_nan=False)
    llm_temperature: float = Field(default=1.0, ge=0, le=2, allow_inf_nan=False)
    llm_max_output_tokens: int = Field(default=1024, gt=0, le=65536)

    @field_validator("llm_model")
    @classmethod
    def nonblank_model(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Model identifier must not be blank")
        return value.strip()


def load_settings(env_file: str | Path | None = ".env") -> Settings:
    """Read a file relative to the working directory; None disables dotenv."""
    return Settings(_env_file=env_file)
