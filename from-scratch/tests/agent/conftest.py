"""Injectable, deterministic provider with no network or configuration loading."""

import pytest

from agent_smith.llm.models import LLMRequest, LLMResponse, TokenUsage


class FakeProvider:
    def __init__(self, outputs: list) -> None:
        self.outputs = list(outputs)
        self.requests: list[LLMRequest] = []
        self.close_calls = 0

    @property
    def calls(self) -> int:
        return len(self.requests)

    def generate(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        output = self.outputs.pop(0)
        if isinstance(output, BaseException):
            raise output
        if isinstance(output, LLMResponse):
            return output
        return LLMResponse(
            text=output, provider="fake", model="offline",
            latency_seconds=0.1,
            usage=TokenUsage(input_tokens=2, output_tokens=3, total_tokens=5),
        )

    def close(self) -> None:
        self.close_calls += 1


@pytest.fixture
def provider_factory():
    return lambda *outputs: FakeProvider(list(outputs))
