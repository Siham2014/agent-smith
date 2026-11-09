"""Gemini integration tested with SDK-shaped fakes and in-memory HTTP only."""

import traceback
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest
from google import genai
from google.genai import errors, types

from agent_smith.config import LLMSettings
from agent_smith.llm import LLMRequest, LLMResponse, generate_text
from agent_smith.llm import gemini, service, smoke
from agent_smith.llm.errors import (
    LLMAuthenticationError, LLMConfigurationError, LLMEmptyResponseError,
    LLMNetworkError, LLMProviderError, LLMRateLimitError, LLMTimeoutError,
    MissingAPIKeyError,
)
from agent_smith.llm.gemini import GeminiProvider

SECRET = "synthetic-secret-never-a-real-key"


def settings(**overrides: object) -> LLMSettings:
    values = dict(provider="google", model="configured-model", api_key=SECRET)
    values.update(overrides)
    return LLMSettings(**values)


def response(with_usage: bool = True) -> types.GenerateContentResponse:
    return types.GenerateContentResponse(
        candidates=[types.Candidate(
            content=types.Content(parts=[
                types.Part(text="private reasoning", thought=True),
                types.Part(text="Hello "), types.Part(text="world"),
            ]),
            finish_reason=types.FinishReason.STOP,
        )],
        model_version="returned-model-version",
        usage_metadata=types.GenerateContentResponseUsageMetadata(
            prompt_token_count=10, candidates_token_count=5, total_token_count=18,
            thoughts_token_count=3, cached_content_token_count=0,
        ) if with_usage else None,
    )


@pytest.fixture
def fake_client(monkeypatch: pytest.MonkeyPatch) -> Mock:
    client = Mock()
    client.models.generate_content.return_value = response()
    monkeypatch.setattr(gemini.genai, "Client", Mock(return_value=client))
    return client


@pytest.mark.parametrize("key", [None, "", "   "])
def test_missing_api_key_never_creates_client(key: str | None, fake_client: Mock) -> None:
    with pytest.raises(MissingAPIKeyError):
        GeminiProvider(settings(api_key=key))
    gemini.genai.Client.assert_not_called()


@pytest.mark.parametrize("overrides", [
    {"provider": None}, {"provider": "other"}, {"model": None},
])
def test_incomplete_configuration_never_creates_client(
    overrides: dict, fake_client: Mock,
) -> None:
    with pytest.raises(LLMConfigurationError):
        GeminiProvider(settings(**overrides))
    gemini.genai.Client.assert_not_called()


@pytest.mark.parametrize("prompt", ["", "   ", None])
def test_invalid_prompt_never_creates_client(prompt: str | None, fake_client: Mock) -> None:
    with pytest.raises(LLMConfigurationError):
        generate_text(prompt, settings())
    gemini.genai.Client.assert_not_called()


def test_mutated_settings_revalidated_before_client(fake_client: Mock) -> None:
    config = settings()
    config.timeout_seconds = -1
    with pytest.raises(LLMConfigurationError):
        GeminiProvider(config)
    gemini.genai.Client.assert_not_called()


