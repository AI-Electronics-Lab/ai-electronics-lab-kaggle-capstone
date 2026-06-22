# Acceptance scenarios

## RC low-pass design

**Given** offline mode and ngspice are available
**When** the user requests a 1 kHz RC low-pass filter
**Then** the system selects the low-pass topology, derives valid component values,
builds the netlist deterministically, runs ngspice, and reports verified checkpoints.

## Explicit RC values

**Given** R = 1.6 kΩ and C = 100 nF
**When** the user requests a low-pass simulation
**Then** the calculated cutoff is approximately 995 Hz and the evidence records the
actual values used.

## High-pass design

**When** the user requests a 1 kHz RC high-pass filter
**Then** low frequencies are attenuated, the cutoff is near −3 dB, and high frequencies
approach unity gain.

## Voltage divider

**Given** R1 = 10 kΩ and R2 = 10 kΩ
**When** the user requests a voltage divider
**Then** the verified unloaded output ratio is approximately 0.5.

## What-if comparison

**Given** a completed RC-filter run
**When** the resistor is doubled
**Then** a child run is created and the new cutoff is compared with the parent run.

## Unsupported request

**When** the user requests an unsupported power-electronics design
**Then** the system returns FAIL without generating fabricated simulation evidence.

## Missing ngspice

**Given** ngspice is unavailable
**When** a live simulation is requested
**Then** the system reports the missing dependency clearly and does not claim that a
simulation completed.
