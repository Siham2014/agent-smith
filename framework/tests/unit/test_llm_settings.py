"""Phase 2 configuration bounds without API access."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from agent_smith.config import Settings, load_settings


def test_llm_settings_defaults():
    settings = load_settings(None)
    assert settings.llm_provider == "google"
    assert settings.llm_model == "gemini-3.1-flash-lite"
    assert settings.llm_api_key is None
    assert settings.llm_timeout_seconds == 30


def test_llm_dotenv_environment_and_secret(tmp_path, monkeypatch):
    private = uuid4().hex
    dotenv = tmp_path / ".env"
    dotenv.write_text(f"SMITH_LLM_API_KEY={private}\nSMITH_LLM_MODEL=custom-model\nSMITH_LLM_TIMEOUT_SECONDS=12\n", encoding="utf-8")
    monkeypatch.setenv("SMITH_LLM_TIMEOUT_SECONDS", "9")
    settings = load_settings(dotenv)
    assert settings.llm_api_key.get_secret_value() == private
    assert settings.llm_model == "custom-model"
    assert settings.llm_timeout_seconds == 9
    assert private not in repr(settings)
    assert private not in settings.model_dump_json()


@pytest.mark.parametrize("field,value", [
    ("llm_provider", "other"), ("llm_model", " "),
    ("llm_timeout_seconds", 0), ("llm_timeout_seconds", 301),
    ("llm_timeout_seconds", float("nan")),
    ("llm_temperature", -1), ("llm_temperature", 3),
    ("llm_temperature", float("inf")),
    ("llm_max_output_tokens", 0), ("llm_max_output_tokens", 65537),
])
def test_invalid_llm_configuration(field, value):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{field: value})
