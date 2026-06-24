# Verified circuit simulation Agent Skill

## Purpose

Add one real repository Agent Skill that teaches a coding or development agent how to work safely
with the existing verified circuit-simulation workflow.

The Skill is a development instruction artifact. It must not change runtime electronics behavior,
load into the FastAPI application, execute ngspice, or replace the deterministic core.

## Exact changed-file allowlist

Phase 2 changes are limited to:

1. `.agents/skills/verified-circuit-simulation/SKILL.md`
2. `.agents/skills/verified-circuit-simulation/references/trust-boundary.md`
3. `.agents/skills/verified-circuit-simulation/references/validation-cases.md`
4. `specs/verified-circuit-simulation-skill.md`
5. `tests/skills/test_verified_circuit_simulation_skill.py`
6. `README.md`
7. `docs/decisions.md`
8. `docs/development-log.md`

No runtime source, dependency, lockfile, web behavior, simulation behavior, or CI workflow is in
scope.

## Required Skill structure

The Skill must use minimal frontmatter containing:

- `name: verified-circuit-simulation`
- a truthful description suitable for Skill selection.

The main file must cover:

- trigger conditions;
- non-trigger conditions;
- the three supported topologies;
- GitHub `main` as source of truth;
- clean synchronization and one-branch/one-PR workflow;
- spec-first development;
- the canonical `CircuitPlan` boundary;
- prohibition on model-authored final connectivity and netlists;
- deterministic runner, parser, and verifier authority;
- safe setup, focused-test, full-test, diff, and localhost-startup commands;
- exact non-goals;
- expected guidance and runtime outputs;
- safe errors and mandatory stop conditions;
- progressive links to repository truth.

## Progressive disclosure

`SKILL.md` must remain a concise operating guide.

Detailed authority mapping belongs in `references/trust-boundary.md`. Trigger, non-trigger,
successful-guidance, refusal, secret, and capability cases belong in
`references/validation-cases.md`.

The Skill must point to actual specifications and implementation paths rather than copying their
full contents.

## Validation contract

Automated validation must confirm:

- valid minimal frontmatter and exact Skill name;
- every required operating section exists;
- exactly three documented trigger cases;
- exactly three documented non-trigger cases;
- one successful repository-guidance case;
- one refusal or scope-boundary case;
- every repository source-of-truth path referenced by the Skill exists;
- no key, token, private user path, `.env` value, or raw provider response is embedded;
- only the three supported topologies are presented as implemented;
- unsupported capabilities remain explicit non-goals;
- README reports the Skill as included and ADK as not yet included.

## Acceptance criteria

- A real Skill exists under `.agents/skills/verified-circuit-simulation/`.
- It reflects current repository behavior exactly.
- It contains no secret or private operational material.
- Focused automated validation passes.
- Full repository verification passes.
- Validation evidence is recorded.
- No electronics functionality changes.
