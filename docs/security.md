# Security architecture

This document describes the security boundaries of the finished AI Electronics Lab capstone.
It is an engineering overview, not a formal security certification, penetration-test report, or
claim that the software is safe for hostile public deployment.

The product is intentionally small and localhost-only. Its security design is based on keeping model
output outside the trusted execution boundary and allowing only deterministic, narrowly bounded code
to construct and execute circuit simulations.

## Security objectives

The implementation is designed to:

- treat natural-language input and model output as untrusted data;
- restrict model authority to bounded topology and numeric intent extraction;
- reject unsupported or malformed plans instead of approximating them;
- prevent model-authored shell commands, paths, circuit connectivity, SPICE directives, and verdicts;
- execute ngspice with fixed arguments, fixed filenames, bounded resources, and a minimal environment;
- expose only structured, reviewed evidence and stable errors;
- keep credentials, raw provider responses, raw subprocess output, and temporary paths out of public
  response contracts;
- bind the development application to `127.0.0.1` by default.

## System trust boundaries

The implemented flow is:

```text
untrusted natural-language prompt
→ bounded OpenRouter request
→ untrusted provider tool arguments
→ deterministic CircuitPlan construction and validation
→ deterministic circuit assembly
→ deterministic trusted SPICE deck
→ bounded local ngspice execution
→ bounded raw-result parsing
→ deterministic analytical verification
→ structured evidence and PASS/WARN/FAIL verdict
```

The Agent Skill and optional Google ADK graph adapter do not gain authority over this pipeline. The
Skill is guidance-only. The ADK `FunctionTool` delegates one prompt to the existing orchestration
entry point and does not add another planner, simulator, verifier, shell interface, filesystem
interface, or model-controlled tool-selection loop.

## Untrusted prompt and provider boundary

User prompt text is inert input. It cannot select a provider endpoint, alter request headers, change
resource limits, add tools, choose subprocess arguments, or modify the deterministic validation
policy.

The OpenRouter planner uses a fixed HTTPS endpoint and a bounded request contract. Provider output is
never trusted as a circuit, command, or engineering conclusion. The model may return only the fixed
plan-tool fields used to extract:

- one topology from the supported vocabulary;
- topology-specific numeric values;
- requested AC frequencies where applicable.

Provider bodies, metadata, reasoning details, usage fields, and unexpected envelope fields do not
become simulation authority. The initial provider request permits at most one narrowly bounded repair
request. There is no autonomous retry loop.

## Canonical CircuitPlan boundary

`CircuitPlan` is the canonical boundary between model-derived candidate data and deterministic
execution.

The supported topology vocabulary is closed:

- `rc_low_pass`;
- `rc_high_pass`;
- `resistive_divider`.

Deterministic validation rejects missing fields, unknown fields, unsupported topologies, invalid
analysis combinations, non-finite values, booleans used as numbers, out-of-range component values,
and incoherent requested frequencies.

The model cannot define:

- circuit nodes or connectivity;
- component reference designators;
- SPICE source forms or directives;
- trusted netlist text;
- executable names or arguments;
- filesystem paths;
- simulation evidence;
- verification tolerances;
- PASS, WARN, or FAIL outcomes.

## Deterministic circuit and netlist generation

After `CircuitPlan` validation, deterministic code selects one of the three fixed topology builders,
uses fixed node names, adds the fixed-policy source, and renders the complete simulation deck.

The final SPICE text is generated from trusted repository code rather than copied from the prompt or
provider response. The runner revalidates the complete deck before executable lookup, file creation,
or process startup.

Only the expected component forms and one generated `.ac` or `.op` analysis directive are accepted.
Arbitrary `.include`, `.lib`, `.control`, `.shell`, additional devices, additional nodes, and
caller-provided directives are rejected.

## Bounded ngspice execution

The ngspice runner exposes no public parameter for an executable, command string, argument vector,
working directory, environment, timeout, or path.

Its execution policy uses:

- trusted absolute executable candidates only;
- no inherited `PATH` lookup;
- `shell=False` and a fixed argument list;
- ngspice `-n` to suppress user and local startup files;
- batch execution with fixed internal filenames;
- one private temporary directory per run;
- a minimal environment that does not inherit credentials, tokens, proxy settings, or caller home
  configuration;
- bounded deck, stdout, stderr, and raw-output sizes;
- per-run and total time limits;
- process-group termination and bounded cleanup on success and failure.

Raw subprocess evidence is an internal boundary. It is not returned by the public orchestration or
web response.

## Parsing and verification boundaries

The raw parser accepts only the repository's immutable execution-evidence structure and a narrow,
inspected ngspice binary format. It validates exact object types, run ordering, topology and analysis
coherence, trusted probe names, bounded header grammar, binary size, and finite native-double values.
It does not perform heuristic recovery or accept arbitrary vectors.

