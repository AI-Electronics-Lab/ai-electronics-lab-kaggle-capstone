# Bounded OpenRouter CircuitPlan planner

## Purpose

Version 1.0 adds one bounded natural-language planning boundary before the existing deterministic
CircuitPlan validation and simulation pipeline:

```text
bounded natural-language prompt
-> fixed OpenRouter chat-completions request
-> bounded provider response envelope
-> exact candidate JSON object
-> candidate CircuitPlan
-> existing deterministic validation
-> validated CircuitPlan or stable safe failure
```

Provider output is always untrusted candidate data.

The planner does not create or accept trusted netlists, circuit connectivity, node names, SPICE
directives, executable arguments, filesystem paths, simulation evidence, verification evidence, or
final engineering claims.

## Supported scope

Version 1.0 supports exactly:

- `rc_low_pass`;
- `rc_high_pass`;
- `resistive_divider`.

The planner may propose only the topology-specific fields already defined by CircuitPlan version
1.0.

Unsupported requests fail safely. The planner must not substitute an unrelated supported topology.

## Public API

The package `ai_electronics_lab.planning` exposes:

- `OPENROUTER_PLANNER_VERSION = "1.0"`;
- `OpenRouterPlannerConfig`;
- `CircuitPlannerError`;
- `load_openrouter_planner_config()`;
- `plan_circuit_request(prompt, *, config=None)`.

`plan_circuit_request` is asynchronous and returns exactly one validated `CircuitPlan` or raises
one `CircuitPlannerError`.

Test-only HTTP transport injection remains private.

## Configuration

The planner reads only:

- `OPENROUTER_API_KEY`;
- `OPENROUTER_BASE_URL`;
- `OPENROUTER_MODEL`;
- `OPENROUTER_TIMEOUT_SECONDS`;
- `OPENROUTER_MAX_TOKENS`.

Defaults:

- base URL: `https://openrouter.ai/api/v1`;
- model: `openai/gpt-oss-120b:free`;
- total timeout: `20` seconds;
- maximum completion tokens: `800`.

The API key is required for a live request.

The implementation does not enumerate the environment and does not automatically parse `.env`.
Local invocation may explicitly load the ignored `.env`, for example with
`uv run --env-file .env`.

The tracked `.env.example` contains only empty or non-secret values.

## Configuration validation

Configuration is validated before creating an HTTP client.

The base URL must:

- use `https`;
- use host exactly `openrouter.ai`;
- use the default HTTPS port;
- use path exactly `/api/v1`, allowing one normalized trailing slash;
- contain no username, password, query, fragment, or additional path.

The model must be an exact built-in trimmed non-empty string no longer than 200 characters and
contain no control characters.

The API key must be an exact built-in trimmed non-empty string no longer than 4096 characters and
contain no control characters.

The API key must never appear in object representations, serialization, exceptions, logs, test
snapshots, or user-facing errors.

The timeout must be an exact built-in finite number from 1 through 60 seconds. Booleans are
rejected.

The completion-token limit must be an exact built-in integer from 64 through 2048. Booleans are
rejected.

## Prompt boundary

The prompt must be an exact built-in `str`.

After trimming, it must:

- be non-empty;
- contain no more than 4000 Unicode code points;
- encode to no more than 16384 UTF-8 bytes.

Invalid prompts fail before configuration loading, HTTP-client creation, or network access.

Prompt text is inert data. It cannot change the endpoint, model, system policy, request fields,
repair count, schema, validators, or downstream execution policy.

## Fixed request

The planner sends POST requests only to:

```text
https://openrouter.ai/api/v1/chat/completions
```

Headers:

- `Authorization: Bearer <OPENROUTER_API_KEY>`;
- `Content-Type: application/json`;
- `Accept: application/json`.

Body fields:

- configured `model`;
- one fixed system message;
- one bounded user message;
- `temperature: 0`;
- `stream: false`;
- configured `max_tokens`;
- `reasoning: {"effort": "low", "exclude": true}`.

