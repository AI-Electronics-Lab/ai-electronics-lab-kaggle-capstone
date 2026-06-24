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

## ADR-020: Forced bounded OpenRouter plan tool

Use one fixed function tool named `submit_circuit_plan` for the default free OpenRouter model and
force that exact tool with `tool_choice`. Do not send `response_format`: the current free provider
endpoint accepts `tools` and `tool_choice` but rejects the JSON-schema response-format parameter
when `provider.require_parameters` is enabled.

Treat tool arguments as untrusted bounded JSON. Accept exactly one tool call, reject parallel prose
and unexpected tool names, then pass the decoded candidate through the existing exact field checks,
`CircuitPlan` construction, and deterministic validator. This transport change does not authorize
arbitrary tools or change the one-repair limit, simulation, evidence, or verdict boundaries.

## ADR-021: Flat provider extraction, deterministic CircuitPlan construction

Do not ask the default free model to author the nested canonical `CircuitPlan` schema. Live tests
showed that the endpoint accepted the forced tool but ignored the nested `anyOf` structure and
invented fields such as `components`, `circuit_type`, and nested `analysis` data on both the initial
and repair attempts.

Use one exact flat seven-field tool schema instead. Require every topology-neutral field, require
exact numeric zero for fields irrelevant to the selected topology, and reject extra or missing
fields locally. Deterministic code derives schema version, analysis kind, topology-specific
parameter names, and an empty assumptions list before invoking the existing canonical
`CircuitPlan` validator.

This narrows rather than expands model authority: the provider extracts topology and numeric values
only. It still cannot define connectivity, netlists, commands, schema versions, analyses,
assumptions, evidence, verification results, or verdicts. Preserve one bounded repair attempt and
the exact legacy candidate parser only as a bounded compatibility path.

## ADR-022: Freeze the finished capstone product scope

Treat the three-topology natural-language-to-verdict workflow as the finished product. Public
documentation must describe only RC low-pass, RC high-pass, and unloaded resistive-divider support,
the bounded OpenRouter planner, deterministic CircuitPlan validation, trusted SPICE generation,
bounded local ngspice execution, parsed measurements, schematic rendering, safe stage tracing, and
deterministic PASS/WARN/FAIL verification.

Do not present plots, downloadable bundles, comparison runs, parent/child history, prose
explanations, persistence, memory, MCP, cloud deployment, BJT circuits, or an offline
natural-language planner as implemented capabilities.

Future Agent Skill and Google ADK work must remain thin competition-alignment layers around the
existing orchestration entry point. They must not duplicate the deterministic electronics core or
expand the frozen product behavior.

## ADR-023: Guidance-only verified circuit simulation Skill

Add one repository Agent Skill under `.agents/skills/verified-circuit-simulation/` to guide coding
agents through safe development, review, testing, and documentation tasks around the existing
three-topology workflow.

The Skill is guidance-only. It is not imported by runtime Python, does not execute ngspice, and has
no authority to construct connectivity, trusted SPICE, commands, paths, evidence, tolerances, or
verdicts. It uses progressive disclosure through a concise main Skill file, a trust-boundary
reference, and recorded trigger/non-trigger validation cases.

The merged GitHub `main` branch, repository specifications, implementation, and tests remain the
sources of truth. The Skill must direct agents back to those files, preserve spec-first development,
and stop on unexplained or out-of-scope dirty state, divergence, scope expansion, secret
exposure, or failed verification.

## ADR-024: Optional Google ADK graph adapter

Add `google-adk>=2.3,<2.4` as an optional dependency and expose one public ADK graph `Workflow`
containing a genuine `FunctionTool`. The tool accepts only a natural-language `prompt` and delegates
to `run_bounded_agent_orchestration()`.

Do not add an ADK LLM agent, Gemini model, alternate planner, framework retry, memory, persistence,
MCP, A2A, cloud service, or FastAPI route. A fresh in-memory ADK session exists only for one adapter
invocation and is discarded afterward.

The adapter canonicalizes known orchestration failures through the existing error vocabulary and
collapses unexpected adapter failures to `orchestration.internal_error`. It does not duplicate
prompt validation, provider transport, CircuitPlan validation, circuit construction, SPICE
generation, ngspice execution, parsing, tolerances, evidence, or verdict logic.

## ADR-025: Split software and documentation licensing

License software source, tests, scripts, workflow configuration, and machine-consumed project
configuration under Apache License 2.0.

License original repository documentation and original project media under Creative Commons
Attribution 4.0 International.

Keep the complete Apache license in `LICENSE`, the complete CC BY 4.0 legal code in
`LICENSE-DOCUMENTATION`, and the file-scope and attribution rules in `LICENSING.md`.

Because distribution files have different file-scoped licenses, do not declare one global license
expression in `pyproject.toml`. List the legal files through `license-files` instead.

Third-party software, services, interfaces, trademarks, logos, and externally sourced material retain
their respective terms. This decision changes repository licensing and metadata only; it does not
change product behavior or deterministic authority.
