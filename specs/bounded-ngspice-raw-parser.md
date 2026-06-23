# Bounded ngspice raw parser

## Purpose

Version 1.0 parses only immutable runner evidence from the fixed ngspice execution policy:

```text
SimulationExecutionEvidence -> bounded ngspice binary raw parsing -> immutable structured voltage measurements
```

The parser does not execute ngspice, open paths, parse caller-provided files, accept parser
configuration, calculate electrical pass/fail status, produce explanations, persist artifacts, or
expose arbitrary raw metadata.

## Trust Boundary And Threat Model

`SimulationExecutionEvidence` is treated as untrusted even though the runner creates frozen
dataclasses. A caller may manually construct evidence or mutate frozen fields with
`object.__setattr__`, including version strings, run ordering, probe names, return codes, raw bytes,
stdout, stderr, and frequency metadata. The parser must validate the complete evidence structure
before binary unpacking.

Threats include malformed or oversized raw files, deceptive ASCII headers, duplicate or reordered
fields, appended plots, ASCII `Values:` mode, unsupported plot kinds, non-finite binary doubles,
frequency substitution, metadata leakage, and denial-of-service through unbounded counts or lines.

## Accepted Runner Evidence

The input object must be exactly `SimulationExecutionEvidence` with version exactly
`SIMULATION_RUNNER_VERSION`. `runs` must already be an exact immutable tuple, nonempty, and no
larger than `MAX_AC_RUNS`. Every item must be exactly `SimulationRunEvidence`.

All runs must use one coherent analysis. AC runs use trusted IDs `ac-01`, `ac-02`, and so on in
original order, trusted probe names `("transfer_function", "vin_voltage", "vout_voltage")`, return
code `0`, and a finite positive built-in `int` or `float` frequency, excluding `bool`, within the
existing frequency bounds. DC uses exactly one run with ID `dc-op`, trusted probe names
`("divider_ratio", "vin_voltage", "vout_voltage")`, return code `0`, and `frequency_hz=None`.

`stdout` and `stderr` must be exact strings but are not parsed or copied to parsed output.
`raw_output` must be exact bytes, nonempty, and no larger than 2 MiB.

Malformed evidence, including unexpected `AttributeError`, `IndexError`, `KeyError`, `TypeError`,
`ValueError`, and assertion failures, is normalized to `SimulationRawParseError`. Existing
`SimulationRawParseError` instances are preserved.

Second audit-remediation checkpoint: after validating the outer evidence container and every run
object type, the parser exact-type validates every field of every run before cross-run coherence
comparisons, hashing, indexing, formatting, iteration over untrusted field contents, or raw parsing.
A malformed second or later `analysis_kind` fails at `("runs", index, "analysis_kind")` before any
hostile comparison method can execute at the parser boundary.

Verification recorded for this checkpoint: `uv run pytest -q tests/simulation/test_raw_parser.py`
-> `79 passed in 0.17s`; `uv run pytest -q` -> `377 passed in 0.94s`; `uv run ruff check .` ->
`All checks passed!`; package import/signature smoke -> `1.0 SimulationRawParseError
SimulationComplexValue SimulationRunMeasurements SimulationParsedResults ['evidence']
SimulationParsedResults`.

Final audit-remediation checkpoint: `Binary:` and `Values:` are both recognized only as exact
complete ASCII header lines before binary payload selection. Ordinary header-field substrings,
including `Date: Binary:` and `Date: prefix Binary:`, do not affect delimiter selection. Binary
payload bytes remain opaque after the real delimiter is found and are inspected only by bounded
native-double unpacking. Trusted probe tuples are length-checked before element traversal, while
length-three tuples still exact-type validate every entry before comparison.

Verification recorded for this checkpoint: `uv run pytest -q tests/simulation/test_raw_parser.py`
-> `86 passed in 0.12s`; `uv run pytest -q` -> `384 passed in 0.97s`;
`uv run ruff check .` -> `All checks passed!`; package import/signature smoke ->
`1.0 SimulationRawParseError SimulationComplexValue SimulationRunMeasurements
SimulationParsedResults ['evidence'] True SimulationParsedResults`.

