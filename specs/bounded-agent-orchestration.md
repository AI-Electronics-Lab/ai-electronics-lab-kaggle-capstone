# Bounded Agent Orchestration

## Purpose

Version 1.0 adds one bounded orchestration boundary on top of the existing deterministic
planning, assembly, simulation, parsing, and verification layers:

```text
natural-language prompt
-> bounded planner
-> validated CircuitPlan
-> deterministic simulation assembly
-> bounded ngspice execution
-> deterministic result parsing
-> deterministic verification
```

The orchestration layer consumes untrusted prompt text and returns only verified structured
results plus a closed, safe stage trace vocabulary. It does not accept trusted netlists, arbitrary
subprocess arguments, filesystem paths, prompt-controlled execution policy, or free-form stage
labels.

The existing manual simulation route at `POST /api/simulate` remains unchanged and continues to
accept direct manual simulation payloads.

## Exact changed-file allowlist

PR #14 implementation changes are limited to:

1. `specs/bounded-agent-orchestration.md`
2. `src/ai_electronics_lab/orchestration/__init__.py`
3. `src/ai_electronics_lab/orchestration/orchestrator.py`
4. `src/ai_electronics_lab/web/app.py`
5. `src/ai_electronics_lab/web/index.html`
6. `tests/orchestration/test_bounded_agent_orchestration.py`
7. `tests/web/test_app.py`

No other repository files are in scope for the PR implementation.

## Public API

The orchestration package exports:

- `BOUNDED_AGENT_ORCHESTRATION_VERSION = "1.0"`
- `BoundedAgentOrchestrationConfig`
- `BoundedAgentOrchestrationError`
- `BoundedAgentTraceEvent`
- `BoundedAgentOrchestrationResult`
- `load_bounded_agent_orchestration_config()`
- `run_bounded_agent_orchestration(prompt, *, config=None, planner=..., runner=..., parser=..., verifier=...)`

`run_bounded_agent_orchestration()` is synchronous and accepts exactly one exact built-in `str`
prompt. It returns exactly one validated `BoundedAgentOrchestrationResult` or raises one
`BoundedAgentOrchestrationError`.

The direct manual simulation API remains separate and is not widened to accept prompt text:

- `simulate_request(payload, *, runner=..., parser=..., verifier=...)`

The orchestration HTTP route is:

- `POST /api/orchestrate`

## Input Contract

The orchestration HTTP request body is an exact JSON object with exactly one key:

- `prompt`: exact built-in `str`

No other request fields are accepted. The body is read with the same request hardening as the
existing local web boundary: bounded size, UTF-8 only, duplicate-key rejection, and non-finite JSON
rejection before any orchestration work starts.

The prompt contract matches the planner boundary:

- after trimming, it must be non-empty;
- it must contain no more than 4000 Unicode code points;
- it must encode to no more than 16384 UTF-8 bytes;
- it must contain no control characters;
- it must not be `bool`, `bytes`, `bytearray`, or `None`.

Invalid prompts fail before planner invocation or ngspice execution.

## Immutable Result Schema

`BoundedAgentTraceEvent` is a frozen slots dataclass with:

1. `stage: str`
2. `status: str`
3. `code: str | None`
4. `path: tuple[str | int, ...]`

`stage_trace` is defensively converted to an immutable tuple. `code` and `path` are present only
for failed events. The trace contains no timestamps, raw provider text, netlists, stack traces,
filesystem paths, or prompt echoes.

`BoundedAgentOrchestrationResult` is a frozen slots dataclass with canonical field order:

1. `version`
2. `status`
3. `stage_trace`
4. `plan`
5. `assembly`
6. `deck`
7. `parsed_results`
8. `verification`

The nested values are the existing immutable deterministic structures from the repository:

- `plan` is a validated `CircuitPlan`;
- `assembly` is a `SimulationAssembly`;
- `deck` is a `SimulationDeck`;
- `parsed_results` is a `SimulationParsedResults`;
- `verification` is a `SimulationVerificationResults`.

The result is immutable, recursively defensive against mutable inputs, and serializes deterministically
with stable key order and compact JSON. It does not expose raw model output, raw simulation evidence,
or unverified evidence. PR #15 will add the explanation layer and its schema.

## Safe Stage-Trace Vocabulary

The stage vocabulary is closed. Only these stage names may appear:

- `request.received`
- `request.validated`
- `planner.requested`
- `planner.completed`
- `plan.validated`
- `assembly.completed`
- `deck.completed`
- `simulation.started`
- `simulation.completed`
- `parse.completed`
- `verification.completed`
- `request.completed`
- `request.failed`

