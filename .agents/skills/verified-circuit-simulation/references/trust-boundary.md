# Verified simulation trust boundary

This reference explains which layer is authoritative. Read the underlying source before changing a
layer. Do not use this document as a replacement for implementation inspection.

## Authority map

| Layer | Accepts | May produce | Must not control |
| --- | --- | --- | --- |
| User prompt | Bounded natural language | Requested topology and numeric intent | Commands, paths, trusted SPICE, evidence, verdicts |
| OpenRouter provider/model | Bounded prompt and fixed schema instructions | Untrusted structured candidate data | Final connectivity, final netlist, simulation evidence, verification |
| OpenRouter planner adapter | Bounded prompt and provider response | Validated `CircuitPlan` or stable safe failure | Raw provider disclosure or unchecked candidate data |
| CircuitPlan validation | Candidate fields | Canonical validated `CircuitPlan` | Provider-specific prose or unchecked data |
| Simulation assembly | Validated `CircuitPlan` | Trusted topology and source assembly | Prompt-authored connectivity or directives |
| Deck builder | Trusted assembly | Deterministic SPICE deck | Arbitrary directives or executable policy |
| ngspice runner | Trusted deck | Bounded raw execution evidence | Prompt-controlled argv, executable, environment, path, or timeout |
| Raw parser | Runner evidence | Bounded structured measurements | Heuristic recovery or public raw evidence |
| Analytical verifier | Validated plan and parsed measurements | Deterministic PASS/WARN/FAIL evidence | Model-authored tolerances, expectations, or verdict |
| Web adapter | Bounded HTTP request | Safe structured response and trace | Secrets, raw provider bodies, subprocess output, private paths |
| Agent Skill | Development task context | Safe repository guidance | Runtime authority or product behavior |

## Canonical boundary sequence

```text
bounded natural-language prompt
→ untrusted planner candidate
→ validated CircuitPlan
→ deterministic simulation assembly
→ trusted deterministic SPICE deck
→ bounded ngspice execution
→ bounded raw parsing
→ deterministic analytical verification
→ structured evidence and PASS/WARN/FAIL
```

Any adapter must enter through an existing public boundary. It must not duplicate or replace the
deterministic core.

## CircuitPlan rules

The canonical contract lives in:

- `src/ai_electronics_lab/contracts/circuit_plan.py`
- related specifications under `specs/`

Before downstream use, require the repository's validation helper. Do not infer validity from type
annotations, provider success, JSON shape, or framework validation alone.

Supported topology identifiers are limited to the repository-defined low-pass, high-pass, and
resistive-divider values.

## Planner rules

The bounded planner lives in:

- `src/ai_electronics_lab/planning/openrouter.py`

Provider output remains untrusted. Preserve:

- bounded prompt size;
- bounded request and response size;
- fixed provider endpoint policy;
- fixed safe tool/candidate schema;
- at most one bounded repair attempt;
- local exact-field validation;
- safe error mapping;
- no raw provider body in public results.

## Orchestration rules

The orchestration entry point is:

- `run_bounded_agent_orchestration(...)`
- `src/ai_electronics_lab/orchestration/orchestrator.py`
- `specs/bounded-agent-orchestration.md`

It coordinates existing layers synchronously and emits a closed stage-trace vocabulary. New
framework integrations should call this entry point or another approved existing public boundary.

Do not let an integration rebuild topology, deck, simulation, parser, or verifier logic.

## Simulation rules

The trusted simulation implementation lives under:

- `src/ai_electronics_lab/simulation/`

Preserve:

- deterministic supported topology construction;
- trusted generated analysis directives;
- fixed executable candidates;
- fixed subprocess argument policy;
- minimal non-inherited environment;
- bounded input, output, raw evidence, and time;
- process-group cleanup;
- stable structured failures.

A prompt, model, Skill, HTTP field, or adapter must never provide executable netlist text, an
executable path, argv, working directory, environment variables, or timeout policy.

## Verification rules

The deterministic verifier lives under:

- `src/ai_electronics_lab/verification/`

It owns analytical expectations, fixed tolerance policy, structured comparisons, and the final
verdict. A model may explain repository structure but must not replace or override the verifier.

## Web and disclosure rules

The localhost adapter lives in:

- `src/ai_electronics_lab/web/app.py`

Public responses and logs must omit:

- credentials and `.env` values;
- raw provider responses;
- hidden reasoning;
- raw subprocess stdout or stderr;
- raw binary simulation data;
- temporary paths;
- inherited environment values;
- unrestricted exception text.

Use safe bounded response structures and stable error codes.

## Change review checklist

Before approving a change, confirm:

- the task is within the frozen three-topology product scope;
- relevant specifications were read and updated when required;
- the model still produces only untrusted candidate intent;
- `CircuitPlan` remains the canonical validation boundary;
- deterministic builders still own connectivity and SPICE;
- runner policy remains fixed and bounded;
- parser and verifier remain authoritative;
- no secret or private path is introduced;
- focused tests and `bash scripts/verify.sh` pass;
- the complete diff contains only the approved files;
- no merge occurs without explicit authorization.
