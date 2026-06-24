# Architectural decisions

## ADR-001: Clean public history

The capstone repository starts with a new Git history. Private repository history is never
published.

## ADR-002: Compact monolith

Use one local FastAPI application rather than reproducing production microservices.

## ADR-003: Local persistence

Use SQLite or local JSON instead of production PostgreSQL.

## ADR-004: Deterministic netlist boundary

The LLM produces a structured plan. Deterministic code validates the plan and constructs
the final netlist.

## ADR-005: Frozen initial scope

Support RC low-pass, RC high-pass, and resistive divider before adding BJT circuits.

## ADR-006: Direct Linux installation first

Docker is deferred until a clean direct installation works.

## ADR-007: Versioned CircuitPlan validation boundary

Use a frozen standard-library `CircuitPlan` as the canonical planner output. Version 1.0 supports
only RC low-pass, RC high-pass, and resistive-divider plans. Semantic validation returns stable,
structured errors; deterministic consumers require validity through a raising helper before using
the plan. Circuit graphs and netlists remain separate downstream representations.

## ADR-008: Bounded simulation-deck expansion

Expand a defensively revalidated `SimulationAssembly` into one immutable complete deck per exact AC
frequency, or one DC operating-point deck. Reuse deterministic component rendering and permit only
trusted generated `.ac` or `.op` directives before the single final `.end`. Simulator execution,
paths, commands, and raw planner-authored directives remain outside this boundary.

## ADR-009: Bounded ngspice execution boundary

Execute `SimulationDeck` values only through a private fixed ngspice policy. The runner
defensively revalidates deck structure and rendered netlist text before executable lookup, uses
trusted absolute candidates only, suppresses ngspice startup files with `-n`, runs batch mode with
fixed internal input and raw-output filenames, provides a minimal non-inherited environment, bounds
input/stdout/stderr/raw bytes and per-run/total time, terminates the process group on failure, and
returns immutable raw evidence only after every run succeeds. Version 1.0 evidence excludes elapsed
time because wall-clock timing is nondeterministic and unnecessary for the future electrical parser.


## ADR-010: PR #8 independent-audit remediation

Keep the fixed ngspice execution policy, but harden its validation and cleanup semantics. The
runner now treats process-leader exit as insufficient evidence that the process group is empty,
signals the complete child process group after both normal stream drain and failure paths, and
reaps the direct child deterministically. It validates exact deck/run/string/tuple/numeric field
types before hashing, indexing, comparing, formatting, encoding, resolving executables, or creating
temporary directories, and normalizes malformed-object exceptions to `SimulationRunnerError`.
Component numeric tokens must equal deterministic scalar rendering after parsing and bounds checks,
so noncanonical aliases are not accepted at the PR #7 deck-text boundary.

## ADR-011: Bounded ngspice raw parser boundary

Parse only `SimulationExecutionEvidence` produced by the fixed runner policy into immutable
structured voltage measurements. The parser defensively revalidates exact evidence types, version,
run ordering, trusted probes, return codes, frequencies, and bounded raw bytes before unpacking
native ngspice binary doubles. It accepts only the inspected ngspice-42 single-plot, single-point
headers for RC AC analysis and divider operating-point analysis, validates every binary double for
finiteness, validates AC frequency against the deterministic scalar-rendered request, and omits raw
dates, stdout, stderr, paths, arbitrary vector names, and raw bytes from public parsed output.

The AC frequency imaginary slot is treated according to the local ngspice-42 producer behavior:
exact zero is accepted, and a finite subnormal placeholder from ngspice is accepted, while normal
nonzero values are rejected. No endian detection, ASCII `Values:` parsing, heuristic recovery,
electrical pass/fail calculation, explanation, persistence, API, UI, MCP, agent, dependency, or
deployment behavior is part of this boundary.

## ADR-012: PR #9 independent-audit remediation

Keep the bounded ngspice raw parser public API, schema, error contract, bounds, and native-double
policy unchanged, but constrain textual mode-marker detection to the ASCII header grammar. The
parser now locates the first exact `Binary:\n` delimiter before checking for unsupported
`Values:` mode, recognizes `Values:` only as a complete header line before binary data, and treats
all bytes after the binary delimiter as opaque payload until bounded native-double unpacking and
finite-value validation. Header substrings such as `Date: Values:` are not data-mode delimiters.

## ADR-013: PR #9 second independent-audit remediation

Keep the bounded raw-parser API, output schema, grammar, bounds, native-double behavior, and
payload-marker remediation unchanged, but make validation order explicit at the evidence boundary.
After validating the outer evidence container and exact run object types, the parser now validates
every field of every run before cross-run coherence comparisons. A hostile object placed into a
second or later `analysis_kind` with raising comparison methods is rejected at the precise
`("runs", index, "analysis_kind")` path before equality or inequality can execute, and before any
raw parsing begins.

