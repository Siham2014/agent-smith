# Architecture decisions

## ADR 1 — Independent From Scratch project

Accepted: personal independent project, with no affiliation to the 42 curriculum.
The user instruction overrides the PDF chapter VII prescribed curriculum
attribution. Keep the README in English and retain useful description,
instructions, resources and AI-assistance transparency requirements.

## ADR 2 — Python 3.10 and uv

Accepted: PDF IV.1 (PDF page 10) requires Python 3.10 and uv.
Use requires-python = ">=3.10,<3.11" and .python-version = "3.10".
Patch updates within 3.10 remain possible. uv.lock locks dependencies, not the
interpreter binary. The runtime is checked separately via uv run --locked.
Global Python 3.14 does not determine the project's interpreter.

## ADR 3 — Keep the existing modular package

Accepted: preserve src/agent_smith, Hatchling and the existing public settings
models. Remove pytest's src path injection so tests import the installed package.
The PDF leaves the directory structure open (chapter VIII).
No orchestrator, provider, sandbox or MCP code is part of Phase 1.
No library replacing agent orchestration is allowed (PDF IV.2).

## ADR 4 — Typed configuration and secret handling

Accepted: Pydantic Settings loads optional UTF-8 .env values and environment
variables with AGENT_SMITH_ prefix and nested __ delimiter.
Precedence: constructor > environment > .env > defaults.
Unknown dotenv entries are ignored to permit shared provider variables later.
SecretStr masks representations but does not encrypt secrets.
The single optional api_key in LLMSettings is not a complete v1.1 provider
design: future provider work must support standard
provider environment names, multiple keys and rotation (V.6, VI).
No real credentials are required for tests.

## ADR 5 — Reproducible configuration tests

Accepted: isolate AGENT_SMITH_ variables in tests; test defaults, overrides,
validation, dotenv precedence and secret masking using synthetic values.
Use uv sync, uv lock --check and uv run --locked pytest.
The existing iteration default of 5 is retained as a local configuration default,
not an implementation of benchmark limits.

## Deferred PDF requirements

V.1: full sandboxed execution loop and extraction formats, StepMetrics/SolutionOutput.
Phase 3 implements a limited static-only revision loop, not this complete contract.
V.2: stdlib security, JSON/Pydantic sandbox configuration, MCP client inside
sandbox, independent MCP servers, stdio and streamable HTTP, final_answer.
V.3–V.5: MBPP, SWE-bench, CLI interfaces and independent tools.
V.6: free-tier providers, standard env variables, multiple tokens and rotation.
V.7: report for >=5 models, >=2 providers, >=3 SWE-bench tasks.
VI: benchmark budgets, provenance, cleanup and security checks.
These requirements are recorded, not claimed as implemented.

## ADR 6 — Phase 2 provider boundary

Accepted: use the official google-genai SDK, not an orchestration framework.
LLMRequest/LLMResponse/TokenUsage and the LLMProvider Protocol do not depend
on Google. GeminiProvider owns SDK translation and lifecycle. generate_text is
a one-shot convenience function; the service currently supports Google only.
No base-class hierarchy, registry or agent loop is needed.

google-genai>=1.75,<2 is the verified SDK API baseline; httpx>=0.28,<1 is declared
directly because our adapter catches its transport exceptions.
The installed lock resolves google-genai 1.75.0 and httpx 0.28.1 on Python 3.10.22.

## ADR 7 — Explicit model and bounded cost

Accepted: configure provider='google' and model='gemini-3.1-flash-lite' locally.
The identifier was verified against the official model page on 2026-11-06:
https://ai.google.dev/gemini-api/docs/models/gemini-3.1-flash-lite
A later user-authorized Phase 2 smoke call confirmed account/model access.
Future availability/quota remains account-dependent; no silent substitution.
Set SDK HttpRetryOptions(attempts=1); implement no application retries.
Disable automatic function calling; provide no tools or execution capability.
Keep temperature at the provider default. An optional positive
max_output_tokens cap is supported; timeout_seconds is finite, 0.001–600.
This transport timeout is not a hard whole-program deadline.

## ADR 8 — Safe boundary and faithful metrics

Accepted: require provider, explicit model and a nonblank SecretStr key before
constructing the SDK client. Keep Phase 1 defaults credential-free.
Revalidate settings at the adapter boundary; normalize request/configuration
errors in the one-shot service. Pydantic hides input values in rendered errors.

