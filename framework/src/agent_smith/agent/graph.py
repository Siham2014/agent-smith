"""A real StateGraph; business budget and recursion limit are independent."""

from time import perf_counter

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langsmith import tracing_context

from agent_smith.agent.models import AgentResult, AgentState
from agent_smith.agent.nodes import GraphState, decide_next_step, finalize_node, generate_node, verify_node
from agent_smith.providers.base import ChatProvider

# At most generate, verify, generate, verify, finalize (5 supersteps).
# Allow one additional scheduler step before END; not a substitute for the budget.
GRAPH_RECURSION_LIMIT = 8


def build_graph(provider: ChatProvider) -> CompiledStateGraph:
    graph = StateGraph(GraphState)
    graph.add_node("generate", lambda state: generate_node(state, provider))
    graph.add_node("verify", verify_node)
    graph.add_node("finalize", finalize_node)
    graph.add_edge(START, "generate")
    graph.add_edge("generate", "verify")
    graph.add_conditional_edges("verify", decide_next_step,
                                {"retry": "generate", "finish": "finalize"})
    graph.add_edge("finalize", END)
    return graph.compile()


def initial_state(task: str, max_llm_calls: int = 2) -> GraphState:
    public = AgentState(task=task, max_llm_calls=max_llm_calls)
    return {**public.model_dump(), "response": None, "generation_error": None,
            "call_latency": 0.0, "started_at": perf_counter(), "result": None}


def run_agent(task: str, provider: ChatProvider, max_llm_calls: int = 2) -> AgentResult:
    state = initial_state(task, max_llm_calls)
    graph = build_graph(provider)
    # Prevent graph state/prompts from being sent to ambient tracing services.
    with tracing_context(enabled=False):
        output = graph.invoke(state, config={"recursion_limit": GRAPH_RECURSION_LIMIT, "callbacks": []})
    return AgentResult.model_validate(output["result"])
