# Development log

## Initial extraction phase

- Created an isolated, user-owned private reference snapshot.
- Verified the snapshot against the selected production `origin/main` commit.
- Removed all Git remotes from the private reference snapshot.
- Confirmed production-only untracked files were not copied.
- Audited repository structure and static dependencies.
- Reviewed the three required topology knowledge files.
- Chose an allowlist-based extraction and compact local architecture.

## Deterministic core extraction

- Approved 26 source and focused-test files through the direct-copy allowlist.
- Verified every imported file against the private SHA-256 manifest.
- Confirmed zero critical findings in the pre-import content scan.
- Ran the isolated baseline test suite successfully before copying.
- Imported only the approved deterministic core and focused tests.
- Kept private Git history and production infrastructure outside this repository.

## Reproducible Python project foundation

- Added an installable `pyproject.toml` using the standard `src` package layout.
- Replaced repository-relative test imports with installed-package imports.
- Added a locked uv development environment.
- Added local verification for linting, tests, and package imports.
- Added GitHub Actions CI using the same locked environment.
- Deferred global line-length reformatting so this infrastructure change remains reviewable.

## Canonical CircuitPlan contract

- Specified the version 1.0 planner-to-deterministic-code boundary for the three initial topologies.
- Added an immutable standard-library contract with defensive copying, deterministic serialization,
  structured validation errors, and a raising validation helper.
- Added focused coverage for valid plans and deterministic rejection boundaries.

## Deterministic RC high-pass topology

- Added the series-capacitor, shunt-resistor RC high-pass topology block and registry descriptor.
- Added deterministic graph validation and SPICE connectivity coverage without extending schematic
  rendering or adding plan adaptation and simulation behavior.

## Deterministic resistive-divider topology

- Added the passive upper-resistor, lower-resistor divider topology and registry descriptor.
- Recorded source-independent divider ratio and Thevenin resistance metrics in deterministic graph
  metadata.
- Added DC-only graph validation and passive SPICE connectivity coverage without adding a voltage
  source, plan adaptation, or schematic changes.

## Deterministic CircuitPlan adapter

- Added validation-before-dispatch conversion from the canonical `CircuitPlan` to the three trusted
  topology builders using fixed input, output, and ground nodes.
- Preserved canonical plan data as inert provenance metadata while deferring sources, requested
  sweep construction, analysis execution, and divider input voltage to a later assembly layer.

## Deterministic simulation assembly

- Added validation-first assembly of trusted passive topology IR with exactly one fixed-policy
  voltage source and a typed, non-executable analysis request.
- Preserved canonical plan provenance and requested frequencies while keeping assumptions inert and
  deferring bounded analysis-directive rendering, simulator execution, and result handling to later
  layers.

## Bounded simulation-deck rendering

- Added defensive validation for manually constructed assemblies before executable analysis text is
  emitted.
- Expanded exact requested AC frequencies into bounded independent single-point decks and DC intent
  into one operating-point deck.
- Reused deterministic component rendering while preserving inert metadata and allowing only the
  generated analysis directive plus the final `.end`.

## Bounded ngspice runner

- Added the PR #8 specification for the deck-to-ngspice trust boundary, fixed execution policy,
  immutable evidence schema, byte/time bounds, cleanup behavior, and stable failure codes.
- Implemented `run_simulation_deck()` with defensive deck/netlist revalidation before executable
  resolution, fixed trusted ngspice candidates, fixed `-n -b -r output.raw input.cir` argv, isolated
  temporary working directories, minimal environment, bounded stdout/stderr/raw capture, and
  process-group termination.
- Added deterministic fake-executable coverage for success, failure, overflow, timeout, cleanup,
  validation-before-resolution, and public API constraints.
- Verification: `uv run pytest -q tests/simulation/test_runner.py` -> `32 passed in 0.40s`; `uv run pytest -q` -> `285 passed in 0.56s`; `uv run ruff check .` -> `All checks passed!`; import smoke -> `1.0 SimulationRunnerError SimulationRunEvidence SimulationExecutionEvidence True`.
- Local ngspice inspection: `/usr/bin/ngspice` exists and reports ngspice-42; `--help` confirms
  `-n` disables local/user config loading, `-b` batch mode, and `-r` rawfile output.


