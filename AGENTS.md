# Repository instructions

## Source of truth

Read the relevant files in `specs/` before implementation. Update specifications when an
approved architectural decision changes.

## Safety boundaries

- Never access or modify production services, databases, credentials, or artifact directories.
- Never copy a private repository wholesale.
- Import private-source code only through the reviewed extraction allowlist.
- Never commit credentials, private paths, internal URLs, operational logs, or user data.
- Bind the application to `127.0.0.1` by default.
- Never let an LLM construct arbitrary shell commands or an unchecked final netlist.
- Bound subprocess time, input length, artifact size, and agent retry count.

## Engineering invariant

1. An agent produces a structured `CircuitPlan`.
2. Deterministic code validates it.
3. Deterministic code builds the netlist.
4. ngspice performs the simulation.
5. Deterministic checks and a verifier inspect the evidence.
6. The explanation uses only verified structured evidence.

## Development workflow

- Make small, reviewable changes.
- Add or update tests with behavior changes.
- Run focused tests before the complete suite.
- Inspect the actual diff before committing.
- Record meaningful decisions in `docs/decisions.md`.
- Record agent handoffs in `docs/development-log.md`.
- Keep Codex and Antigravity from editing the same working tree simultaneously.
