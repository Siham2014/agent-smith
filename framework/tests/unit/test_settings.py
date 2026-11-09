"""Configuration behavior and validation boundaries."""

import pytest
from pydantic import ValidationError

from agent_smith.config import load_settings


def test_missing_dotenv_uses_defaults():
    settings = load_settings()
    assert settings.environment == "development"
    assert settings.log_level == "INFO"


def test_utf8_dotenv_and_environment_precedence(tmp_path, monkeypatch):
    dotenv = tmp_path / "settings.env"
    dotenv.write_text("# Developpement: \u00e9\u00e8\u00e0\nSMITH_ENVIRONMENT=test\nSMITH_LOG_LEVEL=DEBUG\n", encoding="utf-8")
    monkeypatch.setenv("SMITH_LOG_LEVEL", "ERROR")
    settings = load_settings(dotenv)
    assert settings.environment == "test"
    assert settings.log_level == "ERROR"


@pytest.mark.parametrize("name,value", [
    ("SMITH_ENVIRONMENT", "staging"),
    ("SMITH_LOG_LEVEL", "VERBOSE"),
])
def test_invalid_environment_value_is_rejected(monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    with pytest.raises(ValidationError):
        load_settings(None)


def test_unknown_dotenv_key_is_rejected(tmp_path):
    dotenv = tmp_path / ".env"
    dotenv.write_text("SMITH_LOG_LEVLE=DEBUG\n", encoding="utf-8")
    with pytest.raises(ValidationError):
        load_settings(dotenv)


def test_none_disables_dotenv(tmp_path):
    (tmp_path / ".env").write_text("SMITH_ENVIRONMENT=invalid\n", encoding="utf-8")
    assert load_settings(None).environment == "development"


def test_settings_are_immutable():
    settings = load_settings(None)
    with pytest.raises(ValidationError):
        settings.log_level = "DEBUG"
