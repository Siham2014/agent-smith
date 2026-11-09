# Architecture decisions

The Phase 2 sections below describe their original scope. The Phase 3 section supersedes references to the absence of LangGraph/orchestration.

## 1. One request, application-owned contract

`ChatProvider` is a typing Protocol (structural interface). `GeminiProvider.ask` implements it without inheritance. `LLMResponse` and `TokenUsage` are frozen Pydantic data models. Consumers need neither AIMessage nor Google SDK response classes. This makes comparison with a future direct-SDK adapter easier. The configured model is reported; backend revision discovery is not implemented.

## 2. Minimal LangChain integration

Use langchain-core HumanMessage and langchain-google-genai ChatGoogleGenerativeAI. Do not add the umbrella langchain package, LangGraph, or agents. The integration already depends on core and Google GenAI; uv resolves the whole dependency graph for Python 3.10. PyPI verified versions: core 1.7.6 and integration 4.4.3 both declare Python >=3.10,<4. The lock selects Google GenAI 2.33.0.

LangChain handles standardized messages, invoke, and conversion of the Google response into AIMessage. Our application still owns settings, errors, text normalization, latency measurement, public output, and tests. Direct SDK code would instead construct Google contents/parts, call generate_content, and normalize candidates/usage itself. Neither architecture automatically provides safe generated-code execution.

## 3. Model and backend

Official model code verified 2026-11-06: gemini-3.1-flash-lite.
https://ai.google.dev/gemini-api/docs/models/gemini-3.1-flash-lite

Keep configurable; never select a substitute. Select vertexai=False explicitly and pass the SMITH_ credential instead of relying on Google ambient credentials. Account entitlement and quota are only verifiable by an explicit live request. No billing setup or paid feature is enabled.

## 4. Configuration and secrets

Preserve BaseSettings env_prefix SMITH_, UTF-8 dotenv, --env-file, defaults and strict extra handling. A missing credential is allowed until a live operation. SecretStr, repr=False, exclude=True and hide_input_in_errors reduce accidental disclosure. CLI settings errors remain generic. Runtime provider errors use fixed public messages and are raised outside the except block to avoid secret-bearing exception context. No raw exception string, raw metadata, or key is logged. CLI additionally redacts exact key matches from returned text. These protections do not encrypt process memory or guarantee that arbitrary model output is trustworthy.

Tracing is explicitly disabled during invocation, independent of ambient LangSmith settings. Application output is not sent to a tracing service.

## 5. One attempt and timeout

No application retry loop. Set max_retries=0 and explicitly pass http_options.retry_options.attempts=1. Installed integration source interprets max_retries as SDK total attempts; the explicit override avoids ambiguity and is verified at the actual SDK boundary offline. Timeout is configured in seconds and LangChain converts to milliseconds (30 -> 30000), also verified offline. This is an HTTP timeout, not a hard wall-clock process deadline.

## 6. Response and metrics

Accept AIMessage string or text blocks; omit non-text/thinking blocks. Whitespace-only or non-text-only results raise empty_response. TokenUsage retains reported input/output/total counters; absent counters are None, not zero or estimated sums. No raw provider metadata is exposed. finish_reason is optional. perf_counter measures invoke latency including client overhead. No benchmark metrics are fabricated.

## 7. Errors

LLMError codes: missing_key, authentication (401/403), quota (429), model (404), timeout, network, empty_response and provider. Walk wrapped exception causes to support LangChain SDK translations, without copying their messages. Support both httpx and httpx2 transport exception types used by the resolved SDK. Unknown failures get a generic safe message. Configuration failures remain ValidationError handled by the CLI. Blank prompts fail locally before invoke. KeyboardInterrupt/SystemExit are not caught by except Exception.

## 8. Offline verification

Retain Phase 1 tests. Use mock LangChain chat for unit tests, generated non-credential strings for SecretStr tests, and patch Google Models.generate_content to test real LangChain formatting and error translation. An autouse fixture blocks socket connections in the pytest process and disables tracing; existing CLI subprocess tests only use offline startup/version. No automatic live test, API discovery call or real credential is used.

## 9. Scope and tradeoffs

Default CLI behavior still validates configuration without connecting. --llm-smoke-test and --prompt are mutually exclusive opt-ins, make one request, and display text plus measured latency. SDK HTTP connections currently follow the underlying client lifecycle; a reusable application/server lifecycle is future work. No graph, tools, MCP, sandbox, generated-code execution, datasets, key rotation or provider fallback implemented.


