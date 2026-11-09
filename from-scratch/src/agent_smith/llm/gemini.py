"""Synchronous Gemini Developer API adapter; one attempt, no tool execution."""

from time import perf_counter
from types import TracebackType

import httpx
from google import genai
from google.genai import errors, types
from pydantic import ValidationError

from agent_smith.config import LLMSettings

from .errors import (
    LLMAuthenticationError, LLMConfigurationError, LLMEmptyResponseError,
    LLMError, LLMNetworkError, LLMProviderError, LLMRateLimitError,
    LLMTimeoutError, MissingAPIKeyError,
)
from .models import LLMRequest, LLMResponse, TokenUsage


def _translate_error(error: Exception) -> LLMError:
    """Only inspect types/status codes; never interpolate untrusted messages."""
    if isinstance(error, errors.APIError):
        details = error.details if isinstance(error.details, dict) else {}
        nested = details.get("error", details)
        items = nested.get("details", []) if isinstance(nested, dict) else []
        items = items if isinstance(items, list) else []
        invalid_key = any(
            isinstance(item, dict) and item.get("reason") == "API_KEY_INVALID"
            for item in items
        )
        if error.code in (401, 403) or invalid_key:
            return LLMAuthenticationError("Gemini authentication or permission denied.")
        if error.code == 429:
            return LLMRateLimitError("Gemini quota or rate limit reached; no retry made.")
        if error.code in (408, 504):
            return LLMTimeoutError("Gemini request timed out.")
        if error.code == 404:
            return LLMProviderError(
                "Gemini model unavailable or inaccessible; verify the configured model and account access."
            )
        return LLMProviderError("Gemini rejected the request or is unavailable.")
    if isinstance(error, (httpx.TimeoutException, TimeoutError)):
        return LLMTimeoutError("Gemini request timed out.")
    if isinstance(error, (httpx.TransportError, ConnectionError)):
        return LLMNetworkError("Gemini network request failed.")
    return LLMProviderError("Gemini client or response processing failed.")


class GeminiProvider:
    """Owns its SDK client. Use a context manager or explicitly call close()."""

    def __init__(self, settings: LLMSettings) -> None:
        # Revalidate even if a caller mutated an existing Pydantic instance.
        try:
            self._settings = LLMSettings.model_validate(settings.model_dump())
        except (ValidationError, AttributeError):
            raise LLMConfigurationError("Invalid LLM settings.") from None
        if self._settings.provider != "google":
            raise LLMConfigurationError("This phase supports provider 'google' only.")
        if not self._settings.model:
            raise LLMConfigurationError("An explicit Gemini model identifier is required.")
        key = self._settings.api_key
        if key is None or not key.get_secret_value().strip():
            raise MissingAPIKeyError("Set AGENT_SMITH_LLM__API_KEY locally before calling Gemini.")
        self._closed = False
        try:
            self._client = genai.Client(
                api_key=key.get_secret_value(),
                vertexai=False,
                http_options=types.HttpOptions(
                    timeout=max(1, int(self._settings.timeout_seconds * 1000)),
                    retry_options=types.HttpRetryOptions(attempts=1),
                ),
            )
        except Exception as error:
            raise _translate_error(error) from None

    def generate(self, request: LLMRequest) -> LLMResponse:
        if self._closed:
            raise LLMProviderError("Gemini client is closed.")
        try:
            request = LLMRequest.model_validate(request.model_dump())
        except (ValidationError, AttributeError):
            raise LLMConfigurationError("A non-empty text prompt is required.") from None
        started = perf_counter()
        try:
            raw = self._client.models.generate_content(
                model=self._settings.model,
                contents=request.prompt,
                config=types.GenerateContentConfig(
                    max_output_tokens=self._settings.max_output_tokens,
                    automatic_function_calling=types.AutomaticFunctionCallingConfig(
                        disable=True,
                    ),
                ),
            )
            latency = perf_counter() - started
            candidates = raw.candidates or []
            candidate = candidates[0] if candidates else None
            parts = candidate.content.parts if candidate and candidate.content else []
            # Do not expose internal thinking or execute function/code parts.
            text = "".join(
                part.text for part in (parts or [])
                if part.text and not part.thought
            )
            if not text.strip():
                raise LLMEmptyResponseError("Gemini returned no usable text (possibly blocked).")
            metadata = raw.usage_metadata
            usage = TokenUsage(
                input_tokens=metadata.prompt_token_count if metadata else None,
                output_tokens=metadata.candidates_token_count if metadata else None,
                total_tokens=metadata.total_token_count if metadata else None,
                reasoning_tokens=metadata.thoughts_token_count if metadata else None,
                cached_tokens=metadata.cached_content_token_count if metadata else None,
            )
            reason = candidate.finish_reason
            return LLMResponse(
                text=text,
                provider="google",
                model=raw.model_version or self._settings.model,
                usage=usage,
                latency_seconds=latency,
                finish_reason=reason.value if reason else None,
            )
        except LLMError:
            raise
        except Exception as error:
            raise _translate_error(error) from None

    def close(self) -> None:
        if not self._closed:
            try:
                self._client.close()
            except Exception:
                raise LLMProviderError("Gemini client cleanup failed.") from None
            finally:
                self._closed = True

    def __enter__(self) -> "GeminiProvider":
        return self

    def __exit__(
        self, exc_type: type[BaseException] | None,
        exc: BaseException | None, traceback: TracebackType | None,
    ) -> None:
        try:
            self.close()
        except LLMError:
            if exc is None:
                raise
