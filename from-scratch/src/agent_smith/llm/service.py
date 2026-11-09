"""One-shot generation; no orchestration, fallback or automatic retries."""

from pydantic import ValidationError

from agent_smith.config import AgentSettings, LLMSettings

from .errors import LLMConfigurationError
from .gemini import GeminiProvider
from .models import LLMRequest, LLMResponse


def generate_text(prompt: str, settings: LLMSettings | None = None) -> LLMResponse:
    """Load local settings if omitted, generate once and always close the client."""
    try:
        request = LLMRequest(prompt=prompt)
        resolved = settings if settings is not None else AgentSettings().llm
    except ValidationError:
        raise LLMConfigurationError("Invalid prompt or environment configuration.") from None
    with GeminiProvider(resolved) as provider:
        return provider.generate(request)
