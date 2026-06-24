# Acceptance scenarios

## RC low-pass

**Given** a configured OpenRouter planner and local ngspice
**When** the user requests a supported RC low-pass circuit with valid component values and
frequencies
**Then** the system returns HTTP 200, a validated `rc_low_pass` plan, parsed measurements, a
schematic, a completed safe trace, and a deterministic verdict.

## RC high-pass

**Given** a configured OpenRouter planner and local ngspice
**When** the user requests a supported RC high-pass circuit with valid component values and
frequencies
**Then** the system returns HTTP 200, a validated `rc_high_pass` plan, parsed measurements, a
schematic, a completed safe trace, and a deterministic verdict.

## Resistive divider

**Given** a configured OpenRouter planner and local ngspice
**When** the user requests an unloaded resistive divider with valid input voltage and resistor
values
**Then** the system returns HTTP 200, a validated `resistive_divider` plan, parsed DC measurements,
a schematic, a completed safe trace, and a deterministic verdict.

## Unsupported request

**When** the user requests an unsupported topology or asks the model to supply arbitrary SPICE,
commands, paths, tools, or evidence
**Then** the request fails safely without fabricated simulation results or expanded model authority.

## Missing ngspice

**Given** no trusted ngspice executable is available
**When** a simulation reaches the execution boundary
**Then** the system returns a stable execution failure and does not claim that simulation or
verification completed.

## Provider or configuration failure

**Given** the OpenRouter API key is absent, configuration is invalid, or the provider is unavailable
**When** a natural-language request is submitted
**Then** the system returns a stable planner failure without exposing the key, provider body, or
internal exception details.

## Hostile or malformed input

**When** an HTTP request contains malformed JSON, duplicate keys, non-finite values, unexpected
fields, invalid UTF-8, unsupported compression, control characters, or an oversized prompt
**Then** the bounded HTTP and orchestration layers reject it before unsafe downstream processing.

## Deferred scenarios

Plots, downloadable artifact bundles, prose explanations, what-if comparison, parent/child runs,
persistence, memory, MCP, and cloud deployment are outside the finished product scope.
