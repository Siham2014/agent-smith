"""Real LangChain formatting with the Google SDK request replaced offline."""

from uuid import uuid4
from unittest.mock import patch

from google.genai import models, types
from pydantic import SecretStr

from agent_smith.config import Settings
from agent_smith.providers.gemini import GeminiProvider


def test_real_langchain_request_options_without_network():
    settings = Settings(_env_file=None, llm_api_key=SecretStr(uuid4().hex))
    response = types.GenerateContentResponse(
        candidates=[types.Candidate(content=types.Content(parts=[types.Part(text="Offline answer")], role="model"), finish_reason="STOP")],
        usage_metadata=types.GenerateContentResponseUsageMetadata(prompt_token_count=4, candidates_token_count=2, total_token_count=6),
    )
    with patch.object(models.Models, "generate_content", return_value=response) as request:
        result = GeminiProvider(settings).ask("Hello")
    request.assert_called_once()
    options = request.call_args.kwargs["config"].http_options
    assert options.retry_options.attempts == 1
    assert options.timeout == 30000
    assert request.call_args.kwargs["model"] == "gemini-3.1-flash-lite"
    assert result.text == "Offline answer"
    assert result.usage.input_tokens == 4
    assert result.finish_reason == "STOP"


import pytest
from google.genai.errors import ClientError
from agent_smith.providers import LLMError


@pytest.mark.parametrize("status,code", [(401, "authentication"), (403, "authentication"), (429, "quota"), (404, "model")])
def test_real_langchain_error_translation_without_network(status, code):
    private = uuid4().hex
    settings = Settings(_env_file=None, llm_api_key=SecretStr(private))
    error = ClientError(status, {"error": {"message": private}})
    with patch.object(models.Models, "generate_content", side_effect=error) as request:
        with pytest.raises(LLMError) as caught:
            GeminiProvider(settings).ask("Hello")
    request.assert_called_once()
    assert caught.value.code == code
    assert private not in str(caught.value)
    assert caught.value.__context__ is None


@pytest.mark.parametrize("raw_usage", [None, types.GenerateContentResponseUsageMetadata(prompt_token_count=4)])
def test_real_langchain_missing_usage_is_not_claimed(raw_usage):
    settings = Settings(_env_file=None, llm_api_key=SecretStr(uuid4().hex))
    response = types.GenerateContentResponse(
        candidates=[types.Candidate(content=types.Content(parts=[types.Part(text="Answer")], role="model"))],
        usage_metadata=raw_usage,
    )
    with patch.object(models.Models, "generate_content", return_value=response):
        result = GeminiProvider(settings).ask("Hello")
    if raw_usage is None:
        assert result.usage is None
    else:
        assert result.usage.input_tokens == 4
        assert result.usage.output_tokens is None
        assert result.usage.total_tokens is None
