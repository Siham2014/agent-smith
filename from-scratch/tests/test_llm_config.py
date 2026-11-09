"""Phase 2 settings tests; all credentials are synthetic."""

import os

import pytest
from pydantic import ValidationError

from agent_smith.config import AgentSettings, LLMSettings


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in tuple(os.environ):
        if name.upper().startswith("AGENT_SMITH_"):
            monkeypatch.delenv(name)


def test_gemini_settings_load_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for suffix, value in {
        "PROVIDER": "google", "MODEL": "configured-model",
        "API_KEY": "synthetic-secret", "TIMEOUT_SECONDS": "12.5",
        "MAX_OUTPUT_TOKENS": "256",
    }.items():
        monkeypatch.setenv("AGENT_SMITH_LLM__" + suffix, value)
    settings = AgentSettings(_env_file=None).llm
    assert settings.provider == "google"
    assert settings.model == "configured-model"
    assert settings.timeout_seconds == 12.5
    assert settings.max_output_tokens == 256
    assert settings.api_key.get_secret_value() == "synthetic-secret"
    assert "synthetic-secret" not in repr(settings)


@pytest.mark.parametrize("kwargs", [
    {"timeout_seconds": 0}, {"timeout_seconds": -1},
    {"timeout_seconds": float("nan")}, {"timeout_seconds": float("inf")},
    {"timeout_seconds": 601}, {"timeout_seconds": "invalid"},
    {"max_output_tokens": 0}, {"max_output_tokens": -1},
    {"max_output_tokens": 1.5}, {"model": " "}, {"provider": " "},
])
def test_invalid_llm_settings(kwargs: dict) -> None:
    with pytest.raises(ValidationError):
        LLMSettings(**kwargs)
