# Structured OpenRouter Plan Output

## Purpose

The live OpenRouter planner must not rely on prompt wording alone to produce the strict six-field
`CircuitPlan` candidate. The provider request uses OpenRouter structured outputs while the existing
deterministic `CircuitPlan` validation remains the final authority.

## Provider request

The request keeps the existing bounded model, timeout, token, TLS, redirect, proxy-isolation, body-size,
and response-size controls. It additionally sends:

- `response_format.type = "json_schema"`;
- a strict JSON Schema named `bounded_circuit_plan`;
- `provider.require_parameters = true` so OpenRouter selects only providers supporting the requested
  structured-output parameter.

The schema root is an exact object containing one `plan` property. That property is a nested `anyOf`
covering exactly these supported variants:

1. `rc_low_pass` with `analysis = "ac"`, resistance, capacitance, and AC frequencies;
2. `rc_high_pass` with `analysis = "ac"`, resistance, capacitance, and AC frequencies;
3. `resistive_divider` with `analysis = "dc"`, input voltage, top resistance, bottom resistance, and an
   empty frequency list.

Each variant rejects additional fields and uses numeric SI-base-unit values.

## Deterministic defaults

An underspecified demonstration prompt uses these planner defaults:

- RC low-pass or high-pass: `1000` ohms, `0.000001` farads, frequencies `[10, 100, 1000]` hertz;
- resistive divider: `5` volts, `1000` ohms top, `1000` ohms bottom.

These defaults create a demonstrable plan; they do not bypass deterministic validation.

## Candidate boundary

The preferred provider content is an exact JSON object shaped as:

```json
{"plan":{"schema_version":"1.0","topology":"rc_low_pass","analysis":"ac","parameters":{"resistance_ohms":1000,"capacitance_farads":0.000001},"requested_frequencies_hz":[10,100,1000],"assumptions":[]}}
```

For compatibility with the original isolated planner tests and a provider that returns the already-valid
legacy shape, the adapter also accepts a direct exact six-field candidate. Both shapes are converted to
the same compact candidate JSON and passed through the existing `_candidate_to_plan()` and
`require_valid_circuit_plan()` path.

Unknown wrapper fields, Markdown, prose, malformed JSON, duplicate keys, non-finite numbers, unsupported
topologies, invalid parameter combinations, unordered frequencies, and invalid assumptions remain
rejected.

## Repair

At most one repair request is allowed. Repair input contains only:

- the original bounded prompt;
- stable validation error codes;
- stable bounded paths.

Raw model output, provider metadata, credentials, exception text, and invalid values are not copied into
the repair prompt or public errors.

## Acceptance

The implementation must verify with mocked transport tests that:

- the request contains strict `json_schema` structured output and `require_parameters = true`;
- a valid structured low-pass candidate returns a validated `CircuitPlan`;
- a semantic validation failure can be repaired once using only stable context;
- wrapper objects with extra keys are rejected;
- underspecified demonstration prompts receive deterministic defaults;
- the complete existing Ruff and pytest suites remain green.
