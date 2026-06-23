# Bounded ngspice runner

## Purpose

Version 1.0 executes only a defensively revalidated `SimulationDeck` through a fixed,
bounded ngspice subprocess boundary:

```text
SimulationDeck -> bounded ngspice execution -> immutable raw execution evidence
```

The runner does not parse electrical results, produce plots, verify circuit behavior, explain
results, persist artifacts, or accept caller-controlled execution settings.

## Trust Boundary And Threat Model

`SimulationDeck` values are treated as untrusted even though the deck layer creates frozen
dataclasses. A caller may manually construct or mutate objects containing arbitrary text, paths,
directives, nodes, devices, numbers, output probes, run IDs, or analysis metadata. The runner must
reject malformed decks before resolving ngspice, creating a temporary directory, writing input, or
starting a process.

The primary threats are command/path injection, ngspice startup-file loading, inherited secret
environment values, unbounded stdout/stderr/raw output, long-running or descendant processes,
multiline directive injection, arbitrary netlist devices, arbitrary include/control/shell behavior,
and evidence mutation after execution.

## Accepted SimulationDeck Structure

The input object must be exactly a `SimulationDeck` with string version
`SIMULATION_DECK_VERSION`, and `runs` must already be an exact immutable tuple. The run count must
be nonzero and must not exceed `MAX_AC_RUNS`. Every item must be exactly a `SimulationDeckRun`.
Malformed or manually corrupted dataclass fields are normalized to `SimulationRunnerError` before
executable resolution or temporary-directory creation.

All runs must belong to one coherent analysis:

- AC runs use IDs `ac-01`, `ac-02`, and so on in original order.
- DC contains exactly one run with ID `dc-op`.
- AC probes must be exactly `("transfer_function", "vin_voltage", "vout_voltage")`.
- DC probes must be exactly `("divider_ratio", "vin_voltage", "vout_voltage")`.
- AC frequencies must be finite positive exact int or float values, excluding booleans, within
  the existing CircuitPlan frequency bounds, and must exactly match the `.ac lin 1 f f` directive
  after deterministic scalar formatting.
- DC frequency must be `None` and must use `.op`.

Each `netlist_text` must be a UTF-8 encodable string of at most 64 KiB, without NUL, carriage
return, blank lines, or a trailing newline. The first line must be exactly one of:

- `* rc_low_pass`
- `* rc_high_pass`
- `* resistive_divider`

Metadata lines must remain comments beginning with `* metadata: `. Component lines, order,
reference designators, nodes, source form, and numeric ranges must match only the trusted
topologies:

- `rc_low_pass`: `C1 vout 0 C`, `R1 vin vout R`, `V1 vin 0 AC 1 0`
- `rc_high_pass`: `C1 vin vout C`, `R1 vout 0 R`, `V1 vin 0 AC 1 0`
- `resistive_divider`: `R1 vin vout Rtop`, `R2 vout 0 Rbottom`, `V1 vin 0 DC V`

Only positive finite resistance/capacitance values inside the existing contract bounds are accepted.
The divider DC source accepts finite nonzero magnitude inside the existing input-voltage bound.
After numeric parsing and range checks, every component numeric token must exactly equal the
current deterministic scalar rendering of the parsed value; aliases such as Python underscores,
explicit plus signs, leading-zero spellings, and exponential forms are rejected unless they are the
exact canonical renderer output. The only executable directives are the exact matching single-point
`.ac lin 1 f f` or `.op`, followed by exactly one final `.end`.

The runner rejects `.include`, `.lib`, `.control`, `.shell`, `.save`, arbitrary devices, arbitrary
nodes, extra directives, malformed values, booleans, NaN, infinity, topology/analysis mismatches,
NUL, carriage returns, blank executable lines, trailing newlines, and multiline injection attempts.

## Public API

`ai_electronics_lab.simulation` exports:

- `SIMULATION_RUNNER_VERSION = "1.0"`
- `SimulationRunnerError`
- `SimulationRunEvidence`
- `SimulationExecutionEvidence`
- `run_simulation_deck(deck: SimulationDeck) -> SimulationExecutionEvidence`

`run_simulation_deck()` accepts no public executable, command, path, environment, timeout,
working-directory, subprocess-argument, or runner-configuration parameter. It validates the complete
deck before resolving or starting ngspice, executes runs sequentially in original order, returns
evidence only when every run succeeds, and stops at the first failure with `SimulationRunnerError`.

## Executable And Subprocess Policy

The private candidate executable policy is fixed:

1. `/usr/bin/ngspice`
2. `/usr/local/bin/ngspice`

The runner does not search caller input or inherited `PATH`. A candidate must be an executable
regular file. The candidate tuple remains private and monkeypatchable for tests.

