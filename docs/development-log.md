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

## PR #13 bounded OpenRouter planner — specification checkpoint

- Created `feat/bounded-openrouter-planner` from clean merged-main commit `c0e6c3ea9b999249033fe1a4b7987aed1d2963d3`.
- Confirmed `.gitignore` already ignores `.env` while allowing tracked `.env.example`.
- Defined the fixed OpenRouter endpoint, default model, environment contract, request and response
  bounds, transport deadlines, provider-envelope checks, exact candidate JSON boundary, stable
  errors, unsupported-topology behavior, one-repair policy, dependency choice, acceptance tests,
  exact file allowlist, and explicit exclusions.
- Required local JSON enforcement instead of claiming provider-enforced structured-output support.
- Kept the planner outside the web API, UI, simulator, netlist builder, parser, verifier, and final
  explanation layers.
- No implementation source, tests, dependencies, staging, commit, push, or pull request were
  created in this checkpoint.

## PR #13 bounded OpenRouter CircuitPlan planner — uncommitted implementation checkpoint

- Implemented the public `ai_electronics_lab.planning` package for the bounded OpenRouter
  CircuitPlan planner.
- Kept provider output untrusted until strict envelope parsing, exact candidate JSON decoding,
  exact candidate-field checks, `CircuitPlan` construction, and existing deterministic validation
  all succeed.
- Added fixed-request OpenRouter transport behavior with prompt/configuration bounds, secret-safe
  stable errors, no `.env` autoloading, no ambient proxy trust, disabled redirects, bounded
  response reads, and one narrowly bounded repair request.
- Added mocked-transport planning tests covering request construction, provider and candidate
  rejection boundaries, all supported topologies, repair success/exhaustion, and disclosure limits.
- Promoted HTTPX2 to a runtime dependency and updated `.env.example` with only the explicit
  OpenRouter configuration contract.
- This checkpoint remains unstaged and uncommitted pending verification and review.

## PR #13 independent-audit remediation

- Remediated the release-blocking JSON integer boundary by rejecting decimal integer literals
  longer than Python's configured conversion limit before unsafe conversion, and by normalizing
  oversized numeric validation failures to stable planner errors with the existing one-repair
  policy.
- Remediated malformed OpenRouter base-URL port handling by validating the exact approved netloc
  without exposing `urllib.parse` exception text.
- Moved mocked HTTP transport injection behind the private `_plan_circuit_request_with_transport()`
  test seam so the exported coroutine keeps the documented `prompt, *, config=None` signature.
- Added mocked regressions for hostile JSON integers in topology parameters and requested
  frequencies, repair success and exhaustion, malformed direct/env base-URL ports, production
  client isolation from ambient proxy and netrc settings, disabled redirects, and safe error
  serialization.
- Local remediation verification completed with focused and full planning-safe audit commands; changes remain unstaged and uncommitted.

## PR #13 final-audit remediation

- Rejected OpenRouter base URLs with non-empty `urllib.parse` path parameters, including encoded
  semicolon payloads and parameter/query/fragment combinations, without exposing rejected values or
  parser internals in stable configuration errors.
- Strengthened supported-topology planner coverage to assert exact returned plan fields and
  deterministic JSON round-trip content instead of a tautological serialization assertion.

## PR #13 safe-error-path remediation checkpoint

- Remediated the remaining safe-error disclosure routes in the bounded OpenRouter planner by
  normalizing planner error paths through a closed implementation-owned vocabulary.
- Unknown candidate keys, duplicate JSON keys, hostile topology-parameter names, and malformed
  validation paths now collapse to fixed safe tokens before entering `CircuitPlannerError`, repair
  prompts, serialization, or string representations.
- Preserved the validated original bounded prompt in repair requests as required by the
  specification, while excluding raw provider output and hostile path material; repair messages
  contain only the trusted original task context plus stable error code/path data.
- Added hostile-key regression coverage for direct error construction, unknown and duplicate
  provider/candidate keys, repair success, repair exhaustion, and preserved known safe schema paths.

## PR #13 repair-request contract remediation checkpoint

- Restored the validated original bounded prompt to the single permitted repair request, matching
  the authoritative planner specification.
- Encoded the original prompt and sanitized validation evidence in one deterministic repair-context
  JSON object without including the first provider response or hostile provider-controlled paths.
- Corrected the contradictory regression test and development-log statement while preserving the
  closed safe-error vocabulary and one-repair limit.