The analytical verifier revalidates both the plan and parsed results before arithmetic. It uses fixed,
non-user-configurable analytical models and tolerance constants for the supported RC filters and
resistive divider. The final verdict is derived from deterministic comparisons rather than supplied
or revised by a model.

## Web and ADK interfaces

The FastAPI application is intended for local development and demonstration. Repository instructions
bind it to `127.0.0.1`; it is not designed as an internet-facing multi-user service.

The web boundary uses bounded request bodies, strict JSON decoding, duplicate-key and non-finite-value
rejection, stable error mapping, and a one-request concurrency boundary. The browser renders dynamic
values through safe DOM text operations and does not receive raw provider or subprocess data.

The optional ADK adapter accepts only one `prompt: str` tool argument. It delegates to the same
bounded orchestration and returns its safe structured result. Unexpected framework failures collapse
to the existing generic internal-error contract rather than exposing exception text.

## Safe errors and disclosure policy

Public failures use stable implementation-owned codes, bounded field paths, and fixed safe messages.
They must not include:

- API keys or authorization headers;
- environment values;
- prompt echoes in stage traces;
- raw provider responses or provider error bodies;
- exception representations or stack traces;
- child stdout or stderr;
- raw binary simulation evidence;
- temporary directories or private paths;
- arbitrary provider-controlled field names.

Successful orchestration responses contain the validated plan, deterministic assembly and deck,
parsed measurements, verification evidence, and a closed stage trace. They do not contain hidden
reasoning or raw operational data.

## Secret handling

The live OpenRouter key is supplied through the ignored local `.env` file. The tracked
`.env.example` contains only empty or non-secret configuration values.

Repository and development rules prohibit committing credentials, internal URLs, private paths,
operational logs, or user data. Code must not enumerate the environment, print `.env`, or embed the
key in logs, exceptions, object representations, snapshots, or response payloads.

On 2026-06-24, Gitleaks 8.30.1 scanned the tracked tree and full reachable Git history at
commit `2d09e7be962d1e46893db36a4e2a7334e0920720`. Both scans returned exit code 0 with zero findings. See
[`secret-scan-evidence.md`](secret-scan-evidence.md) for the safe reproducible record. Raw JSON
reports remain outside the repository.

## Dependency and CI posture

Python dependencies are locked with `uv.lock`. Both `scripts/verify.sh` and GitHub CI install the
locked `dev` and optional `adk` dependency groups, run Ruff, and execute the full pytest suite.
`scripts/verify.sh` additionally performs a package-import smoke check.

Automated tests use deterministic fakes and fixtures for provider and simulator boundaries where
appropriate. CI does not require a real OpenRouter key or live external model request.

## Known limitations and non-protections

The project does not claim protection against every threat. In particular:

- it is not a hardened public SaaS service or multi-tenant isolation boundary;
- localhost binding does not protect a compromised local machine or untrusted local user;
- the project relies on the security of the operating system, Python runtime, installed dependencies,
  GitHub Actions ecosystem, ngspice executable, and OpenRouter service;
- dependency locking improves reproducibility but does not prove dependencies are vulnerability-free;
- deterministic validation cannot eliminate defects in the validators themselves;
- resource bounds reduce denial-of-service exposure but do not constitute complete DoS protection;
- the application has no authentication or authorization layer because remote hosting is outside the
  finished scope;
- no formal threat-model review, penetration test, sandbox certification, supply-chain attestation,
  or cryptographic verification of the ngspice executable is claimed;
- the recorded secret scan is detector- and ruleset-based and applies only to the named commit; it does not guarantee that every secret format or future commit is clean;
- unsupported circuit topologies and arbitrary user-authored SPICE are intentionally rejected rather
  than sandboxed.

Do not expose this development server publicly without a separate security design, authentication,
transport-security, deployment, monitoring, patching, and operational review.

## Authoritative implementation references

The implementation and detailed contracts remain the source of truth:

- `AGENTS.md`;
- `specs/architecture.md`;
- `specs/circuit-plan-contract.md`;
- `specs/bounded-openrouter-planner.md`;
- `specs/simulation-assembly.md`;
- `specs/bounded-simulation-deck.md`;
- `specs/bounded-ngspice-runner.md`;
- `specs/bounded-ngspice-raw-parser.md`;
- `specs/deterministic-evidence-verifier.md`;
- `specs/bounded-agent-orchestration.md`;
- `specs/google-adk-workflow-adapter.md`;
- `docs/decisions.md`.

When this overview and an implementation specification differ, the current merged specification,
source, and tests take precedence.