def test_valid_request_metadata_and_client_options(
    fake_client: Mock, monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = iter([10.0, 10.25])
    monkeypatch.setattr(gemini, "perf_counter", lambda: next(clock))
    result = generate_text("  Explain Python  ", settings(
        timeout_seconds=2.5, max_output_tokens=64,
    ))
    assert isinstance(result, LLMResponse)
    assert result.text == "Hello world"
    assert result.provider == "google"
    assert result.model == "returned-model-version"
    assert result.finish_reason == "STOP"
    assert result.latency_seconds == 0.25
    assert result.usage.model_dump() == dict(
        input_tokens=10, output_tokens=5, total_tokens=18,
        reasoning_tokens=3, cached_tokens=0,
    )
    kwargs = gemini.genai.Client.call_args.kwargs
    assert kwargs["vertexai"] is False
    assert kwargs["api_key"] == SECRET
    assert kwargs["http_options"].timeout == 2500
    assert kwargs["http_options"].retry_options.attempts == 1
    call = fake_client.models.generate_content
    call.assert_called_once()
    assert call.call_args.kwargs["model"] == "configured-model"
    assert call.call_args.kwargs["contents"] == "Explain Python"
    config = call.call_args.kwargs["config"]
    assert config.max_output_tokens == 64
    assert config.automatic_function_calling.disable is True
    fake_client.close.assert_called_once()


def test_missing_metadata_stays_unknown(fake_client: Mock) -> None:
    fake_client.models.generate_content.return_value = response(False)
    result = generate_text("Hello", settings())
    assert all(value is None for value in result.usage.model_dump().values())


def test_missing_model_version_and_finish_reason(fake_client: Mock) -> None:
    raw = response()
    raw.model_version = None
    raw.candidates[0].finish_reason = None
    fake_client.models.generate_content.return_value = raw
    result = generate_text("Hello", settings())
    assert result.model == "configured-model"
    assert result.finish_reason is None


@pytest.mark.parametrize("raw", [
    types.GenerateContentResponse(),
    types.GenerateContentResponse(candidates=[types.Candidate()]),
    types.GenerateContentResponse(candidates=[types.Candidate(
        content=types.Content(parts=[types.Part(text="   ")]),
    )]),
    types.GenerateContentResponse(candidates=[types.Candidate(
        content=types.Content(parts=[types.Part(text="reason", thought=True)]),
    )]),
])
def test_empty_or_unusable_response(raw: types.GenerateContentResponse, fake_client: Mock) -> None:
    fake_client.models.generate_content.return_value = raw
    with pytest.raises(LLMEmptyResponseError):
        generate_text("Hello", settings())
    fake_client.close.assert_called_once()


@pytest.mark.parametrize("failure,expected", [
    (errors.ClientError(400, {"error": {"details": [{"reason": "API_KEY_INVALID"}]}}), LLMAuthenticationError),
    (errors.ClientError(401, {"error": {"message": SECRET}}), LLMAuthenticationError),
    (errors.ClientError(403, {"error": {"message": SECRET}}), LLMAuthenticationError),
    (errors.ClientError(429, {"error": {"message": SECRET}}), LLMRateLimitError),
    (errors.ClientError(404, {"error": {"message": SECRET}}), LLMProviderError),
    (errors.ClientError(400, {"error": {"message": SECRET}}), LLMProviderError),
    (errors.ServerError(503, {"error": {"message": SECRET}}), LLMProviderError),
    (errors.ServerError(504, {"error": {"message": SECRET}}), LLMTimeoutError),
    (httpx.ReadTimeout(SECRET), LLMTimeoutError),
    (TimeoutError(SECRET), LLMTimeoutError),
    (httpx.ConnectError(SECRET), LLMNetworkError),
    (httpx.RemoteProtocolError(SECRET), LLMNetworkError),
    (ConnectionError(SECRET), LLMNetworkError),
    (RuntimeError(SECRET), LLMProviderError),
])
def test_provider_errors_are_sanitized_without_retries(
    failure: Exception, expected: type[Exception], fake_client: Mock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    fake_client.models.generate_content.side_effect = failure
    with pytest.raises(expected) as caught:
        generate_text("Hello", settings())
    assert SECRET not in str(caught.value)
    assert SECRET not in repr(caught.value)
    assert SECRET not in "".join(traceback.format_exception(
        type(caught.value), caught.value, caught.value.__traceback__,
    ))
    assert SECRET not in caplog.text
    fake_client.models.generate_content.assert_called_once()
    fake_client.close.assert_called_once()


def test_client_initialization_failure_is_sanitized(fake_client: Mock) -> None:
    gemini.genai.Client.side_effect = ValueError(SECRET)
    with pytest.raises(LLMProviderError) as caught:
        generate_text("Hello", settings())
    assert SECRET not in str(caught.value)


def test_close_is_idempotent_and_closed_client_rejects_calls(fake_client: Mock) -> None:
    provider = GeminiProvider(settings())
    provider.close()
    provider.close()
    fake_client.close.assert_called_once()
    with pytest.raises(LLMProviderError):
        provider.generate(LLMRequest(prompt="Hello"))
    fake_client.models.generate_content.assert_not_called()


def test_cleanup_failure_does_not_hide_original_error(fake_client: Mock) -> None:
    fake_client.close.side_effect = RuntimeError(SECRET)
    fake_client.models.generate_content.side_effect = httpx.ReadTimeout(SECRET)
    with pytest.raises(LLMTimeoutError):
        generate_text("Hello", settings())


def test_cleanup_failure_is_sanitized(fake_client: Mock) -> None:
    fake_client.close.side_effect = RuntimeError(SECRET)
    with pytest.raises(LLMProviderError) as caught:
        generate_text("Hello", settings())
    assert SECRET not in str(caught.value)


def test_malformed_usage_maps_to_provider_error(fake_client: Mock) -> None:
    raw = response()
    raw.usage_metadata.prompt_token_count = -1
    fake_client.models.generate_content.return_value = raw
    with pytest.raises(LLMProviderError):
        generate_text("Hello", settings())


def test_load_environment_settings_in_service(
    monkeypatch: pytest.MonkeyPatch, fake_client: Mock,
) -> None:
    monkeypatch.setattr(service, "AgentSettings", lambda: SimpleNamespace(llm=settings()))
    assert generate_text("Hello").text == "Hello world"


def test_invalid_environment_is_sanitized(
    monkeypatch: pytest.MonkeyPatch, fake_client: Mock,
) -> None:
    def invalid_settings() -> object:
        return LLMSettings(timeout_seconds=SECRET)
    monkeypatch.setattr(service, "AgentSettings", invalid_settings)
    with pytest.raises(LLMConfigurationError) as caught:
        generate_text("Hello")
    assert SECRET not in str(caught.value)
    gemini.genai.Client.assert_not_called()


def test_smoke_disabled_by_default(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    generate = Mock()
    monkeypatch.setattr(smoke, "generate_text", generate)
    assert smoke.main([]) == 0
    generate.assert_not_called()
    assert "No request sent" in capsys.readouterr().out


def test_smoke_explicit_activation_with_fake_only(
    monkeypatch: pytest.MonkeyPatch, capsys,
) -> None:
    generate = Mock(return_value=LLMResponse(
        text="A short explanation", provider="google", model="configured-model",
        latency_seconds=0.2,
    ))
    monkeypatch.setattr(smoke, "generate_text", generate)
    assert smoke.main(["--allow-api"]) == 0
    generate.assert_called_once()
    output = capsys.readouterr().out
    assert "A short explanation" in output
    assert "configured-model" in output
    assert "0.200" in output


@pytest.mark.parametrize("failure", [
    LLMRateLimitError("Quota exhausted."),
    LLMProviderError("Model inaccessible."),
])
def test_smoke_reports_failure_with_fake_only(
    failure: Exception, monkeypatch: pytest.MonkeyPatch, capsys,
) -> None:
    monkeypatch.setattr(smoke, "generate_text", Mock(side_effect=failure))
    assert smoke.main(["--allow-api"]) == 1
    assert type(failure).__name__ in capsys.readouterr().out


@pytest.mark.parametrize("status", [200, 429])
def test_real_sdk_contract_over_in_memory_transport(
    status: int, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exercise SDK serialization/retry behavior without any network request."""
    real_client = genai.Client
    calls = []
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if status == 429:
            return httpx.Response(429, json={"error": {
                "code": 429, "status": "RESOURCE_EXHAUSTED", "message": "quota",
            }})
        return httpx.Response(200, json={
            "candidates": [{"content": {"parts": [{"text": "SDK text"}], "role": "model"},
                            "finishReason": "STOP"}],
            "usageMetadata": {"promptTokenCount": 2, "candidatesTokenCount": 3,
                              "totalTokenCount": 5},
        })

    with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
        def factory(**kwargs: object) -> genai.Client:
            kwargs["http_options"].httpx_client = http_client
            return real_client(**kwargs)
        monkeypatch.setattr(gemini.genai, "Client", factory)
        if status == 429:
            with pytest.raises(LLMRateLimitError):
                generate_text("Hello", settings())
        else:
            result = generate_text("Hello", settings())
            assert result.text == "SDK text"
            assert result.usage.total_tokens == 5
        assert len(calls) == 1
        assert "configured-model:generateContent" in str(calls[0].url)
