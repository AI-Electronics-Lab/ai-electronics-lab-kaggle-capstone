# CircuitPlan contract

## Purpose

`CircuitPlan` is the canonical structured boundary between planning and deterministic
electronics code. It describes intent and canonical SI-unit values only. It is not a circuit
graph or a SPICE netlist.

## Version 1.0

The fields, in canonical serialization order, are:

1. `schema_version`: exactly `"1.0"`.
2. `topology`: `rc_low_pass`, `rc_high_pass`, or `resistive_divider`.
3. `analysis`: `ac` for RC filters and `dc` for a resistive divider.
4. `parameters`: exactly the parameter keys required by the selected topology.
5. `requested_frequencies_hz`: an immutable sequence of canonical hertz values.
6. `assumptions`: an immutable sequence of bounded plain-text statements.

RC filters require `resistance_ohms` and `capacitance_farads`. A resistive divider requires
`resistance_top_ohms`, `resistance_bottom_ohms`, and `input_voltage_volts`. Missing and unknown
keys are invalid.

## Deterministic boundaries

Only Python `int` and `float` values, excluding booleans, are numeric contract values. Values
must be finite and within these inclusive ranges:

- resistance: 1.0 through 1e9 ohms;
- capacitance: 1e-15 through 1.0 farads;
- frequency: 1e-6 through 1e9 hertz;
- input-voltage magnitude: greater than zero and no more than 1e6 volts.

An AC plan may omit requested frequencies. Supplied frequencies must contain no more than 32
finite numeric values and be strictly increasing, which also makes them unique. A DC plan must
not contain requested frequencies.

A plan may contain no more than 20 assumptions. Each assumption must be a trimmed, non-empty
string of no more than 240 characters and must not contain control characters. Nested mutable
containers are not contract values. Input mappings and sequences are defensively and recursively
frozen when a plan is constructed.

Validation errors have stable machine-readable codes, field paths, and human-readable messages.
`validate_circuit_plan()` returns all deterministic errors in stable order.
`require_valid_circuit_plan()` raises `CircuitPlanValidationError` when any errors are present.
Serialization is deterministic: parameter keys are sorted, field order is fixed, and JSON uses
compact separators without non-finite-number extensions.

## Exclusions

BJT circuits, arbitrary circuit graphs, netlist construction, simulation, and default frequency
sweep selection are outside this contract.