## Phase 0 capstone baseline audit and scope freeze

- Audited the public GitHub repository and synchronized local `main` with GitHub at commit
  `318ee54b1e1cbf28d25db01901633ac08e090517`.
- Confirmed there were no open pull requests and the local working tree was clean before
  verification.
- Verified the locked development environment with `uv sync --extra dev --frozen`.
- Verification completed successfully: `uv run ruff check .` reported all checks passed,
  `uv run pytest -q` reported `620 passed in 1.34s`, and the package import smoke reported
  `package_import=ok`.
- Confirmed the local application was already running from this repository on
  `127.0.0.1:18800`; `GET /` returned HTTP 200 with the expected security headers.
- Verified the established local startup command remains:
  `uv run --env-file .env uvicorn ai_electronics_lab.web.app:app --host 127.0.0.1 --port 18800 --no-server-header`.
- Executed one bounded natural-language request for each supported topology through
  `POST /api/orchestrate`:
  - RC low-pass: HTTP 200, validated `rc_low_pass` plan, final verdict `PASS`;
  - RC high-pass: HTTP 200, validated `rc_high_pass` plan, final verdict `PASS`;
  - resistive divider: HTTP 200, validated `resistive_divider` plan, final verdict `PASS`.
- Each successful request produced the complete 12-event safe stage trace from
  `request.received` through `request.completed`.
- No credentials, raw provider responses, subprocess output, or private configuration were
  recorded.
- Confirmed the useful product workflow is complete and frozen. No additional product features
  are required for the remaining competition-alignment work.

## Phase 1 public-scope alignment

- Rewrote the README around the finished three-topology natural-language-to-verdict workflow.
- Documented the actual deterministic trust boundary, Linux prerequisites, locked `uv` setup,
  ngspice requirement, safe OpenRouter configuration, localhost startup command, verification
  command, supported example prompts, and exact limitations.
- Removed public requirements and scenarios for plots, downloadable bundles, comparison runs,
  parent/child history, explanations, persistence, memory, MCP, cloud deployment, unsupported
  topologies, and offline natural-language planning.
- Replaced the architecture description with the implemented planner-to-structured-evidence flow
  and reserved future Skill and ADK work for thin adapters around the existing core.
- Reduced `.env.example` to the active bounded OpenRouter planner settings.
- Updated the submission-evidence checklist to require only reproducible finished-scope and later
  alignment evidence.
- Added ADR-022 to freeze the product scope. No runtime source, dependency, or behavior changed.

## Phase 2 verified circuit simulation Agent Skill

- Added a real project Skill at `.agents/skills/verified-circuit-simulation/SKILL.md`.
- Defined truthful trigger and non-trigger conditions for repository development tasks.
- Recorded the frozen three-topology scope, GitHub source-of-truth policy, spec-first workflow,
  canonical CircuitPlan boundary, deterministic runner/parser/verifier authority, safe commands,
  expected outputs, non-goals, and mandatory stop conditions.
- Added progressive trust-boundary and validation-case references instead of duplicating repository
  specifications.
- Recorded three trigger prompts, three non-trigger prompts, one successful repository-guidance
  task, one refusal/scope-boundary task, and secret/capability checks.
- Added focused automated validation for Skill structure, references, safety, scope, cases, and
  README status.
- Updated the README to report the Skill as included while leaving the ADK adapter explicitly
  unimplemented.
- Added ADR-023. No electronics runtime source, dependency, lockfile, web behavior, simulation
  behavior, or CI workflow changed.

## Phase 3 thin Google ADK workflow adapter

- Selected the verified optional `google-adk>=2.3,<2.4` dependency range.
- Used the public graph `Workflow`, direct `FunctionTool` node support, `Runner`, and
  `InMemorySessionService`; no private graph or tool-node import is used.
- Registered one tool named `run_verified_circuit_simulation` with exactly one `prompt` argument.
- Delegated the tool to `run_bounded_agent_orchestration()` without repeating deterministic
  electronics, provider, repair, simulation, parser, verifier, or safe-error logic.
- Added an ephemeral convenience runner that returns only the closed adapter success/error schema.
- Kept the existing FastAPI application separate from ADK and kept Google ADK optional for ordinary
  application installation.
- Added deterministic tests using fake planner, runner, and parser seams; no API key or live ngspice
  execution is required.