## ADR-014: PR #9 final independent-audit remediation

Keep the bounded raw-parser public API, output schema, bounds, native-double policy, stable errors,
payload opacity, hostile-comparison remediation, and validation-order fixes unchanged, but require
both `Binary:` and `Values:` to be recognized only as exact complete ASCII header lines. Ordinary
header-field substrings such as `Date: Binary:` and `Date: prefix Binary:` do not affect delimiter
selection, variable-row substrings do not become delimiters, and binary payload remains opaque after
the real delimiter is found.

The trusted probe tuple contract remains exact: the tuple must have exactly three entries, the
length is checked before element traversal, and length-three tuples still exact-type validate every
entry before comparison with the trusted probe tuple.

## ADR-015: PR #9 integer-overflow remediation

Preserve the bounded raw-parser API, schema, grammar, exact-line delimiter handling, payload
opacity, and validation ordering, while separating integer and floating-point frequency
validation. Exact built-in integers are mathematically finite and are compared directly against
the trusted positive range without conversion to a C double. Exact built-in floats continue to
require `math.isfinite()` before range checks. This prevents huge malformed integers from escaping
the structured parser boundary as `OverflowError`.

## ADR-016: Minimal localhost FastAPI UI boundary

Expose the existing deterministic plan-to-parser pipeline through one localhost-only FastAPI
application. The HTTP boundary accepts exact topology-specific JSON fields rather than
attempting natural-language planning. Route handlers perform bounded decoding and delegate to a
separate orchestration function; they do not reproduce topology, deck, runner, or parser logic.

Use a self-contained page with no external assets, disabled generated API documentation, safe
text-node rendering, Blob-backed schematic images, stable generic execution errors, a
one-request concurrency boundary, and an explicit 127.0.0.1:18800 startup command. Return
validated plans, trusted deck text, deterministic schematic SVG, and parsed voltages, but never
return raw evidence, child output, temporary paths, environment values, or exception strings.

Add only bounded FastAPI and Uvicorn runtime ranges and test-only HTTPX. Keep the implementation
unstaged and uncommitted until independent audit.

## ADR-017: Deterministic analytical evidence verification

Add an immutable deterministic verifier after bounded raw parsing and before any future
explanation layer. The verifier accepts only a validated CircuitPlan and coherent
SimulationParsedResults, revalidates exact types and cross-object structure, calculates frozen
analytical expectations for the three supported topologies, and emits bounded PASS, WARN, or
FAIL evidence.

Use fixed non-user-configurable tolerances: absolute 1e-9, relative 1e-6, warning multiplier
10.0, and denominator floor 1e-12. Compare complex values using magnitude error, use a
scale-aware complex-division algorithm, report phase only above the denominator floor, preserve
deterministic canonical JSON, and normalize malformed or non-finite inputs to stable structured
verifier errors.

Integrate verification into the existing localhost API and self-contained UI without adding a
dependency, LLM, prose explanation, persistence, arbitrary SPICE, user-defined tolerances, or
new deployment surface.

## ADR-018: PR #11 independent-audit trust-boundary remediation

Preserve the deterministic verifier API, analytical models, fixed tolerances, comparison order,
web response, and UI behavior while closing two public-contract gaps found during independent
audit.

Before traversing `CircuitPlan.parameters`, inspect the exact `MappingProxyType` referent without
invoking mapping protocol hooks and require the referent itself to be an exact built-in `dict`.
This prevents a mapping proxy over a hostile custom mapping from executing user-defined iteration
or lookup code at the verifier boundary.

Also enforce the documented `VerificationComparison` schema at construction: metric allowlist,
nonnegative errors, positive fixed-policy limits, value/error coherence, and status/reason
classification coherence. These checks harden the public immutable evidence contract without
changing normal verifier output.

## ADR-019: Bounded OpenRouter CircuitPlan planner

Add one bounded natural-language planner before the canonical CircuitPlan boundary.

Use the fixed OpenRouter chat-completions endpoint with
`openai/gpt-oss-120b:free` as the default model. Provider output remains untrusted candidate data
until it passes bounded provider-envelope parsing, exact local JSON decoding, exact candidate-field
validation, CircuitPlan construction, and the existing deterministic validator.

Do not send or rely on `response_format` for the default free model. Require one JSON object through
the fixed prompt and enforce the contract locally.

Permit one initial provider call and at most one narrowly bounded repair request. Never allow the
model to create trusted netlists, shell commands, arbitrary tool choices, paths, circuit
connectivity, simulation evidence, verification evidence, or final engineering claims.

Keep PR #13 separate from the existing web API and UI.