The fixed subprocess argument vector is:

```text
<trusted-ngspice> -n -b -r output.raw input.cir
```

`-n` suppresses local and user startup configuration, `-b` runs batch mode, and `-r` writes the raw
output file. The runner uses no shell and no command string.

Each run uses a private temporary working directory. The only netlist input path is `input.cir`; the
only raw output path is `output.raw`. Only the already validated complete deck text is written to
the input file.

The subprocess is started with `shell=False`, an explicit argument list, `close_fds=True`,
`start_new_session=True`, `cwd` set to the private temporary directory, and a minimal environment:

- `HOME=<private-temporary-directory>`
- `TMPDIR=<private-temporary-directory>`
- `LANG=C`
- `LC_ALL=C`

No `PATH`, API key, token, proxy setting, Python variable, caller `HOME`, or inherited environment
value is forwarded.

## Bounds, Termination, And Cleanup

Private module constants define the fixed limits:

- maximum trusted input deck size: 64 KiB per run;
- maximum captured stdout: 256 KiB per run;
- maximum captured stderr: 256 KiB per run;
- maximum raw output file: 2 MiB per run;
- per-run timeout: 10 seconds;
- total execution timeout across the complete deck: 60 seconds;
- run count: never greater than `MAX_AC_RUNS`.

These limits are not public parameters. Tests may monkeypatch private constants.

The runner continuously drains stdout and stderr with hard byte caps and monitors the raw output
file while the process is running where practical. On timeout, overflow, I/O failure, interruption,
or process-start failure after partial start, it terminates the complete process group and then
cleans up the private temporary directory. The process-group ID is the started process PID because
`start_new_session=True`; leader exit or reaping is never treated as proof that descendants are
gone. After normal stdout/stderr draining and direct-child completion, the runner still sends
bounded TERM/KILL cleanup to the process group before accepting success or raising for nonzero exit
or raw-output errors. The runner refuses to signal the caller's process group. Final raw output size
is enforced before bytes are read.

## Immutable Evidence Schema

`SimulationRunEvidence` is a frozen slots dataclass:

- `run_id: str`
- `analysis_kind: Literal["ac", "dc"]`
- `frequency_hz: float | int | None`
- `probe_names: tuple[str, ...]`
- `returncode: int`
- `stdout: str`
- `stderr: str`
- `raw_output: bytes`

`probe_names` is defensively converted to a tuple. `to_dict()` serializes `raw_output` as
deterministic standard Base64 text under `raw_output_base64`. `to_json()` emits canonical compact
UTF-8 JSON with sorted keys, compact separators, and `allow_nan=False`.

`SimulationExecutionEvidence` is a frozen slots dataclass:

- `version: str`
- `runs: tuple[SimulationRunEvidence, ...]`

`runs` is defensively converted to a tuple. Dict and JSON serialization are deterministic. Version
1.0 evidence deliberately excludes elapsed wall-clock time because timing is nondeterministic and
not required by the future electrical parser.

## Stable Error Codes

`SimulationRunnerError` inherits `RuntimeError`, has `code`, `path`, and `message` attributes,
formats as `<code> at <path>: <message>`, exposes `to_dict()`, and never embeds uncontrolled child
output, temporary paths, inherited environment values, or secrets in its message.

Malformed decks, including manually corrupted frozen dataclasses, must fail as
`SimulationRunnerError` rather than leaking raw `TypeError`, `AttributeError`, `KeyError`,
`IndexError`, `ValueError`, or assertion failures. Process pipe, selector, wait, and relevant
cleanup `OSError` failures are normalized to `runner.io.failed` without embedding exception text,
temporary paths, environment values, or child output.

Stable failure categories include:

- `runner.deck.malformed`
- `runner.version.unsupported`
- `runner.executable.missing`
- `runner.executable.invalid`
- `runner.io.failed`
- `runner.subprocess.start_failed`
- `runner.timeout.per_run`
- `runner.timeout.total`
- `runner.stdout.overflow`
- `runner.stderr.overflow`
- `runner.raw_output.overflow`
- `runner.exit.nonzero`
- `runner.raw_output.missing`

Paths identify precise locations such as `("runs", index, "netlist_text")` where applicable.

## Fake-Executable Test Seam

Tests may monkeypatch the private executable candidate tuple to point at a controlled fake
executable, and may monkeypatch private timeout or byte-limit constants to exercise limits quickly.
This is not a public runner configuration API.

## Explicit PR #8 Exclusions

This boundary does not implement electrical result parsing, analytical verification, waveform
plots, natural-language explanations, persistence, API behavior, UI behavior, MCP behavior, agent
behavior, dependency changes, deployment changes, or caller-configurable execution settings.
