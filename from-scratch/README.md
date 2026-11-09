# Agent Smith — From Scratch

## Description

Independent personal project by an ENSA Al Hoceima student in Digital
Transformation and Artificial Intelligence engineering, based on Agent Smith
v1.1. This project has no affiliation with the 42 curriculum.

Phase 1 provides the environment and validated settings. Phase 2 adds a
single-prompt Gemini integration. Phase 3 adds a bounded, static-only code
generation/revision workflow. Sandboxed execution is future work.

## Installation and offline verification

Requirements: uv and Python 3.10. The project uses its .venv independently of
global Python. The manifest accepts only Python 3.10.x.

Run from the repository root in PowerShell:

```powershell
uv sync
uv run --locked python --version
uv run --locked pytest
uv lock --check
```

Dependency installation may require Internet. Tests do not: every automated
test blocks socket connections and DNS resolution. Clients are mocked, except
two tests using the real SDK with an in-memory HTTP transport.

## Gemini configuration

Create a local file only if it does not exist:

```powershell
if (!(Test-Path .env)) { Copy-Item .env.example .env }
```

Edit .env locally in your editor:
- AGENT_SMITH_LLM__PROVIDER=google
- AGENT_SMITH_LLM__MODEL=gemini-3.1-flash-lite
- AGENT_SMITH_LLM__API_KEY: replace the example with your own local credential.
- AGENT_SMITH_LLM__TIMEOUT_SECONDS=30
- Optional AGENT_SMITH_LLM__MAX_OUTPUT_TOKENS: positive integer.

Never paste a real key into chat, source, tests or logs. .env and .env.* are
ignored by Git, except .env.example. SecretStr masks normal representations;
it does not encrypt credentials. Do not serialize raw SDK exceptions or
Pydantic error detail dictionaries.

Environment variables override .env; explicit constructor values override both.
The .env path is relative to the current working directory. Standard Google
key aliases are not automatically imported by our settings: use the documented
AGENT_SMITH_ variable. Settings remain optional until a call is requested, so
Phase 1 works without credentials.

