"""Run the real compiled graph with scripted responses, never Gemini."""

from langsmith import tracing_context

from agent_smith.agent.graph import GRAPH_RECURSION_LIMIT, build_graph, initial_state
from agent_smith.providers.base import LLMResponse


class ScriptedProvider:
    def __init__(self, responses: list[str]) -> None:
        self.responses = iter(responses)
        self.calls = 0

    def ask(self, prompt: str) -> LLMResponse:
        self.calls += 1
        return LLMResponse(text=next(self.responses), provider="offline-demo", model="scripted",
                           latency_seconds=0.0)  # Synthetic fixture, not a live latency.


def main() -> None:
    scenarios = {
        "valid_first_proposal": ["def maximum(a, b, c):\n    return max(a, b, c)"],
        "error_then_correction": ["def maximum(:", "def maximum(a, b, c):\n    return max(a, b, c)"],
        "two_errors": ["def maximum(:", "def maximum(a, b, c)"],
    }
    for name, responses in scenarios.items():
        provider = ScriptedProvider(responses)
        graph = build_graph(provider)
        with tracing_context(enabled=False):
            updates = list(graph.stream(initial_state("Write maximum of three numbers"),
                config={"recursion_limit": GRAPH_RECURSION_LIMIT, "callbacks": []}, stream_mode="updates"))
        path = [node for update in updates for node in update]
        result = updates[-1]["finalize"]["result"]
        print(name)
        print("Path: " + " -> ".join(path))
        print(f"Status: {result.status}; stop: {result.stop_reason}; calls: {provider.calls}")
        print(f"Synthetic fixture latency: {result.total_latency_seconds:.3f}s")
        print()


if __name__ == "__main__":
    main()