Translate exceptions using types/status/structured API_KEY_INVALID reason only;
never include raw SDK messages, exception chains, prompts or keys in application
logs. SecretStr is not encryption and raw validation detail dictionaries should
not be logged. Preserve KeyboardInterrupt/SystemExit by catching Exception only.

Use the first candidate's visible text; skip thought parts. Missing token
metadata remains None, including unknown totals. Preserve zero values and
separate reasoning/cache counts. Use perf_counter around the SDK call only.
Return the server model version when available, otherwise the requested model.
Context management closes the client on success/failure; cleanup failures do not
replace the original error.

## ADR 9 — Offline tests and opt-in manual verification

Accepted: socket/DNS access is forbidden in every automated test.
Use SDK-shaped fake clients and the SDK's real types; two contract cases use
httpx.MockTransport to verify serialization and single-attempt behavior.
Never perform real calls in pytest. The smoke module requires --allow-api;
without it, settings are not loaded and no client is created.
A real call is deliberately not part of implementation verification.

Multi-key rotation, fallback and standard provider-variable aliases remain
deferred by the user's Phase 2 scope, despite being eventual PDF requirements.

## ADR 10 — Phase 3 experimental AlphaCodium-Lite workflow

Accepted: this is our static-revision variant, not an official reproduction.
Implement START → Generate → Verify → Decide → Revision/Finalize → END in native
Python. Use separate models, prompts, verifier, controller and runner modules.
No orchestration framework or new dependency. Reuse Phase 2 GeminiProvider.

run_agent accepts an injected LLMProvider; the caller retains its ownership.
The default Gemini path owns one adapter and closes it in finally.
Input contract errors are rejected before constructing a client. Controlled
runtime errors return AgentResult. Cancellation propagates after cleanup.

## ADR 11 — Hard generation budget and terminal semantics

Accepted: max_llm_calls is a strict integer in [1,2], default 2, separate from
the existing max_iterations=5. Increment before provider.generate, including
failed calls. A bounded for loop is the final upper bound.
The only second call is a code revision after failed extraction/static syntax,
including an empty response. There is no transport retry or self-evaluation call.
Fatal configuration/access/quota/network/timeout errors stop immediately.

Syntax passing means status=unverified and
stop_reason=syntax_passed_functionality_unverified. Persisting static failure
means failed/budget_exhausted. No functional correctness is claimed.

## ADR 12 — AST-only verification and conservative extraction

Accepted: accept raw Python or one Python/py-tagged Markdown block. Refuse empty,
ambiguous or malformed output. Parse source with ast.parse only, never execute it.
Keep line/column errors bounded and avoid echoing source or raw exception messages.
Cap responses at 100000 characters before parsing. This bounds work but provides
no sandbox, hard wall-time guarantee or functional/security proof.
No arbitrary structural rules are added. level='structure' is reserved.

Prompts put task/previous code/observations into a JSON data payload, not a new
system instruction. This does not claim to solve model prompt injection.
The parser does not interpret generated text as instructions.

## ADR 13 — State and metrics as reviewable evidence

Accepted: Pydantic models validate positive budgets, nonnegative counts/times,
consecutive histories and terminal evidence. Lists use default_factory.
Mutable state is revalidated at transition/finalization boundaries; final history
contains one entry per counted call. Generation may temporarily have one
in-flight call not yet recorded.
Rejected input raises ValidationError before any API use; it is not represented
by a fabricated result with a nonempty replacement task.

Keep code per attempt (at most two bounded outputs), not raw provider exceptions.
Preserve returned usage/latency; missing metadata is None. Aggregate each token
field only if complete across every attempt. Total elapsed workflow time is a
separate monotonic-clock measurement including owned cleanup.
Unexpected failures and cleanup failures use fixed reasons without raw messages.

## ADR 14 — Offline verification and Phase 2 live evidence

Accepted: preserve all 63 Phase 1/2 test cases. Phase 3 uses injected fake providers,
the existing network-denial fixture, independent controller tests and a local
fixed-response demo. No real request is authorized for Phase 3.

A separately authorized Phase 2 smoke call already succeeded with
gemini-3.1-flash-lite, latency 1.920 seconds, one attempt. This is connectivity
evidence, not proof that every generated answer is correct. It was not rerun.
The response's claim about negative Python indices required a factual correction.

A planned Framework implementation may express stages/transitions as graph
constructs; our code uses a bounded Python loop and a pure controller.
The other project's code was not inspected; no performance comparison is claimed.