The exact model identifier was checked on 2026-11-06 in Google's
[official model documentation](https://ai.google.dev/gemini-api/docs/models/gemini-3.1-flash-lite).
It is configurable and has no hidden fallback. Documentation confirms the
identifier. A separately authorized Phase 2 smoke call succeeded with this
model in 1.920 seconds. No real calls were made during Phase 3. Consult [Google's pricing](https://ai.google.dev/gemini-api/docs/pricing)
and AI Studio for current free-tier eligibility and quota. Use a free-tier
project; no billing setting is changed by this code.

## Optional real API check — explicit activation required

This command is disabled and sends no request:

```powershell
uv run --locked python -m agent_smith.llm.smoke
```

Only after configuring your local key and checking free quota, explicitly opt in:

```powershell
uv run --locked python -m agent_smith.llm.smoke --allow-api
```

It asks: "Explain in two sentences what a Python IndexError is."
A valid configuration results in one generate_content call, with SDK retries
disabled. It prints the answer, model and measured latency. Authentication,
quota, model-access, timeout and network failures are reported with safe messages.
The initial implementation used offline tests. A later explicitly authorized
Phase 2 real check succeeded; it was not repeated for Phase 3.

## Architecture and responsibilities

| File | Responsibility |
|---|---|
| src/agent_smith/config.py | Typed environment-backed settings |
| src/agent_smith/llm/models.py | LLMRequest, LLMResponse and TokenUsage |
| src/agent_smith/llm/provider.py | Minimal structural LLMProvider interface |
| src/agent_smith/llm/gemini.py | SDK adapter, extraction, metrics, errors and lifecycle |
| src/agent_smith/llm/service.py | generate_text(prompt, settings=None), one-shot entry point |
| src/agent_smith/llm/errors.py | Provider-independent exception hierarchy |
| src/agent_smith/llm/smoke.py | Explicitly activated manual API check |
| tests/conftest.py | Deny external network access in automated tests |
| tests/test_config.py | Preserved Phase 1 tests |
| tests/test_llm_config.py | Phase 2 settings and validation |
| tests/test_llm.py | Fake-client behavior and in-memory SDK contract |
| PROJECT_PROGRESS.md | Actual verification and scope |
| ARCHITECTURE_DECISIONS.md | Decisions and deferred requirements |

Request flow:
prompt → validated LLMRequest → generate_text → GeminiProvider →
Google SDK generate_content → Gemini API → normalized LLMResponse → client close.

LLMProvider is a Python Protocol: future providers can implement generate and
close without inheriting Google types. The one-shot service currently selects
only Gemini; adding another provider will require extending that selection.
The Google SDK is an API client, not an agent orchestration framework.

The adapter concatenates visible text parts from the first candidate and omits
thought parts. It never executes generated code or function calls. Automatic
function calling is explicitly disabled.

The response exposes text, provider, returned model version (or requested model
when absent), latency_seconds, finish_reason and optional input/output/total/
reasoning/cached token counts. Missing metrics remain None; zero is preserved.
No missing total is invented by summing partial metrics.

## Errors, limits and future work

The integration distinguishes configuration, missing key, authentication/
permission, rate-limit/quota, timeout, network, unusable response and other
provider errors. Raw provider messages and exception chains are not displayed.
No prompt, key or raw response is logged by our adapter.

SDK retries default to more than one attempt; this project explicitly sets
attempts=1. There is no application retry. Users decide whether to try again
after a failure, protecting the free quota.

Timeout seconds are converted to SDK milliseconds. This is a transport request
timeout, not a guaranteed hard deadline for the whole program. Latency uses a
monotonic performance clock around the SDK call; it excludes client construction,
normalization and cleanup.

Remaining: ongoing account/quota availability, multi-key rotation, provider fallback,
standard provider-key aliases, streaming and benchmark metrics aggregation.
The PDF ultimately requires multi-token providers; the user explicitly deferred
rotation and fallback beyond Phase 2. Phase 3 adds static orchestration only;
no sandbox, MCP, MBPP, SWE-bench or multi-model benchmark is implemented.

## Resources and AI assistance

- Agent Smith v1.1, supplied locally (32 PDF pages).
- [Python 3.10](https://docs.python.org/3.10/)
- [uv](https://docs.astral.sh/uv/)
- [Pydantic Settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)
- [pytest](https://docs.pytest.org/)
- [Official Google Gen AI SDK](https://googleapis.github.io/python-genai/)
- [Gemini 3.1 Flash-Lite](https://ai.google.dev/gemini-api/docs/models/gemini-3.1-flash-lite)

GitHub Copilot assisted the initial Phase 1 attempt. Codex reviewed Phase 1
against the PDF and implemented the Phase 2 adapter, offline tests and
documentation. Phase 3 orchestration, static verification and offline tests were
also implemented with Codex assistance. Technical decisions remain the project
author's responsibility.

## Phase 3 — AlphaCodium-Lite static revision

This name refers to our experimental variant, not an official reproduction of
AlphaCodium. It adds handwritten Python orchestration over the existing
Phase 2 provider. It does not implement the PDF's complete sandboxed
Thought → Code → Observation execution loop.

### Workflow

```text
START → Generate → Extract → Verify (AST) → Decide
                           ↑                |
                           └── Revision ────┘
                           or Finalize → END
```

A task gets at most two provider.generate calls (or one if explicitly configured).
A valid first syntax check stops immediately. Only unusable output or a syntax
failure may trigger a revision; transport errors never trigger retries.
There is no model-based self-evaluation.

### Offline demonstration

```powershell
uv run --locked python -m agent_smith.agent.demo
```

This command injects two fixed responses, without reading .env or constructing
a Gemini client. It first returns a function missing a colon, then a corrected
function. The result is JSON with llm_calls=2, an ordered attempt history,
status="unverified" and stop_reason="syntax_passed_functionality_unverified".
The demo prints source code as data; it does not execute that source.

Run the complete offline suite:

```powershell
uv run --locked pytest
```

Actual Phase 3 verification: 177 passed in 2.67s on Python 3.10.22.
The previous 63 cases remain unchanged and pass.
No real Gemini request was made during Phase 3.

### Components and public API

| Module in src/agent_smith/agent/ | Responsibility |
|---|---|
| models.py | Validated state, observations, attempts, decisions and terminal results |
| prompts.py | build_prompt(state), with task/prior code/errors as JSON data |
| verifier.py | extract_python_code(text), verify_code(state), using ast.parse only |
| controller.py | decide_next_step(state), deterministic and independent of a provider |
| runner.py | generate_code, finalize_result and bounded run_agent |
| demo.py | Fixed-response offline demonstration |
| __init__.py | Minimal public API |

run_agent(task, provider=an_existing_provider, max_llm_calls=2) supports a provider
implementing the Phase 2 LLMProvider Protocol. Injected providers are caller-owned:
the runner neither reads local credentials nor closes these providers.

Without an injected provider, run_agent uses the existing GeminiProvider and
local settings. That is a real API path: do not invoke it without explicit
authorization. It constructs one adapter, reuses it across revisions, then closes
it in finally. No second Google SDK implementation was added. The existing
one-shot generate_text and Gemini smoke command remain unchanged.

### State and result contracts

- VerificationResult: passed, level, bounded errors and code_extracted.
  This phase always uses level="syntax"; "structure" is reserved.
- AttemptRecord: 1-based iteration, extracted code, verification, latency,
  optional TokenUsage and optional stable error_kind.
- AgentState: nonblank task, current extracted code, call count and budget,
  attempts, status, stop reason, last observation, elapsed time and last error.
- Decision: generate/retry/finalize, next status and optional stop reason.
- AgentResult: task, last attempt's code, terminal status/reason, counted calls,
  total wall latency, attempts and optional aggregated tokens.

The budget is a strict integer from 1 to 2. It is separate from Phase 1's
max_iterations=5, which is not used by this workflow.
Input contract violations (blank task/invalid budget) raise ValidationError
before client creation; controlled runtime failures return failed AgentResult.
Passing both an injected provider and settings raises ValueError.

State is mutable internally. Pydantic validates it at creation and generation,
decision and finalization boundaries. Histories must be consecutive; every
counted call must have an attempt at finalization. Only a generating state may
temporarily lack one entry. Current/final code must match the last completed
attempt. Mutable collections use default_factory; no shared default history.

### Deterministic stop policy

| Observation | Decision |
|---|---|
| Syntax passes | unverified / syntax_passed_functionality_unverified; no extra call |
| Extraction/syntax fails, budget remains | needs_revision; include previous code and static errors |
| Extraction/syntax fails, budget spent | failed / budget_exhausted |
| Empty response, including Phase 2 empty-response exception | Failed extraction; revision only with remaining budget |
| Missing key or invalid configuration | failed / missing_api_key or configuration_error |
| Authentication/permission or quota failure | failed / authentication_error or quota_exceeded |
| Timeout or network failure | failed / timeout or network_error; no transport retry |
| Other provider failure | failed / provider_error |
| Unexpected ordinary exception | failed / unexpected_error |
| Owned-client cleanup failure | failed / client_cleanup_error, preserving an earlier failure |

pending → generating → verifying → needs_revision → generating is the revision
path. The final states are unverified and failed. No status is called
"functionally correct" or "success". KeyboardInterrupt and SystemExit propagate;
owned resources are still closed.

### Static verification and its limits

Extraction accepts raw Python or one Python/py-tagged, correctly closed Markdown
block (optional surrounding prose is discarded). Multiple, unclosed, untagged
or non-Python fences are rejected. Empty output is rejected.
Responses are limited to 100,000 characters before AST parsing to bound local
work and history size; this is not a sandbox or a hard memory/time limit.

Syntax errors return bounded line/column diagnostics, without echoing the source.
No structural heuristics, imports, generated tests or code execution are used.
ast.parse builds a syntax tree; it does not run module statements.
It cannot establish algorithmic correctness, valid dependencies, safe behavior,
or absence of runtime errors. Comments and a function returning 1/0 can pass.
Some checks normally done by later compilation stages are outside this phase.

Task and previous source remain untrusted data. JSON delimiting documents the
prompt boundary; it is not a guarantee that a model will resist prompt injection.
Provider messages are mapped to stable reason codes without copying raw
exceptions. Do not include secrets in tasks/source; history contains code.

### Metrics

Calls are counted immediately before provider.generate, including failed attempts.
A failure during client/settings construction is zero calls and zero attempts.
No transport retry or extra verification call is made.

Each successful response preserves the Phase 2 SDK-call latency and available
tokens. On a failed call, the runner measures its elapsed duration; tokens stay
unknown. total_latency_seconds covers the workflow including client setup,
static processing and owned-client cleanup, after input validation.

Aggregate token fields are summed only when every attempt has that field.
A missing field in any attempt leaves its total unknown (None); zero is preserved.
Known per-attempt values remain in history even if a complete total is unavailable.

### Planned Framework comparison

The environment, LLM contracts and validation problem can remain similar.
A possible LangGraph version could represent these stages and conditional
transitions with graph constructs. Here, a bounded for loop and a pure controller
make those choices explicitly. This is a design comparison only: the other
project has not been inspected, no LangGraph dependency was added, and no
performance advantage is claimed.

Remaining work requires later authorization: functional verification in a
sandbox, MCP, full PDF output schemas and benchmark budgets. Phase 4 is not started.
