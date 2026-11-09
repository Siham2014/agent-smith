"""One-shot Gemini Developer API adapter through LangChain."""

from time import perf_counter
from typing import Any

import httpx
import httpx2
from langsmith import tracing_context
from langchain_core.messages import HumanMessage
from langchain_core.exceptions import (
    ModelAuthenticationError, ModelPermissionDeniedError, ModelNotFoundError,
    ModelRateLimitError, ModelTimeoutError, ModelConnectionError,
)
from langchain_google_genai import ChatGoogleGenerativeAI

from agent_smith.config import Settings
from agent_smith.providers.base import LLMError, LLMResponse, TokenUsage


def _safe_error(exc: Exception) -> LLMError:
    # Walk wrapped causes without copying their potentially sensitive messages.
    current: BaseException | None = exc
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        code = getattr(current, "code", None)
        if code is None:
            code = getattr(getattr(current, "response", None), "status_code", None)
        if code in (401, 403) or isinstance(current, (ModelAuthenticationError, ModelPermissionDeniedError)):
            return LLMError("authentication", "Gemini authentication refused. Check the local API key and permissions.")
        if code == 429 or isinstance(current, ModelRateLimitError):
            return LLMError("quota", "Gemini quota or rate limit exceeded. Check your free-tier quota.")
        if code == 404 or isinstance(current, ModelNotFoundError):
            return LLMError("model", "Gemini model unavailable. Check SMITH_LLM_MODEL and account access.")
        if code in (408, 504) or isinstance(current, (TimeoutError, httpx.TimeoutException, httpx2.TimeoutException, ModelTimeoutError)):
            return LLMError("timeout", "Gemini request timed out.")
        if isinstance(current, (ConnectionError, httpx.NetworkError, httpx2.NetworkError, ModelConnectionError)):
            return LLMError("network", "Gemini network connection failed.")
        current = current.__cause__ or current.__context__
    return LLMError("provider", "Gemini request failed. Check the configuration and provider status.")


class GeminiProvider:
    """No tools, orchestration, streaming, fallback or application retries."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        key = settings.llm_api_key
        if key is None or not key.get_secret_value().strip():
            raise LLMError("missing_key", "Set SMITH_LLM_API_KEY in your local environment or dotenv file.")
        failure = None
        try:
            self._chat = ChatGoogleGenerativeAI(
                model=settings.llm_model,
                api_key=key,
                vertexai=False,
                timeout=settings.llm_timeout_seconds,
                temperature=settings.llm_temperature,
                max_tokens=settings.llm_max_output_tokens,
                max_retries=0,
            )
        except Exception as exc:
            failure = _safe_error(exc)
        # Raise outside except so the public exception retains no secret-bearing context.
        if failure is not None:
            raise failure

    def ask(self, prompt: str) -> LLMResponse:
        if not prompt.strip():
            raise ValueError("Prompt must not be blank")
        failure = None
        result = None
        start = perf_counter()
        try:
            with tracing_context(enabled=False):
                message = self._chat.invoke(
                    [HumanMessage(content=prompt)],
                    config={"callbacks": [], "tags": []},
                    # SDK total attempts=1, independently of max_retries semantics.
                    http_options={"retry_options": {"attempts": 1}},
                )
            elapsed = perf_counter() - start
            content = message.content
            text = content if isinstance(content, str) else "".join(
                block if isinstance(block, str) else block.get("text", "")
                for block in content
                if isinstance(block, str) or (isinstance(block, dict) and block.get("type") == "text")
            )
            if not text.strip():
                failure = LLMError("empty_response", "Gemini returned no usable text (possibly blocked or truncated).")
            else:
                raw: dict[str, Any] | None = message.usage_metadata
                # LangChain substitutes missing provider counters with zero.
                # Conservatively expose zero as unknown rather than claiming a
                # measured zero we cannot distinguish from an absent counter.
                usage = TokenUsage(**{
                    k: raw[k] for k in ("input_tokens", "output_tokens", "total_tokens")
                    if k in raw and raw[k] > 0
                }) if raw else None
                finish = message.response_metadata.get("finish_reason")
                result = LLMResponse(
                    text=text, provider="google", model=self._settings.llm_model,
                    usage=usage, latency_seconds=elapsed,
                    finish_reason=str(finish) if finish is not None else None,
                )
        except Exception as exc:
            failure = _safe_error(exc)
        if failure is not None:
            raise failure
        assert result is not None
        return result
