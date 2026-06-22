# Deterministic simulation assembly

## Purpose

The assembly layer prepares bounded simulation input without executing a simulator:

```text
validated CircuitPlan -> trusted passive topology -> trusted source -> typed analysis request
```

Its output contains an immutable `NetlistIR` component deck with exactly one trusted voltage
source and a typed `SimulationAnalysis`. It does not generate executable analysis directives or
run ngspice.

## Version and API

Assembly version `1.0` exports:

- `SIMULATION_ASSEMBLY_VERSION`;
- `SimulationAnalysis`;
- `SimulationAssembly`;
- `build_simulation_assembly_from_plan(plan)`.

The build function calls `require_valid_circuit_plan(plan)` before reading plan topology,
parameters, or frequencies and before invoking the adapter or source builders. Existing
`CircuitPlanValidationError` data crosses the boundary unchanged.

## Trusted construction

The passive topology comes only from `build_circuit_graph_from_plan()`. The assembly does not
mutate that graph. It converts the passive graph to `NetlistIR`, builds one source in a separate
temporary graph, converts that source through `NetlistStatement.from_component()`, and creates a
new IR with statements sorted by reference designator.

The source always uses reference `V1`, positive node `vin`, and negative node `0`. These nodes must
already exist in the passive topology.

- RC filters use an AC source with magnitude `1.0` and phase `0.0`.
- Resistive dividers use a DC source whose voltage is the validated `input_voltage_volts`, including
  a valid negative value.

Planner data cannot provide source names, nodes, kinds, connectivity, directives, paths, commands,
or raw netlist text.

## Typed analysis

`SimulationAnalysis` contains only `kind`, immutable `requested_frequencies_hz`, and immutable
sorted `probe_names`.

- RC analysis kind is `ac`; requested frequencies are preserved exactly, including an empty tuple.
- Divider analysis kind is `dc`; requested frequencies are empty.
- Probe names come only from the trusted passive graph.

The assembly does not invent a sweep or execute an analysis.

## Metadata and rendering boundary

Passive IR metadata, including the canonical validated-plan provenance, is preserved. The assembly
adds trusted `simulation_assembly_version` and `simulation_source_policy` fields, using `unit_ac`
for RC filters and `plan_dc` for dividers. Assembly-owned fields take precedence.

Assumptions remain inert serialized metadata. The existing renderer emits a deterministic component
deck ending in `.end`; it does not emit `.ac`, `.op`, `.dc`, `.tran`, `.save`, `.print`, `.measure`,
`.control`, or `.include`. A later bounded renderer/execution layer will translate typed analysis
data into executable directives.
