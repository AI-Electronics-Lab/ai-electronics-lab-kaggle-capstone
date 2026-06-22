# RC high-pass topology

## Scope

The deterministic RC high-pass block is exactly:

```text
VIN -- C1 -- VOUT
              |
              R1
              |
             GND
```

`C1` is the series capacitor from input to output. `R1` is the shunt resistor from output
to ground. The inverse RC low-pass arrangement is invalid for this block.

## Contract

- capability identifier: `rc_high_pass`;
- archetype identifier: `rc_high_pass_vertical_slice`;
- topology identifier: `series_capacitor_shunt_resistor`;
- category: `filters`;
- maturity: `mvp`;
- ports: `VIN`, `VOUT`, and `GND` on three distinct nets;
- probes: `vin_voltage`, `vout_voltage`, and `transfer_function`;
- analyses: AC, DC, and transient;
- metrics: `cutoff_frequency_hz` and `time_constant_s`.

Resistance and capacitance are positive, finite numeric SI values. Booleans are not numeric
values. Node and graph names are non-empty, trimmed string tokens without whitespace. Input,
output, and ground node names must be distinct.

The graph contains only `C1` and `R1`. Neither component may connect both terminals to the same
node. Capability, archetype, port, probe, analysis, component-placement, and artifact metadata are
validated deterministically before the block is returned.

## Deterministic output

The reusable block exposes bounded default analyses consistent with the RC low-pass block:

- AC: 10 points per decade, 1 Hz through 1 MHz;
- DC: no sweep parameters;
- transient: 10 microsecond step through 10 milliseconds.

Circuit graph serialization, Netlist IR conversion, and SPICE rendering use the shared
deterministic core. This block does not parse prompts, adapt a `CircuitPlan`, execute ngspice, or
provide a schematic layout.
