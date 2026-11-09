"""Deterministic offline demonstration. Does not read .env or create a client."""

from agent_smith.llm.models import LLMRequest, LLMResponse, TokenUsage

from .runner import run_agent


class DemoProvider:
    """Two fixed outputs to illustrate revision, not a model-quality test."""

    def __init__(self) -> None:
        self.calls = 0

    def generate(self, request: LLMRequest) -> LLMResponse:
        self.calls += 1
        text = (
            "def maximum(a, b, c)\n    return max(a, b, c)"
            if self.calls == 1
            else "def maximum(a, b, c):\n    return max(a, b, c)"
        )
        return LLMResponse(
            text=text, provider="offline-demo", model="fixed-responses",
            latency_seconds=0.0, usage=TokenUsage(),
        )

    def close(self) -> None:
        pass


def main() -> None:
    result = run_agent(
        "Write a Python function that returns the maximum of three numbers.",
        provider=DemoProvider(),
    )
    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
