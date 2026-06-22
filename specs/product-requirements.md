# Product requirements

## Goal

Turn a natural-language electronics request into reproducible engineering evidence.

## Required topologies

1. RC low-pass filter
2. RC high-pass filter
3. Resistive voltage divider

BJT support is deferred.

## Required result

A successful run must include:

- interpreted intent;
- structured circuit plan;
- topology and component values;
- assumptions and caveats;
- deterministic validation status;
- generated SPICE netlist;
- ngspice execution status;
- numerical checkpoints;
- analytical comparison;
- schematic or readable circuit representation;
- plot and downloadable artifacts;
- concise execution trace;
- final PASS, WARN, or FAIL status.

## Failure behavior

Unsupported, unsafe, or materially ambiguous requests must not receive fabricated results.
They must return FAIL or request bounded clarification.

## Operation modes

- `offline`: deterministic demonstration without an LLM API key;
- `live`: planner, verifier, and explainer use a configured model provider.

Offline output must never be presented as a live model run.