The default free model is not treated as supporting provider-enforced structured output.
Version 1.0 does not send or rely on `response_format`. Exact JSON is enforced locally.

The request contains no:

- tools or tool choice;
- functions;
- plugins;
- web search;
- images, files, or audio;
- alternate-model list;
- caller-provided URL;
- caller-provided headers;
- prompt-controlled request options.

The encoded request body must not exceed 32768 bytes.

## HTTP transport policy

The async HTTP transport uses:

- TLS verification enabled;
- `trust_env=False`;
- redirects disabled;
- no automatic retries;
- no ambient proxy configuration;
- no `.netrc` credential loading;
- connect timeout no greater than 5 seconds;
- read timeout no greater than 15 seconds;
- one total planner deadline, defaulting to 20 seconds.

At most two provider calls may occur: one initial request and one bounded repair request.

The response body is read incrementally. More than 65536 bytes fails immediately.

Provider responses are never written to disk.

## Provider-envelope boundary

The HTTP status must be successful. Error bodies are not copied into exceptions.

The decoded provider response must contain:

- an exact JSON object;
- `choices` as an exact list containing exactly one item;
- one exact object choice;
- `message` as an exact object;
- assistant `content` as an exact non-empty string;
- no non-empty `tool_calls`;
- `finish_reason` equal to `stop`.

Assistant content must not exceed 16384 UTF-8 bytes.

Provider IDs, usage information, reasoning details, fingerprints, metadata, and arbitrary envelope
fields are discarded.

Reject:

- malformed UTF-8;
- malformed JSON;
- duplicate JSON keys;
- non-finite JSON constants;
- excessive JSON nesting;
- zero or multiple choices;
- choice-level errors;
- missing message or content;
- tool calls;
- truncated output;
- non-string content.

## Candidate JSON boundary

Assistant content must be exactly one JSON object.

Reject:

- Markdown fences;
- prose prefixes or suffixes;
- comments;
- JSON fragments;
- multiple JSON values;
- duplicate keys;
- non-finite constants;
- heuristic extraction.

The candidate object must contain exactly:

1. `schema_version`;
2. `topology`;
3. `analysis`;
4. `parameters`;
5. `requested_frequencies_hz`;
6. `assumptions`.

Unknown fields are rejected, including:

- `netlist`;
- `spice`;
- `spice_directive`;
- `shell`;
- `command`;
- `path`;
- `tools`;
- `tool_calls`;
- `evidence`;
- `verification`;
- `status`;
- `explanation`.

The six values are passed only to the existing `CircuitPlan` constructor.

The resulting object must pass `require_valid_circuit_plan()` before it is returned.

The planner does not weaken, duplicate, replace, or bypass existing CircuitPlan validation.

## Unsupported topology

A plain-string topology outside the existing CircuitPlan allowlist fails with:

- `planner.plan.unsupported_topology`.

This failure is not repairable.

No second request is made and the unsupported topology text is not reflected in the safe error.

## Single repair policy

Exactly one repair request is permitted only when the initial provider result contains:

- invalid candidate JSON; or
- an exact candidate object that produces an invalid supported-topology CircuitPlan.

These failures are not repairable:

- prompt errors;
- configuration errors;
- timeout or network errors;
- HTTP errors;
- oversized responses;
- malformed provider envelopes;
- tool calls;
- truncated responses;
- unsupported topologies.

The repair request contains only:

- the original bounded prompt;
- the fixed system policy;
- bounded stable validation codes;
- bounded field paths;
- an instruction to return one corrected exact JSON object.

It does not contain:

- the raw first response;
- provider metadata;
- exception representations;
- secrets;
- filesystem paths;
- raw provider messages.

A second invalid candidate fails with `planner.repair.exhausted`.

No third request or autonomous loop is allowed.

## Stable errors

`CircuitPlannerError` inherits `ValueError` and contains:

- `code`;
- `path`;
- `message`;
- deterministic `to_dict()` output.

Stable codes:

### Input

- `planner.input.type`;
- `planner.input.empty`;
- `planner.input.too_large`.

### Configuration

