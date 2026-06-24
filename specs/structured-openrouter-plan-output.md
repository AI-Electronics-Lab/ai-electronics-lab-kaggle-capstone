# Flat OpenRouter Circuit-Value Tool Output

## Purpose

The live OpenRouter planner must not be trusted to author the nested six-field `CircuitPlan`
shape directly. The provider is used only to extract a small flat set of circuit values. Local
deterministic code then constructs the canonical `CircuitPlan` and runs the existing validator.

## Live finding

The default free model accepts one forced function tool, but it did not reliably follow the prior
nested `anyOf` schema. For the same explicit RC low-pass prompt, two consecutive bounded attempts
returned invented nested fields such as `circuit_type`, `components`, and nested `analysis` data.

A live probe with a flat seven-field tool schema returned exactly the required keys and correct SI
values:

```json
{
  "topology": "rc_low_pass",
  "resistance_ohms": 1000,
  "capacitance_farads": 0.000001,
  "input_voltage_volts": 0,
  "resistance_top_ohms": 0,
  "resistance_bottom_ohms": 0,
  "requested_frequencies_hz": [10, 100, 1000]
}
```

## Provider request

The request retains the existing bounded model, timeout, token, TLS, redirect, proxy-isolation,
body-size, response-size, and one-repair controls. It sends:

- exactly one function tool named `submit_circuit_plan`;
- one flat object schema with seven required fields;
- an exact `tool_choice` forcing `submit_circuit_plan`;
- `provider.require_parameters = true`;
- no `response_format`.

The seven fields are:

1. `topology`;
2. `resistance_ohms`;
3. `capacitance_farads`;
4. `input_voltage_volts`;
5. `resistance_top_ohms`;
6. `resistance_bottom_ohms`;
7. `requested_frequencies_hz`.

Every field is required and additional properties are forbidden.

## Zero policy

The flat schema has one stable shape for every topology.

For `rc_low_pass` and `rc_high_pass`:

- `resistance_ohms` and `capacitance_farads` carry the requested values;
- `input_voltage_volts`, `resistance_top_ohms`, and `resistance_bottom_ohms` must be exact finite
  numeric zero;
- `requested_frequencies_hz` must contain positive, unique, strictly increasing frequencies.

For `resistive_divider`:

- `input_voltage_volts`, `resistance_top_ohms`, and `resistance_bottom_ohms` carry the requested
  values;
- `resistance_ohms` and `capacitance_farads` must be exact finite numeric zero;
- `requested_frequencies_hz` must be empty.

Nonzero, boolean, non-finite, or nonnumeric irrelevant fields are rejected locally.

## Deterministic construction

Provider tool arguments remain untrusted JSON. After exact bounded decoding and exact-key checks,
local code derives:

- `schema_version = "1.0"`;
- `analysis = "ac"` for RC topologies or `"dc"` for a divider;
- the topology-specific `parameters` mapping;
- `assumptions = []`.

Only relevant flat values are copied into the canonical candidate. The result is serialized and
passed through the existing `_candidate_to_plan()` and `require_valid_circuit_plan()` path.

The model does not choose schema versions, analyses, parameter names, assumptions, topology
connectivity, netlists, simulator commands, evidence, verification results, or engineering verdicts.

## Compatibility

The response parser continues to accept the previously supported exact legacy `{"plan": ...}`
wrapper and exact six-field candidate shape. Those compatibility forms remain subject to exact-key
checks and the same deterministic validator. Invented nested plan structures remain rejected.

## Envelope boundary

The accepted provider response must contain:

- exactly one choice;
- `finish_reason = "tool_calls"`;
- no parallel prose content;
- exactly one function call;
- the exact function name `submit_circuit_plan`;
- one bounded nonempty argument string.

Malformed JSON, duplicate keys, non-finite numbers, extra or missing flat keys, unexpected tools,
multiple calls, prose content, unsupported topologies, invalid values, invalid irrelevant-field
zeros, unordered frequencies, and all invalid canonical plans are rejected.

## Repair

At most one repair request is allowed. Repair input contains only:

- the original bounded prompt;
- stable validation error codes;
- stable bounded paths.

Raw invalid values, raw model output, provider metadata, credentials, exception text, and private
configuration are not copied into repair prompts or public errors.

## Deterministic defaults

An underspecified demonstration prompt uses these planner defaults:

- RC low-pass or high-pass: `1000` ohms, `0.000001` farads, frequencies `[10, 100, 1000]` hertz;
- resistive divider: `5` volts, `1000` ohms top, `1000` ohms bottom.

Defaults remain untrusted provider output until deterministic construction and validation complete.

## Acceptance

The implementation must verify with mocked transport tests that:

- the request defines one exact flat tool, forces its name, omits `response_format`, and requires
  provider parameter support;
- valid flat RC and divider values become canonical validated `CircuitPlan` objects;
- nonzero irrelevant fields are rejected and can use the single bounded repair attempt;
- semantic validation failures can repair using only stable context;
- extra, missing, or invented nested fields are rejected;
- unexpected tool names and parallel prose are rejected;
- the exact bounded legacy plan wrapper remains compatible;
- the complete Ruff and pytest suites remain green;
- all three live natural-language UI examples succeed before explanation-layer work resumes.
