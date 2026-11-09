"""Structural interface: later providers need only implement these methods."""

from typing import Protocol

from .models import LLMRequest, LLMResponse


class LLMProvider(Protocol):
    def generate(self, request: LLMRequest) -> LLMResponse:
        ...

    def close(self) -> None:
        ...
