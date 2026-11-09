"""Provider-independent errors. Never include raw SDK messages or credentials."""


class LLMError(Exception):
    """Base error exposed by the LLM integration."""


class LLMConfigurationError(LLMError):
    """Invalid local configuration or request."""


class MissingAPIKeyError(LLMConfigurationError):
    """No non-empty credential was supplied."""


class LLMAuthenticationError(LLMError):
    """The provider rejected authentication or permissions."""


class LLMRateLimitError(LLMError):
    """The free quota or rate limit was reached."""


class LLMTimeoutError(LLMError):
    """The request timed out."""


class LLMNetworkError(LLMError):
    """The transport could not complete the request."""


class LLMEmptyResponseError(LLMError):
    """No usable text was returned."""


class LLMProviderError(LLMError):
    """Other provider, model access, parsing or client lifecycle failure."""
