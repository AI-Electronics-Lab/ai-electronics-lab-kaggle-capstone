# Bounded simulation deck

## Purpose and API

Version 1.0 expands a validated `SimulationAssembly` into an immutable ordered tuple of complete,
independent ngspice input decks. The public API exports `SIMULATION_DECK_VERSION`, `MAX_AC_RUNS`,
`SimulationDeckError`, `SimulationDeckRun`, `SimulationDeck`, and
`build_simulation_deck_from_assembly()`. Errors have stable code, path, and message fields. Dict and
canonical compact JSON serialization are deterministic.

## Bounded trusted expansion

AC requests contain one through `MAX_AC_RUNS` finite positive numeric frequencies, excluding
booleans. Exact values and order are preserved. Each creates one independent run using
`.ac lin 1 <frequency> <frequency>`. No points are added, removed, reordered, interpolated, or
deduplicated. DC contains no frequencies and creates one run using `.op`; its assembled voltage,
including a valid negative value, is preserved. No `.dc` sweep is emitted. Frequencies, passive
component values, and DC source magnitude are rechecked against the CircuitPlan version 1.0 numeric
bounds so a manually constructed assembly cannot bypass the canonical contract.

The boundary revalidates assembly version, analysis kind, frequency bounds, trusted sorted probes,
fixed nodes, trusted topology components and order, and fixed `V1` source policy. Component text
comes only from the existing renderer and must have single-line fields and exactly one terminal
`.end` with no other directive. Only trusted `.ac` or `.op` is inserted. Metadata and assumptions
remain comment-prefixed. This layer has no simulator, shell, filesystem, import, or subprocess API.