## PR #8 independent-audit remediation

- Reproduced the independent-audit concerns from the current runner implementation and kept changes
  confined to the PR #8 allowlisted files.
- Hardened process cleanup so descendant processes are terminated even when the process leader has
  already exited or been reaped, including before accepting successful output or reporting stable
  nonzero/raw-output failures.
- Added defensive exact-type validation and malformed-object exception normalization before
  executable resolution or temporary-directory creation.
- Required component numeric tokens to match deterministic scalar rendering after parse and bounds
  checks, rejecting noncanonical aliases such as `1_000`, `+1000`, `01000`, and `1e3`.
- Normalized process stream/selector/wait I/O failures to `runner.io.failed` without exposing
  underlying exception text or child output.
- Added deterministic fake-executable regression coverage for escaped descendants after both zero
  and nonzero leader exits, corrupted dataclass fields via `object.__setattr__`, noncanonical
  numeric aliases, and selector `OSError` cleanup.
- Verification: `uv run pytest -q tests/simulation/test_runner.py` -> `45 passed in 0.70s`;
  `uv run pytest -q` -> `298 passed in 0.84s`; `uv run ruff check .` ->
  `All checks passed!`; import smoke ->
  `1.0 SimulationRunnerError SimulationRunEvidence SimulationExecutionEvidence True`;
  `git diff --check` -> no output.

## Bounded ngspice raw parser

- Inspected `/usr/bin/ngspice` and confirmed ngspice-42. The current runner emits raw headers with `Title: * rc_low_pass` and `Title: * rc_high_pass` for AC, `Plotname: AC Analysis`, `Flags: complex`, `No. Points: 1`, and variable rows including `frequency`, `v(vin)`, `v(vout)`, and `i(v1)`; the observed AC binary payload uses native 64-bit doubles with complex slots. The inspected frequency real double matched the requested scalar exactly, while the frequency imaginary slot was a finite subnormal placeholder on this build.
- Inspected the divider operating-point raw output and confirmed `Title: * resistive_divider`, `Plotname: Operating Point`, `Flags: real`, one point, variables `v(vin)`, `v(vout)`, and `i(v1)`, and one native 64-bit double per real vector.
- Added the PR #9 parser-boundary specification before implementation, including trust boundary, accepted evidence, grammar, bounds, schema, canonical JSON, error contract, native double policy, AC/DC mapping, public API, and explicit exclusions.
- Implemented `parse_simulation_execution_evidence()` with exact evidence validation, bounded ASCII header parsing, native-double payload validation, finite-value checks, trusted title/analysis mapping, required-vector extraction, immutable parsed result dataclasses, canonical JSON, and stable structured parser errors.
- Added deterministic synthetic raw-format coverage plus optional real-ngspice plan -> assembly -> deck -> runner -> parser integration coverage for low-pass, high-pass, and divider cases.
- Verification: `uv run pytest -q tests/simulation/test_raw_parser.py` -> `74 passed in 0.11s`.
- Verification: `uv run pytest -q` -> `372 passed in 0.98s`.
- Verification: `uv run ruff check .` -> `All checks passed!`.
- Verification: package import/signature smoke -> `1.0 SimulationRawParseError SimulationComplexValue SimulationRunMeasurements SimulationParsedResults ['evidence'] SimulationParsedResults`.

## PR #9 independent-audit remediation

- Remediated the blocking raw-parser audit finding by locating the first exact `Binary:\n`
  delimiter before checking for unsupported textual data mode.
- Constrained `Values:` recognition to exact complete ASCII header lines before binary data, so
  header substrings such as `Date: Values:` are not treated as data-mode delimiters.
- Preserved binary payload opacity until bounded native-double unpacking; finite ignored-vector
  payload bytes containing `Values:` or `Values:\n` are parsed only as payload values and are not
  exposed in public measurements.
- Added deterministic synthetic regression coverage for portable native-double `Values:` payload
  collisions, exact-line ASCII `Values:` rejection, and `Date: Values:` binary-header acceptance.
