# Architecture

## Truthful core flow

```text
bounded OpenRouter planner
→ CircuitPlan validation
→ simulation assembly
→ trusted SPICE deck
→ bounded local ngspice
→ bounded raw parser
→ deterministic analytical verifier
→ structured evidence
```

The localhost FastAPI application and browser UI are thin interfaces around this core.

## Planner boundary

The provider extracts bounded topology and numeric intent only. Provider output is untrusted until
local deterministic code constructs and validates the canonical `CircuitPlan`.

The provider cannot define trusted circuit connectivity, netlists, commands, paths, simulation
evidence, verification evidence, or verdicts. One initial provider call and at most one bounded
repair attempt are permitted.

## Deterministic core

After `CircuitPlan` validation, deterministic modules:

1. assemble the supported circuit;
2. render the trusted SPICE deck;
3. execute ngspice through a fixed subprocess policy;
4. parse bounded raw evidence;
5. compare measurements with frozen analytical models;
6. produce structured evidence and `PASS`, `WARN`, or `FAIL`.

The browser may display the trusted deck, schematic, measurements, verification data, and safe stage
trace. Raw provider bodies, raw subprocess evidence, credentials, environment values, and temporary
paths are not public response fields.

## Current interface

The current supported interface is one localhost-only FastAPI application with a self-contained
browser page and bounded JSON routes. The service is intentionally bound to `127.0.0.1`.

## Competition-alignment adapters

The repository Agent Skill is a guidance-only development layer. The optional Google ADK 2.3.x
adapter is a public graph `Workflow` containing a registered `FunctionTool` that delegates one prompt
to `run_bounded_agent_orchestration()`.

Neither adapter replaces, duplicates, or gains authority over the deterministic electronics core.
The FastAPI application remains a separate interface and does not run through ADK.

No MCP server, persistence layer, memory service, cloud deployment, or general-purpose CLI is part of
the finished runtime architecture.

## Reproducibility

The Python environment is locked with `uv.lock`. `scripts/verify.sh` performs the CI-equivalent
development verification. Live natural-language execution additionally requires OpenRouter access
and a trusted local ngspice installation.
