import os
from pathlib import Path

from pydantic import SecretStr, ValidationError
import pytest

from agent_smith.config import AgentSettings


@pytest.fixture(autouse=True)
def isolate_settings_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in tuple(os.environ):
        if name.upper().startswith("AGENT_SMITH_"):
            monkeypatch.delenv(name)


def test_settings_have_safe_defaults() -> None:
    settings = AgentSettings(_env_file=None)

    assert settings.log_level == "INFO"
    assert settings.max_iterations == 5
    assert settings.llm.api_key is None


def test_settings_load_nested_values_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENT_SMITH_LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("AGENT_SMITH_MAX_ITERATIONS", "3")
    monkeypatch.setenv("AGENT_SMITH_LLM__PROVIDER", "example")
    monkeypatch.setenv("AGENT_SMITH_LLM__API_KEY", "local-test-secret")

    settings = AgentSettings(_env_file=None)

    assert settings.log_level == "DEBUG"
    assert settings.max_iterations == 3
    assert settings.llm.provider == "example"
    assert settings.llm.api_key == SecretStr("local-test-secret")
    assert "local-test-secret" not in repr(settings.llm)


def test_settings_reject_invalid_log_level(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENT_SMITH_LOG_LEVEL", "TRACE")

    with pytest.raises(ValidationError):
        AgentSettings(_env_file=None)


def test_settings_reject_non_positive_iteration_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENT_SMITH_MAX_ITERATIONS", "0")

    with pytest.raises(ValidationError):
        AgentSettings(_env_file=None)


def test_settings_load_dotenv_with_environment_precedence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(
        "AGENT_SMITH_LOG_LEVEL=DEBUG\n"
        "AGENT_SMITH_MAX_ITERATIONS=7\n"
        "AGENT_SMITH_LLM__MODEL=modèle-test\n"
        "UNRELATED_SETTING=ignored\n",
        encoding="utf-8",
    )
    settings = AgentSettings()
    assert settings.log_level == "DEBUG"
    assert settings.max_iterations == 7
    assert settings.llm.model == "modèle-test"

    monkeypatch.setenv("AGENT_SMITH_MAX_ITERATIONS", "9")
    assert AgentSettings().max_iterations == 9
    assert AgentSettings(max_iterations=2).max_iterations == 2


@pytest.mark.parametrize("value", ["-1", "not-an-integer"])
def test_settings_reject_invalid_iteration_limits(
    value: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENT_SMITH_MAX_ITERATIONS", value)
    with pytest.raises(ValidationError):
        AgentSettings(_env_file=None)