- Verification: `uv run pytest -q tests/simulation/test_raw_parser.py` -> `77 passed in 0.12s`.
- Verification: `uv run pytest -q` -> `375 passed in 1.01s`.
- Verification: `uv run ruff check .` -> `All checks passed!`.
- Verification: package import/signature smoke -> `1.0 SimulationRawParseError
  SimulationComplexValue SimulationRunMeasurements SimulationParsedResults ['evidence']
  SimulationParsedResults`.
- Verification: `git diff --check` -> no output.

## PR #9 second independent-audit remediation

- Remediated the remaining validation-order finding by validating all run field types before
  comparing analysis kinds or enforcing cross-run AC/DC coherence.
- Added deterministic two-run AC regressions for a hostile second-run `analysis_kind` whose
  equality and inequality methods raise, and for a simple unhashable list value in the same field.
- Verified malformed second-run `analysis_kind` values fail with `raw.evidence.malformed` at
  `("runs", 1, "analysis_kind")`, hostile comparison methods are not invoked, and raw parsing is
  not reached.
- Verification: `uv run pytest -q tests/simulation/test_raw_parser.py` -> `79 passed in 0.17s`.
- Verification: `uv run pytest -q` -> `377 passed in 0.94s`.
- Verification: `uv run ruff check .` -> `All checks passed!`.
- Verification: package import/signature smoke -> `1.0 SimulationRawParseError
  SimulationComplexValue SimulationRunMeasurements SimulationParsedResults ['evidence']
  SimulationParsedResults`.
- Verification: `git diff --check` -> no output.

## PR #9 final independent-audit remediation

- Remediated the remaining delimiter-recognition finding by selecting the first exact complete
  `Binary:` header line only when it appears at byte offset zero or immediately after `\n`, with
  its terminating `\n`.
- Preserved exact complete-line `Values:` rejection before the real binary delimiter, while keeping
  ordinary header-field substrings such as `Date: Binary:` and `Date: prefix Binary:` inert for
  delimiter selection.
- Preserved binary payload opacity after the real delimiter; ignored-vector native-double bytes
  containing `Binary:\n` remain payload data and are not searched as headers.
- Hardened trusted probe validation so oversized tuples fail at `("runs", index, "probe_names")`
  by length before element traversal, while length-three tuples still exact-type validate all
  entries before tuple comparison.
- Added deterministic regressions for `Date: Binary:`, `Date: prefix Binary:`, binary-payload
  `Binary:\n`, variable-row `Binary:` substrings, missing real delimiters with `Date: Binary:`,
  standalone `Values:` rejection, early standalone `Binary:` malformed headers, and oversized probe
  tuples.
- Verification: `uv run pytest -q tests/simulation/test_raw_parser.py` -> `86 passed in 0.12s`.
- Verification: `uv run pytest -q` -> `384 passed in 0.97s`.
- Verification: `uv run ruff check .` -> `All checks passed!`.
- Verification: package import/signature smoke -> `1.0 SimulationRawParseError
  SimulationComplexValue SimulationRunMeasurements SimulationParsedResults ['evidence'] True
  SimulationParsedResults`.

## PR #9 integer-overflow remediation

- Separated exact built-in integer and float frequency validation.
- Exact integer frequencies are now positivity- and range-checked without conversion to a C double.
- Exact float frequencies continue to require finiteness before range validation.
- Added regressions proving huge positive and negative integers and booleans fail at
  `("runs", 0, "frequency_hz")` before raw parsing, without leaking `OverflowError`.
- Verification: `uv run pytest -q tests/simulation/test_raw_parser.py` -> `92 passed in 0.18s`.
- Verification: `uv run pytest -q` -> `390 passed in 0.94s`.
- Verification: `uv run ruff check .` -> `All checks passed!`.
- Verification: package import/signature smoke -> `1.0 SimulationRawParseError SimulationComplexValue SimulationRunMeasurements SimulationParsedResults ['evidence'] True SimulationParsedResults`.
- Verification: `git diff --check` and untracked-file whitespace checks -> `PASS`; source compile audit -> `PASS`.

