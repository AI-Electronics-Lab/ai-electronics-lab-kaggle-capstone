---
name: verified-circuit-simulation
description: Safely guide development, review, testing, and documentation work for this repository's bounded three-topology circuit-simulation workflow without expanding model authority or product scope.
---

# Verified Circuit Simulation

Use this Skill to guide repository work around the verified natural-language-to-verdict circuit
workflow. It is a development-agent instruction layer only. It does not execute simulations, replace
the deterministic core, or grant an LLM authority over trusted engineering evidence.

Use progressive disclosure:

1. Read this file first.
2. Read `references/trust-boundary.md` when a task touches authority, security, orchestration,
   simulation, verification, or public claims.
3. Read `references/validation-cases.md` when validating Skill triggers, non-triggers, guidance, or
   refusal behavior.
4. Read the repository specifications and implementation files referenced below before editing.

## Trigger this Skill when

Use the Skill when a coding or development task asks to:

- implement, review, test, document, or integrate the repository's bounded planner-to-verdict flow;
- modify or audit `CircuitPlan`, orchestration, simulation, parsing, verification, web-adapter, Skill,
  or future ADK-adapter boundaries;
- prepare safe setup, test, localhost-startup, security, evaluation, or submission-evidence guidance;
- check whether a proposed repository change preserves deterministic authority and frozen scope;
- diagnose a supported low-pass, high-pass, or unloaded-divider development workflow.

## Do not trigger this Skill when

Do not use the Skill for:

- general electronics tutoring or circuit design unrelated to this repository;
- standalone requests to design unsupported circuits or product features unrelated to repository
  maintenance; use this Skill when the task is to document or enforce the repository refusal boundary;
- unrelated infrastructure, cloud, database, office, tax, medical, or personal tasks;
- arbitrary SPICE authoring outside the trusted deterministic builders;
- operational requests that do not concern repository development or validation.

## Supported product scope

The finished runtime supports exactly:

- RC low-pass filters;
- RC high-pass filters;
- unloaded resistive voltage dividers.

Treat plots, downloadable bundles, what-if comparisons, parent/child runs, prose explanations,
persistence, memory, MCP, cloud deployment, BJT circuits, power electronics, arbitrary topologies,
and arbitrary SPICE as explicit non-goals.

Do not quietly reinterpret a non-goal as future work inside a bounded task.

## Repository source of truth

The merged GitHub `main` branch is authoritative.

Before editing:

1. inspect the current repository and open pull requests;
2. synchronize local `main` with GitHub using fast-forward-only operations;
3. require a clean working tree with no unexpected untracked files;
4. create one dedicated branch from the verified current `main`;
5. stop on divergence, conflicting work, secrets, or unexplained changes.

Never discard, reset, force-push, rewrite, or delete work merely to obtain a clean state.

## Required spec-first workflow

For every behavioral or architectural task:

1. read the relevant files under `specs/`;
2. inspect the actual implementation and tests;
3. state the smallest changed-file allowlist;
4. update or add the governing specification before or together with implementation;
5. preserve existing deterministic boundaries;
6. add focused validation for changed behavior;
7. run focused tests;
8. run `bash scripts/verify.sh`;
9. inspect `git diff --check`, the changed-file list, and the complete diff;
10. commit and push one bounded branch;
11. open a PR describing scope, tests, security impact, risks, and exclusions;
12. do not merge without explicit user authorization;
13. synchronize local `main` after an authorized merge.

## Canonical CircuitPlan boundary

`CircuitPlan` is the canonical planner-to-deterministic-code boundary.

Treat provider output as untrusted candidate data until deterministic code:

- enforces the bounded candidate schema;
- constructs the canonical `CircuitPlan`;
- runs repository validation;
- rejects unsupported topology, invalid values, unknown fields, or malformed data.

Do not allow a model, prompt, adapter, Skill, or framework to bypass this boundary.

## Trust and authority boundaries

The LLM may extract bounded topology and numeric intent only.

The LLM must not author or control:

- trusted final connectivity;
- executable SPICE netlists or directives;
- subprocess arguments;
- executable paths or arbitrary filesystem paths;
- simulation evidence;
- analytical expectations or tolerances;
- PASS, WARN, or FAIL verdicts;
- free-form stage-trace vocabulary;
- raw provider or subprocess evidence returned to users.

Deterministic repository code constructs the circuit and deck. The bounded ngspice runner produces
raw execution evidence. The bounded parser interprets that evidence. The deterministic verifier is
the authority for the engineering verdict.

Read `references/trust-boundary.md` before changing any of these layers.

## Safe commands

From the repository root, use:

```bash
uv sync --extra dev --frozen
uv run pytest -q tests/skills/test_verified_circuit_simulation_skill.py
bash scripts/verify.sh
git diff --check
git status --short --branch
```

For the localhost application, use a local uncommitted `.env` containing the OpenRouter key:

```bash
uv run --env-file .env uvicorn ai_electronics_lab.web.app:app \
  --host 127.0.0.1 \
  --port 18800 \
  --no-server-header
```

Never print, copy, commit, summarize, or expose the key or `.env` contents.

Do not transform user text into shell commands, executable paths, or hand-authored trusted netlists.

## Expected outputs

A repository-guidance response should produce only what the task needs, normally including:

- the verified current scope and relevant source-of-truth files;
- the smallest proposed changed-file allowlist;
- the trust boundary affected by the task;
- focused and full verification commands;
- explicit security and non-goal checks;
- a stop condition when assumptions cannot be verified.

A successful runtime result may contain a validated plan, deterministic assembly and deck, parsed
measurements, engineering schematic, safe stage trace, deterministic verification data, and a final
PASS, WARN, or FAIL verdict.

Do not promise unsupported artifacts.

## Error handling and stop conditions

Stop and report rather than guessing when:

- GitHub and local `main` differ;
- the working tree contains unexplained or out-of-scope changes;
- another PR or agent is changing the same scope;
- a required specification or implementation file cannot be inspected;
- a task would widen the frozen product scope;
- a request asks for credentials, raw provider data, hidden reasoning, subprocess internals, or
  private paths;
- a request asks the LLM to author final SPICE, commands, paths, evidence, or verdicts;
- focused tests, full verification, security checks, or diff checks fail;
- an unsupported topology or ambiguous product claim is presented as implemented.

Use stable repository error vocabulary where one exists. Do not expose raw exception text as a
substitute for the public error contract.

## Progressive references

Read only the references needed for the task:

- `references/trust-boundary.md`
- `references/validation-cases.md`
- `README.md`
- `specs/product-requirements.md`
- `specs/acceptance-scenarios.md`
- `specs/architecture.md`
- `specs/bounded-agent-orchestration.md`
- `src/ai_electronics_lab/contracts/circuit_plan.py`
- `src/ai_electronics_lab/planning/openrouter.py`
- `src/ai_electronics_lab/orchestration/orchestrator.py`
- `src/ai_electronics_lab/simulation/`
- `src/ai_electronics_lab/verification/`
- `src/ai_electronics_lab/web/app.py`
- `scripts/verify.sh`

These files contain the actual product and trust-boundary truth. This Skill summarizes how to work
with them; it does not supersede them.
