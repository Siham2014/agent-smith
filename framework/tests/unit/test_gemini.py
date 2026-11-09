"""Offline tests of the LangChain adapter using generated dummy credentials."""

from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4
import traceback

import httpx
import httpx2
import pytest
from google.genai.errors import ClientError, ServerError
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.exceptions import ModelRateLimitError
from pydantic import SecretStr

from agent_smith.config import Settings
from agent_smith.providers import LLMError
from agent_smith.providers import gemini


@pytest.fixture
def credential():
    return SecretStr(uuid4().hex)


@pytest.fixture
def configured(credential):
    return Settings(_env_file=None, llm_api_key=credential)


@pytest.fixture
def fake_chat(monkeypatch):
    chat = Mock()
    chat.invoke.return_value = AIMessage(content="A Python IndexError means an index is out of range.")
    factory = Mock(return_value=chat)
    monkeypatch.setattr(gemini, "ChatGoogleGenerativeAI", factory)
    return factory, chat


def test_missing_key_does_not_construct_client(fake_chat):
    with pytest.raises(LLMError) as caught:
        gemini.GeminiProvider(Settings(_env_file=None))
    assert caught.value.code == "missing_key"
    fake_chat[0].assert_not_called()


def test_blank_key_is_missing(fake_chat):
    with pytest.raises(LLMError, match="SMITH_LLM_API_KEY"):
        gemini.GeminiProvider(Settings(_env_file=None, llm_api_key=SecretStr("  ")))
    fake_chat[0].assert_not_called()


def test_initialization(configured, fake_chat):
    gemini.GeminiProvider(configured)
    options = fake_chat[0].call_args.kwargs
    assert options == dict(model="gemini-3.1-flash-lite", api_key=configured.llm_api_key,
        vertexai=False, timeout=30, temperature=1.0, max_tokens=1024, max_retries=0)


def test_send_and_normalize(configured, fake_chat, monkeypatch):
    fake_chat[1].invoke.return_value = AIMessage(content="Answer", usage_metadata={
        "input_tokens": 7, "output_tokens": 9, "total_tokens": 16}, response_metadata={"finish_reason": "STOP"})
    ticks = iter([10.0, 10.25])
    monkeypatch.setattr(gemini, "perf_counter", lambda: next(ticks))
    response = gemini.GeminiProvider(configured).ask("Explain IndexError")
    args, kwargs = fake_chat[1].invoke.call_args
    assert isinstance(args[0][0], HumanMessage)
    assert args[0][0].content == "Explain IndexError"
    assert kwargs["http_options"]["retry_options"]["attempts"] == 1
    assert response.text == "Answer"
    assert response.provider == "google"
    assert response.model == configured.llm_model
    assert response.usage.input_tokens == 7
    assert response.usage.output_tokens == 9
    assert response.usage.total_tokens == 16
    assert response.latency_seconds == 0.25
    assert response.finish_reason == "STOP"
    fake_chat[1].invoke.assert_called_once()


def test_absent_metadata_is_not_invented(configured, fake_chat):
    response = gemini.GeminiProvider(configured).ask("Hello")
    assert response.usage is None
    assert response.finish_reason is None


def test_content_blocks_keep_only_text(configured, fake_chat):
    fake_chat[1].invoke.return_value = AIMessage(content=[
        {"type": "text", "text": "First "}, {"type": "thinking", "thinking": "private"},
        {"type": "text", "text": "second"}])
    assert gemini.GeminiProvider(configured).ask("Hello").text == "First second"


@pytest.mark.parametrize("content", ["", "  ", [], [{"type": "thinking", "thinking": "hidden"}]])
def test_empty_response(configured, fake_chat, content):
    fake_chat[1].invoke.return_value = AIMessage(content=content)
    with pytest.raises(LLMError) as caught:
        gemini.GeminiProvider(configured).ask("Hello")
    assert caught.value.code == "empty_response"


@pytest.mark.parametrize("kind,code", [
    (401, "authentication"), (403, "authentication"), (429, "quota"),
    (404, "model"), (408, "timeout"), (504, "timeout"),
    (500, "provider"), (400, "provider"),
    ("timeout", "timeout"), ("network", "network"),
    ("timeout2", "timeout"), ("network2", "network"),
    ("wrapped", "quota"), ("unknown", "provider"),
])
def test_safe_provider_errors(configured, fake_chat, credential, kind, code):
    private = credential.get_secret_value()
    if isinstance(kind, int):
        cls = ServerError if kind >= 500 else ClientError
        exc = cls(kind, {"error": {"message": private}})
    elif kind == "timeout":
        exc = httpx.ReadTimeout(private)
    elif kind == "network":
        exc = httpx.ConnectError(private)
    elif kind == "timeout2":
        exc = httpx2.ReadTimeout(private)
    elif kind == "network2":
        exc = httpx2.ConnectError(private)
    elif kind == "wrapped":
        exc = ModelRateLimitError(private)
    else:
        exc = RuntimeError(private)
    fake_chat[1].invoke.side_effect = exc
    with pytest.raises(LLMError) as caught:
        gemini.GeminiProvider(configured).ask("Hello")
    assert caught.value.code == code
    assert private not in "".join(traceback.format_exception(type(caught.value), caught.value, caught.value.__traceback__))
    assert caught.value.__context__ is None
    assert caught.value.__cause__ is None
    fake_chat[1].invoke.assert_called_once()


def test_initialization_failure_is_safe(configured, fake_chat, credential):
    fake_chat[0].side_effect = RuntimeError(credential.get_secret_value())
    with pytest.raises(LLMError) as caught:
        gemini.GeminiProvider(configured)
    assert caught.value.code == "provider"
    assert credential.get_secret_value() not in str(caught.value)
    assert caught.value.__context__ is None


def test_blank_prompt_never_invokes(configured, fake_chat):
    provider = gemini.GeminiProvider(configured)
    with pytest.raises(ValueError):
        provider.ask("  ")
    fake_chat[1].invoke.assert_not_called()


def test_partial_usage_does_not_invent_counts(configured, fake_chat):
    fake_chat[1].invoke.return_value = SimpleNamespace(
        content="Answer", usage_metadata={"input_tokens": 7}, response_metadata={})
    result = gemini.GeminiProvider(configured).ask("Hello")
    assert result.usage.input_tokens == 7
    assert result.usage.output_tokens is None
    assert result.usage.total_tokens is None


def test_zero_counters_are_conservatively_unknown(configured, fake_chat):
    fake_chat[1].invoke.return_value = AIMessage(content="Answer", usage_metadata={
        "input_tokens": 4, "output_tokens": 0, "total_tokens": 0})
    result = gemini.GeminiProvider(configured).ask("Hello")
    assert result.usage.input_tokens == 4
    assert result.usage.output_tokens is None
    assert result.usage.total_tokens is None
