# Resistive divider topology

## Scope

The deterministic unloaded resistive divider block is exactly:

```text
VIN -- R1 -- VOUT
              |
              R2
              |
             GND
```

`R1` is the upper resistor from input to output. `R2` is the lower resistor from output to
ground. The block is a passive reusable subgraph and contains no voltage source.

## Contract

- capability identifier: `resistive_divider`;
- archetype identifier: `resistive_divider_vertical_slice`;
- topology identifier: `series_resistor_shunt_resistor`;
- category: `passive_networks`;
- maturity: `mvp`;
- ports: `VIN`, `VOUT`, and `GND` on three distinct nets;
- probes: `vin_voltage`, `vout_voltage`, and `divider_ratio`;
- supported analysis: DC only;
- metrics: `divider_ratio` and `thevenin_resistance_ohms`.

Both resistances are positive, finite numeric SI values. Booleans are not numeric values. Node
and graph names are non-empty, trimmed string tokens without whitespace. Input, output, and ground
node names must be distinct.

The graph contains only `R1` and `R2`, and neither resistor may connect both terminals to the same
node. Capability, archetype, topology, port, probe, analysis, component-placement, and artifact
metadata are validated deterministically before the block is returned.

## Deterministic metrics

For top resistance `R1` and bottom resistance `R2`:

```text
divider_ratio = R2 / (R1 + R2)
thevenin_resistance_ohms = (R1 * R2) / (R1 + R2)
```

Canonical resistance values and both calculated metrics are stored in graph metadata. Output
voltage is not calculated because this passive block does not own an input source.

## Deterministic output

The graph declares exactly one analysis named and typed `dc`, with an empty parameter mapping and
bias-domain metadata. Circuit graph serialization, Netlist IR conversion, and SPICE rendering use
the shared deterministic core. This block does not parse prompts, adapt a `CircuitPlan`, execute
ngspice, or modify schematic rendering and layout.