## PR #10 minimal localhost UI — uncommitted implementation checkpoint

- Started feat/minimal-local-web-ui from merged PR #9 commit
  f30972a80ff22fc2457b232a450ecf6ceff6cca7.
- Wrote the UI specification before implementation.
- Selected exact structured fields rather than inventing a natural-language parser.
- Added one self-contained local page, one bounded JSON route, a thin deterministic
  orchestration service, safe stable error mapping, restricted browser headers, and a
  one-request execution limit.
- Reused CircuitPlan, simulation assembly, bounded deck generation, bounded ngspice execution,
  bounded raw parsing, and the existing engineering SVG renderer.
- Added focused route, service, security, output-disclosure, malformed-input, fake-pipeline, and
  optional real-ngspice tests.
- Added only bounded FastAPI and Uvicorn runtime dependencies and test-only HTTPX.
- No coding-agent CLI was invoked by this guarded edit block.
- This checkpoint must remain unstaged and uncommitted until independent audit and
  authorization.
- Remediated the initial PR #10 test-collection failure by assigning explicit stable pytest IDs to huge-integer cases, preventing Python's decimal string-conversion limit from being invoked by pytest parameter-name generation.
- Independent audit remediation replaced the deprecated HTTPX TestClient fallback with HTTPX2, narrowed FastAPI and Uvicorn to the tested minor release lines, and added wheel package-data plus live localhost verification evidence.

## PR #11 deterministic evidence verifier — specification checkpoint

- Created feat/deterministic-evidence-verifier from clean merged-main commit
  837ab6505480df1653aa23d0c77610431a9476fb.
- Confirmed the PR #10 UI process was stopped before starting the next milestone.
- Defined the verifier trust boundary, exact public API, input coherence rules, analytical RC
  and divider formulas, fixed tolerance policy, immutable schema, stable errors, web mapping,
  safe UI panel, acceptance tests, implementation boundaries, and explicit exclusions.
- Selected fixed comparison constants: absolute tolerance 1e-9, relative tolerance 1e-6,
  warning multiplier 10.0, and denominator floor 1e-12.
- Required scale-aware complex division, exact-type validation before arithmetic, deterministic
  JSON, and omission of raw or process evidence.
- No implementation source file, dependency, staging operation, commit, push, or pull request
  was created in this specification checkpoint.


## PR #11 deterministic evidence verifier — uncommitted implementation checkpoint

- Verified and preserved the existing branch, merge-base, decision record, development-log, and
  verifier-specification checkpoint before implementation.
- Added the public `ai_electronics_lab.verification` package with immutable result contracts,
  stable errors, exact-type hostile-boundary validation, fixed PASS/WARN/FAIL policy, analytical
  RC and divider models, scale-aware complex division, and canonical deterministic JSON.
- Extended the established pipeline after bounded raw parsing and before safe response generation.
- Added safe HTTP error mapping and deterministic verification fields without exposing raw or
  process evidence.
- Added a self-contained verification panel using DOM creation and `textContent`, plus core, web,
  hostile-input, serialization, browser-safety, and approved real-ngspice tests.
- Kept dependencies unchanged. Validation outputs are recorded in the timestamped PR #11 audit
  bundle. All implementation changes remain unstaged and uncommitted.

## PR #11 independent audit — remediation checkpoint

- Verified the uploaded audit ZIP against SHA-256
  `822fd7ed09610d18ea7bfd656340e2c72b878a18a4c1f81d6d33a74f90053dc3`.
- Reproduced a release-blocking trust-boundary defect: a `MappingProxyType` backed by a hostile
  mapping executed its custom iterator and escaped as `RuntimeError`.
- Reproduced public comparison-contract gaps that accepted an unknown metric, negative errors,
  zero limits, and incoherent status/reason combinations.
- Added exact backing-dict inspection without mapping-hook execution, strengthened comparison
  invariants, and added focused regression tests.
- The remediation remains unstaged and uncommitted pending server-side full-suite, Ruff,
  compilation, ngspice, wheel, and audit verification.
