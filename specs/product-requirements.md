# Product requirements

## Goal

Turn one bounded natural-language electronics request into reproducible engineering evidence for a
small frozen set of circuit topologies.

## Supported topologies

1. RC low-pass filter
2. RC high-pass filter
3. Unloaded resistive voltage divider

All other topologies are unsupported in the finished capstone.

## Successful result

A successful natural-language run must include:

- an accepted and bounded user prompt;
- a structured and validated `CircuitPlan`;
- the selected topology and component values;
- deterministic validation status;
- a deterministically generated SPICE deck;
- bounded local ngspice execution;
- parsed numerical measurements;
- an engineering schematic;
- a safe bounded stage trace;
- deterministic analytical verification;
- a final `PASS`, `WARN`, or `FAIL` verdict.

## Failure behavior

The system must fail safely when:

- the prompt is empty, oversized, malformed, or contains prohibited control data;
- the provider configuration is absent or invalid;
- the provider request fails or returns invalid candidate data;
- the requested topology is unsupported;
- deterministic plan validation fails;
- ngspice is unavailable or execution fails;
- raw evidence cannot be parsed;
- analytical verification cannot be completed safely.

A failure must use stable structured errors and must not expose credentials, raw provider responses,
child-process output, temporary paths, environment values, or exception internals.

## Natural-language operation

Natural-language planning is a live OpenRouter operation and requires an API key and network access.
There is no offline natural-language planning mode.

The deterministic validation, assembly, deck, simulation, parsing, verification, and test layers are
separate from the model and can be exercised directly without granting the model additional
authority.

## Explicitly deferred or excluded

The finished product does not require:

- plots;
- downloadable artifact bundles;
- what-if comparison;
- parent/child runs;
- prose explanations;
- persistence or memory;
- MCP;
- cloud deployment;
- unsupported circuit topologies.