Integer-overflow remediation checkpoint: exact built-in integer frequencies are range-checked
directly without conversion to binary floating point. Exact built-in float frequencies still
require `math.isfinite()` before range checks. Huge positive or negative integer values therefore
fail as `SimulationRawParseError` at the precise `frequency_hz` path before raw parsing and cannot
escape as `OverflowError`.

## Accepted ngspice Binary Raw Grammar

Version 1.0 accepts one ngspice-42 raw plot per run as emitted by the fixed runner command:

```text
<trusted-ngspice> -n -b -r output.raw input.cir
```

The raw file contains an ASCII header, a `Binary:` delimiter line, and a native-endian IEEE-754
64-bit double payload. The parser uses the standard-library `struct` module with native byte order
and fixed eight-byte doubles. It rejects unsupported Python runtimes where `struct.calcsize("@d")`
is not 8 or finite double assumptions do not hold.

The accepted header order is exactly:

```text
Title: <title>
Date: <date>
Plotname: <plotname>
Flags: <flags>
No. Variables: <count>
No. Points: 1
Variables:
	0	<name>	<type>
	1	<name>	<type>
...
Binary:
```

The parser rejects empty files, oversized files, NUL or carriage return in the ASCII header,
non-ASCII header bytes, missing fields, duplicate fields, reordered fields, malformed lines,
oversized lines, appended plots, unsupported `Values:` ASCII mode, unsupported fields before
`Binary:`, and binary truncation or trailing bytes. Textual data-mode markers are recognized only
as exact complete ASCII header lines before the first valid `Binary:\n` delimiter, or before
missing-delimiter rejection when no binary delimiter exists. `Binary:` is also recognized only as
an exact complete ASCII header line. Header substrings such as `Date: Values:`,
`Date: Binary:`, and variable-row field values are ordinary header contents, and bytes after
`Binary:\n` are opaque binary payload until bounded native-double unpacking. `Date` is required only to match the bounded single-line
structure; it is never returned.

Variable indices must be contiguous beginning with zero. Variable names must be unique bounded safe
ASCII tokens of at most 128 bytes. Variable types must be bounded safe ASCII tokens of at most
64 bytes. At most 64 variables are accepted. `No. Points` must be exactly one.

## Inspected ngspice-42 Format

Local inspection of `/usr/bin/ngspice` on 2026-06-23 reported ngspice-42. The current runner
emitted these trusted headers:

- `Title: * rc_low_pass`, `Plotname: AC Analysis`, `Flags: complex`;
- `Title: * rc_high_pass`, `Plotname: AC Analysis`, `Flags: complex`;
- `Title: * resistive_divider`, `Plotname: Operating Point`, `Flags: real`.

AC low-pass variables were `frequency`, `v(vout)`, `v(vin)`, `i(v1)`. AC high-pass variables were
`frequency`, `v(vin)`, `v(vout)`, `i(v1)`. DC operating-point variables were `v(vin)`, `v(vout)`,
`i(v1)`.

The inspected AC binary payload contains two native doubles for each variable slot. The real
frequency double exactly matches the requested scalar. On this ngspice-42 build the frequency
imaginary slot is a finite subnormal placeholder rather than `0.0`; version 1.0 accepts exact zero
or a finite subnormal placeholder for that slot, and rejects normal nonzero frequency imaginary
values. All other ignored extra-vector doubles are still required to be finite.

## Fixed Bounds

Private constants define fixed parser bounds:

- maximum raw file: 2 MiB;
- maximum ASCII header: 64 KiB;
- maximum header line: 512 bytes;
- maximum variable count: 64;
- number of points: exactly one;
- maximum variable name: 128 ASCII bytes;
- maximum variable type: 64 ASCII bytes;
- run count: no greater than `MAX_AC_RUNS`.

These are not public caller parameters. Tests may monkeypatch private constants.

## Title, Plot, Flags, And Analysis Mapping

Topology is inferred only from the exact trusted raw title:

- `Title: * rc_low_pass` -> `rc_low_pass`;
- `Title: * rc_high_pass` -> `rc_high_pass`;
- `Title: * resistive_divider` -> `resistive_divider`.

