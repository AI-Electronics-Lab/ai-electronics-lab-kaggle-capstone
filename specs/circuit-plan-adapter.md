# CircuitPlan adapter

## Purpose

The deterministic adapter connects the validated planning contract to trusted topology builders:

```text
CircuitPlan -> deterministic validation -> trusted topology builder -> CircuitGraph
```

It builds a reusable passive topology graph only. It does not assemble sources, execute analyses,
select frequency sweeps, construct netlists directly, or run ngspice.

## Version and API

Adapter version `1.0` exports:

- `CIRCUIT_PLAN_ADAPTER_VERSION`;
- `build_circuit_graph_from_plan(plan)`.

The function calls `require_valid_circuit_plan(plan)` before reading topology parameters or
selecting a builder. Existing `CircuitPlanValidationError` instances and their structured errors
cross this boundary unchanged. Invalid plans never reach a topology builder.

## Trusted dispatch

The adapter supports exactly the version 1.0 plan topologies and calls their existing builders:

- `rc_low_pass`: resistance and capacitance;
- `rc_high_pass`: resistance and capacitance;
- `resistive_divider`: top and bottom resistance only.

Every call uses fixed nodes `vin`, `vout`, and `0`. Plans cannot provide node names, component
reference designators, component kinds, connectivity, graph names, analysis names, probe names,
artifact paths, executable text, or dynamic imports. The adapter does not create voltage or current
sources.

## Provenance metadata

The adapter passes only these adapter-owned metadata fields:

- `circuit_plan_adapter_version`: `"1.0"`;
- `validated_circuit_plan`: the canonical result of `plan.to_dict()`.

The snapshot preserves schema version, topology, requested analysis, canonical parameters,
requested frequencies, and assumptions. For a divider it also preserves `input_voltage_volts`,
which is not passed to the passive topology builder and is not used to calculate output voltage.

Requested frequencies remain metadata only. RC topology blocks retain their existing analysis
capability declarations; the adapter does not create a sweep. Divider plans retain requested DC
analysis metadata while their graph remains DC-only.

Validated assumptions are inert metadata. They are never interpreted as SPICE directives,
filenames, paths, shell commands, code, or component definitions. Deterministic SPICE rendering may
show the serialized provenance only on comment lines.