- `planner.config.api_key_missing`;
- `planner.config.invalid`.

### Provider

- `planner.provider.timeout`;
- `planner.provider.network_error`;
- `planner.provider.http_error`;
- `planner.provider.response_oversized`;
- `planner.provider.envelope_invalid`;
- `planner.provider.content_missing`.

### Candidate plan

- `planner.output.invalid_json`;
- `planner.plan.unsupported_topology`;
- `planner.plan.invalid`;
- `planner.repair.exhausted`.

Messages are fixed and user-safe.

They never contain API keys, authorization headers, prompts, assistant content, HTTP bodies,
provider messages, metadata, exception representations, environment values, or local paths.

## Dependency

Promote the already locked HTTPX2 distribution to a runtime dependency:

```toml
"httpx2>=2.4,<2.5"
```

The implementation imports its `httpx` compatibility module.

Do not add:

- OpenAI SDK;
- OpenRouter SDK;
- `requests`;
- `python-dotenv`;
- an agent framework;
- another schema-validation framework.

## Acceptance tests

Mocked transport tests must prove:

1. valid plans for all three supported topologies;
2. exact endpoint, headers, messages, model, token limit, and reasoning policy;
3. absence of tools, plugins, web search, and arbitrary request fields;
4. invalid prompts make zero HTTP calls;
5. invalid configuration makes zero HTTP calls;
6. timeout, network, HTTP, redirect, and oversized-response handling;
7. environment proxy and `.netrc` isolation;
8. malformed UTF-8 and provider JSON rejection;
9. duplicate provider keys and non-finite constants rejection;
10. malformed, multiple, errored, truncated, tool-call, and content-less choices rejection;
11. assistant-content size enforcement;
12. fenced JSON, prose, trailing text, multiple values, duplicate keys, and non-finite values rejection;
13. missing, unknown, and forbidden candidate fields rejection;
14. existing CircuitPlan validation remains authoritative;
15. one invalid candidate may produce exactly one repair;
16. valid repair succeeds;
17. second invalid candidate returns `planner.repair.exhausted`;
18. unsupported topology produces no repair;
19. provider failures produce no repair;
20. secrets and raw provider data never appear in exceptions;
21. deterministic package exports and error serialization;
22. focused tests, complete tests, Ruff, compilation, wheel build, and secret scan pass.

No automated test sends a real external request.

## Exact PR file allowlist

Only these files may change:

```text
.env.example
docs/decisions.md
docs/development-log.md
pyproject.toml
specs/bounded-openrouter-planner.md
src/ai_electronics_lab/planning/__init__.py
src/ai_electronics_lab/planning/openrouter.py
src/ai_electronics_lab/planning/planner.py
tests/planning/test_openrouter.py
tests/planning/test_planner.py
uv.lock
```

Explicitly excluded:

```text
.gitignore
README.md
src/ai_electronics_lab/contracts/**
src/ai_electronics_lab/simulation/**
src/ai_electronics_lab/verification/**
src/ai_electronics_lab/web/**
tests/web/**
```

## Implementation sequence

1. Freeze this specification and documentation checkpoint.
2. Add configuration and stable error contracts.
3. Add the bounded OpenRouter HTTP adapter.
4. Add provider-envelope parsing.
5. Add exact candidate decoding and CircuitPlan validation.
6. Add one bounded repair path.
7. Add mocked transport tests.
8. Update `.env.example`, dependency metadata, and `uv.lock`.
9. Run focused and complete verification.
10. Inspect the exact allowlist diff before staging.

## Explicit exclusions

PR #13 does not:

- modify the web API or browser UI;
- run ngspice;
- construct simulation assemblies or decks;
- create or accept raw netlist text;
- execute shell commands or subprocesses;
- select arbitrary tools;
- use OpenRouter plugins;
- persist prompts or responses;
- create trusted simulation or verification evidence;
- generate final engineering explanations;
- add offline planner behavior;
- add an ADK workflow, MCP server, CLI, deployment surface, or evaluation service;
- stage, commit, push, open, or merge itself.