RC titles are valid only for AC evidence. `resistive_divider` is valid only for DC evidence.
AC requires `Plotname: AC Analysis` and `Flags: complex`. DC operating point requires
`Plotname: Operating Point` and `Flags: real`. Unsupported plots, flags, topology/analysis
mismatches, duplicate headers, and appended plots are rejected.

## Required Vectors

AC requires exactly one `frequency` vector of type `frequency`, one `v(vin)` vector of type
`voltage`, and one `v(vout)` vector of type `voltage`. It parses complex `v(vin)` and `v(vout)`
values. The real frequency double must exactly equal `float(_format_scalar(run.frequency_hz))`,
matching the deterministic scalar rendered by the deck boundary. No engineering tolerance or
alternate endian recovery is applied.

DC operating point requires exactly one `v(vin)` vector of type `voltage` and one `v(vout)` vector
of type `voltage`. DC voltage imaginary components are represented as `0.0`.

Additional bounded vectors from trusted circuits, such as `i(v1)`, are parsed for binary shape and
finite doubles but are not returned.

## Immutable Parsed-Result Schema

`SimulationComplexValue` is a frozen slots dataclass with `real: float` and `imag: float`. Both
values must be finite built-in floats. It exposes deterministic `to_dict()` and canonical compact
`to_json()`.

`SimulationRunMeasurements` is a frozen slots dataclass with `run_id`, `topology`,
`analysis_kind`, `frequency_hz`, `vin_voltage`, and `vout_voltage`. AC preserves the trusted
requested frequency representation after validating the binary frequency. DC uses
`frequency_hz=None` and voltage imaginary components `0.0`. It exposes deterministic `to_dict()`
and canonical compact `to_json()`.

`SimulationParsedResults` is a frozen slots dataclass with `version` and tuple-backed `runs`. It
preserves run order and exposes deterministic `to_dict()` and canonical compact `to_json()`.

Parsed output excludes raw dates, filesystem data, stdout, stderr, elapsed time, arbitrary raw
vector names, raw headers, and raw bytes.

## Canonical JSON

All parsed dataclasses emit JSON with `json.dumps(..., sort_keys=True, separators=(",", ":"),
ensure_ascii=False, allow_nan=False)`. The returned Python string is UTF-8 text.

## Stable Structured Errors

`SimulationRawParseError` inherits `ValueError`, has `code`, `path`, and `message`, formats as
`<code> at <path>: <message>`, and exposes `to_dict()`.

Messages never embed raw header text, raw bytes, variable contents, stdout, stderr, dates,
temporary paths, environment values, or secrets.

Stable code categories include:

- `raw.evidence.malformed`;
- `raw.version.unsupported`;
- `raw.output.empty`;
- `raw.output.oversized`;
- `raw.header.invalid`;
- `raw.header.oversized`;
- `raw.format.unsupported`;
- `raw.title.invalid`;
- `raw.plot.invalid`;
- `raw.flags.invalid`;
- `raw.variables.invalid`;
- `raw.count.invalid`;
- `raw.payload.truncated`;
- `raw.payload.trailing`;
- `raw.vector.missing`;
- `raw.vector.duplicate`;
- `raw.value.non_finite`;
- `raw.frequency.mismatch`.

Paths identify precise evidence locations such as `("runs", index, "raw_output", "header")`,
`("runs", index, "raw_output", "variables")`, and `("runs", index, "frequency_hz")`.

## Public API

`ai_electronics_lab.simulation` exports:

- `SIMULATION_RAW_PARSER_VERSION = "1.0"`;
- `SimulationRawParseError`;
- `SimulationComplexValue`;
- `SimulationRunMeasurements`;
- `SimulationParsedResults`;
- `parse_simulation_execution_evidence(evidence: SimulationExecutionEvidence) -> SimulationParsedResults`.

The parser exposes no caller-controlled format, encoding, endian, path, variable-name, tolerance,
limit, or parser-configuration parameter.

## Explicit PR #9 Exclusions

PR #9 does not calculate transfer function, gain, magnitude, phase, cutoff frequency, divider
ratio, expected voltage, error, pass/fail status, plots, explanations, persistence, API behavior,
UI behavior, MCP behavior, agent behavior, dependency changes, deployment changes, or
caller-configurable parsing behavior.