Allowed trace statuses are closed as well:

- `started`
- `completed`
- `failed`

Trace events must use only these vocabulary items. No free-form stage text, provider text, prompt
text, stack traces, or netlist fragments may be written into the trace. If a bounded repair attempt
occurs, it is represented only by repeated closed-vocabulary stage events and not by ad hoc notes.

Successful runs emit the stage sequence in deterministic order and end with `request.completed`.
Failed runs end with `request.failed` and a stable error code.

## Web UI

The self-contained browser UI at `src/ai_electronics_lab/web/index.html` includes:

- a natural-language prompt input for `POST /api/orchestrate`;
- supported example prompts that populate the prompt input;
- a safe stage-trace renderer that only displays the closed stage/status vocabulary and bounded path/code metadata;
- the existing manual simulation form for `POST /api/simulate`, which remains unchanged.

The prompt UI is bounded before request submission and is separate from the manual simulation form.

## Stable Error Codes And HTTP Mappings

The orchestration HTTP boundary maps stable codes to stable HTTP statuses. Error payloads use the
same safe shape as the local web boundary: a top-level `status: "error"` plus a stable machine
code, bounded path, and human-readable message.

| Code | HTTP | Meaning |
| --- | --- | --- |
| `orchestration.request.content_type` | 400 | Request is not JSON. |
| `orchestration.request.encoding` | 400 | Request body is not valid UTF-8. |
| `orchestration.request.empty` | 400 | Request body is empty. |
| `orchestration.request.malformed_json` | 400 | JSON syntax is invalid. |
| `orchestration.request.duplicate_key` | 400 | JSON object contains duplicate keys. |
| `orchestration.request.non_finite` | 400 | JSON contains NaN or infinity. |
| `orchestration.request.object_required` | 422 | Request body is not a JSON object. |
| `orchestration.request.prompt_invalid` | 422 | Prompt violates the bounded prompt contract. |
| `orchestration.request.busy` | 429 | Another orchestration request is already running. |
| `orchestration.planner.invalid` | 422 | Planner returned a candidate plan that fails deterministic validation. |
| `orchestration.planner.unavailable` | 503 | The bounded planner could not complete a provider call. |
| `orchestration.plan.invalid` | 422 | The request cannot be converted into a valid circuit plan. |
| `orchestration.deck_rejected` | 500 | Deterministic simulation deck creation failed. |
| `orchestration.execution_failed` | 503 | Bounded ngspice execution did not complete. |
| `orchestration.evidence_invalid` | 502 | Simulation evidence could not be parsed. |
| `orchestration.verification_invalid` | 502 | Deterministic verification failed. |
| `orchestration.internal_error` | 500 | Unclassified deterministic failure. |

The HTTP mappings are stable and do not depend on raw provider bodies, stack traces, or filesystem
paths. The manual simulation route keeps its existing request and error contract.

## Acceptance And Hostile-Input Tests

The implementation must add tests that cover:

- a successful prompt-to-result run with an exact trace sequence, frozen nested data, and stable JSON
  serialization;
- preservation of the manual `POST /api/simulate` route and its direct manual simulation payloads;
- rejection of empty prompts, unsupported types, overlong prompts, and control-character prompts;
- rejection of invalid JSON, duplicate keys, non-finite numbers, invalid UTF-8, and oversized bodies
  before planner invocation;
- stable error mapping for planner failure, evidence parse failure, verification failure, busy-lock
  failure, and internal failure;
- hostile prompt text containing command fragments, paths, URLs, or provider-injection text without
  echoing those strings into traces or error payloads;
- rejection of unknown stage labels and any attempt to construct a trace with mutable sequence fields;
- isolated tests that inject fake planner, runner, parser, and verifier dependencies without touching
  the manual simulation route.

The tests should live in:

- `tests/orchestration/test_bounded_agent_orchestration.py`
- `tests/web/test_app.py`

## Smallest Implementation Sequence

1. Add the orchestration dataclasses and error type in the new orchestration package, reusing the
   existing planner, simulation, parser, and verification modules.
2. Implement the pure synchronous orchestration function that builds the plan, validates it, runs the
   bounded simulation, verifies the evidence, and assembles the deterministic stage trace.
3. Add the HTTP route `POST /api/orchestrate` in `src/ai_electronics_lab/web/app.py` without changing
   `POST /api/simulate`.
4. Add the success-path and hostile-input tests, including the dependency-injection seams and manual-
   route preservation checks.
5. Verify that the new API exports remain stable and that the result schema serializes deterministically.
