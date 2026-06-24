# Structured OpenRouter Plan Tool Output

## Purpose

The live OpenRouter planner must not rely on prompt wording alone to produce the strict six-field
`CircuitPlan` candidate. The provider request forces one fixed function call while the existing
deterministic `CircuitPlan` validation remains the final authority.

## Provider request

The request keeps the existing bounded model, timeout, token, TLS, redirect, proxy-isolation,
body-size, and response-size controls. It additionally sends:

- exactly one function tool named `submit_circuit_plan`;
- the topology-specific plan JSON Schema as that tool's `parameters`;
- an exact `tool_choice` forcing `submit_circuit_plan`;
- `provider.require_parameters = true` so OpenRouter selects only endpoints supporting `tools` and
  `tool_choice`.

The request does not send `response_format`. The default free model's current OpenRouter endpoint
accepts forced tool calls but rejects the `json_schema` response-format parameter with
`No endpoints found that can handle the requested parameters`.

The tool schema root is an exact object containing one `plan` property. That property is a nested
`anyOf` covering exactly these supported variants:

1. `rc_low_pass` with `analysis = "ac"`, resistance, capacitance, and AC frequencies;
2. `rc_high_pass` with `analysis = "ac"`, resistance, capacitance, and AC frequencies;
3. `resistive_divider` with `analysis = "dc"`, input voltage, top resistance, bottom resistance, and
   an empty frequency list.

Each variant rejects additional fields and uses numeric SI-base-unit values.

## Deterministic defaults

An underspecified demonstration prompt uses these planner defaults:

- RC low-pass or high-pass: `1000` ohms, `0.000001` farads, frequencies `[10, 100, 1000]` hertz;
- resistive divider: `5` volts, `1000` ohms top, `1000` ohms bottom.

These defaults create a demonstrable plan; they do not bypass deterministic validation.

## Candidate boundary

The accepted provider envelope must contain exactly one choice whose finish reason is `tool_calls`.
Its message must contain no parallel prose and exactly one function call named
`submit_circuit_plan`. The bounded function `arguments` string must decode to either:

```json
{"plan":{"schema_version":"1.0","topology":"rc_low_pass","analysis":"ac","parameters":{"resistance_ohms":1000,"capacitance_farads":0.000001},"requested_frequencies_hz":[10,100,1000],"assumptions":[]}}
```

or the already-valid legacy exact six-field candidate shape. Both shapes are converted to the same
compact candidate JSON and passed through the existing `_candidate_to_plan()` and
`require_valid_circuit_plan()` path.

Unknown wrapper fields, Markdown, prose content, missing or multiple tool calls, unexpected tool
names, malformed JSON, duplicate keys, non-finite numbers, unsupported topologies, invalid parameter
combinations, unordered frequencies, and invalid assumptions remain rejected.

## Repair

At most one repair request is allowed. Repair input contains only:

- the original bounded prompt;
- stable validation error codes;
- stable bounded paths.

The repair request forces the same fixed tool. Raw model output, provider metadata, credentials,
exception text, and invalid values are not copied into the repair prompt or public errors.

## Acceptance

The implementation must verify with mocked transport tests that:

- the request omits `response_format`, defines one bounded tool, forces its exact name, and requires
  provider parameter support;
- a valid forced-tool low-pass candidate returns a validated `CircuitPlan`;
- a semantic validation failure can be repaired once using only stable context;
- an unexpected tool name or parallel prose content is rejected;
- wrapper objects with extra keys are rejected;
- underspecified demonstration prompts receive deterministic defaults;
- the complete existing Ruff and pytest suites remain green.