### Token zero ambiguity

Installed LangChain converts some absent Google token counters into zero. To avoid fabricating measured zeros, this adapter conservatively exposes zero counters as None (unknown); positive reported counters are retained. This also loses the distinction of a genuine reported zero. Complete absence of usage remains None. Real SDK-boundary tests cover both absent and partial metadata. No total is calculated by the application.


## Phase 3 decisions - LangGraph static workflow

1. **Real graph, shared provider:** add langgraph 1.2.20 (Requires-Python >=3.10), resolved against existing core 1.7.6 and Google integration 4.4.3. Reuse GeminiProvider.ask unchanged. StateGraph builds generate/verify/finalize nodes, START/END edges and a conditional retry/finish edge. Compile and invoke/stream are the orchestration engine, not a custom while loop. No prebuilt agent factory is called.
2. **Package layout:** use the requested cohesive agent/ package with models, prompts, verifier, nodes and graph. Initial graph/ placeholders remain reserved; there is only one implemented graph, in agent/graph.py. No duplicate implementation is placed in the old placeholders.
3. **Bounded requests:** accept strict max_llm_calls 1 or 2, default 2. Always generate once for a valid input. Retry exactly once only for extraction/structure/syntax errors or empty responses. Stop on provider/configuration/auth/quota/timeout/network errors without transport retry. The Phase 2 adapter retains one SDK attempt per ask. generate_node guards its budget before asking; routing uses state, not model output. Recursion limit 8 accommodates the five-node longest path without replacing the business budget.
4. **Application vs runtime state:** frozen Pydantic boundary contracts validate fields and cross-field invariants. TypedDict GraphState supports LangGraph partial updates and contains transient data. validated_state checks public fields in nodes and routing. Lists use default_factory and nodes replace history with a new list. Frozen is not deep immutability. No checkpoint store, credentials or provider object in state. The compiled graph can be reused with fresh initial_state; callers should use run_agent for the validated entry point, not inject arbitrary runtime states.
5. **No functional-success claim:** a nonempty Python module accepted by ast.parse yields unverified with syntax_passed_functionality_unverified. Wrong algorithms, missing runtime names and unsafe operations may still parse. AST is neither sandbox nor proof of correctness, and is not a complete compiler-context check. Extraction accepts raw Python or a unique python/py fenced block (surrounding explanation ignored); multiple or malformed fences and non-Python fence labels are rejected. Comment-only or string-only modules fail structure checks. Source code is never executed.
6. **Provider failures:** preserve error codes but never raw exception messages in observations/results. Record a structure-level failed attempt with code_extracted=False and explicit verification-not-performed observation; retain provider_* stop_reason so this is not confused with syntax failure. Unexpected failures map to provider_error. Empty_response is special and recoverable. A configuration ValidationError during ask maps to configuration_invalid. CLI rejects invalid Settings before provider creation.
7. **Metrics:** attempt count includes failed ask calls; latency on successful calls comes from LLMResponse, failed-call latency from perf_counter. total_latency_seconds sums call latencies; elapsed_seconds is graph wall time. TokenUsage fields aggregate only when known for every attempt. Otherwise the aggregate field is None and known per-attempt data stays available. No estimates or incomplete totals labelled as complete.
8. **Tracing and secrets:** run_agent disables tracing around the whole graph. No raw provider exceptions are propagated. CLI initialization errors remain generic and exact configured-key occurrences in proposed output are redacted. Phase 2 files config/settings.py and providers/gemini.py are unchanged in this phase. No .env contents are displayed.
9. **Verification:** real compiled-graph stream updates assert exact node order for success, revision and failure; scripted providers verify actual call counts. Tests cover default budgets, invalid state, independent histories, empty/ambiguous Markdown, errors, metrics and CLI. A top-level file-write/raise proposal passes syntax without creating the file or raising, proving nonexecution in that scenario. The existing socket-blocking fixture is retained. No live Gemini calls in Phase 3.
10. **Comparison:** LangGraph provides node scheduling, state propagation, conditional transitions and END. The same policy using a custom state machine could provide equivalent behavior without LangGraph, but would own the scheduling code. We have not inspected the separate From Scratch repository and claim policy equivalence to the supplied rules only.

A Mermaid source file is generated locally from get_graph().draw_mermaid(); no external drawing service is used. An offline scripted-provider demonstration is available in examples/phase3_offline.py. No Phase 4 tools, MCP, sandbox or execution are added.
