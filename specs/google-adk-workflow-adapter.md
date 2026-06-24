# Thin Google ADK Workflow Adapter

## Purpose

Version 1.0 adds one optional Google ADK graph adapter around the existing bounded orchestration
entry point. It demonstrates genuine ADK workflow and tool execution without changing product
behavior or deterministic authority.

The adapter is not a second planner, simulation engine, verifier, HTTP service, memory layer, or
deployment path.

## Framework decision

Use the official `google-adk` package in the verified `>=2.3,<2.4` range.

The implementation uses only these public framework APIs:

- `google.adk.workflow.Workflow`
- `google.adk.workflow.START`
- `google.adk.tools.function_tool.FunctionTool`
- `google.adk.runners.Runner`
- `google.adk.sessions.InMemorySessionService`
- `google.genai.types.Content`
- `google.genai.types.Part`

A `FunctionTool` is placed directly in the workflow edge list. The adapter does not import private
`_ToolNode`, `_Workflow`, graph, or runner implementation modules.

The graph Workflow API is currently documented by Google as experimental. The dependency range is
therefore restricted to the verified 2.3 minor line.

## Exact changed-file allowlist

The Phase 3 implementation is limited to:

1. `README.md`
2. `docs/decisions.md`
3. `docs/development-log.md`
4. `pyproject.toml`
5. `scripts/verify.sh`
6. `specs/architecture.md`
7. `specs/google-adk-workflow-adapter.md`
8. `src/ai_electronics_lab/adk/__init__.py`
9. `src/ai_electronics_lab/adk/tools.py`
10. `src/ai_electronics_lab/adk/workflow.py`
11. `tests/adk/test_workflow.py`
12. `tests/skills/test_verified_circuit_simulation_skill.py`
13. `uv.lock`

The Skill test changes only because its README assertion previously required the ADK adapter to be
absent.

## Architecture

The adapter flow is:

    ADK Content message
    -> lightweight function node producing {"prompt": message_text}
    -> registered FunctionTool
    -> run_bounded_agent_orchestration(prompt)
    -> safe adapter result

`run_bounded_agent_orchestration()` remains the sole product pipeline entry point. It continues to
own prompt validation, OpenRouter configuration and transport, the bounded repair policy,
CircuitPlan validation, simulation assembly, trusted deck construction, ngspice execution, raw
parsing, deterministic analytical verification, and safe error mapping.

No electronics calculations or validation rules are repeated in the ADK package.

## ADK tool contract

The registered tool name is:

- `run_verified_circuit_simulation`

Its generated callable schema has exactly one input:

- `prompt: str`

It has no parameters for a netlist, shell command, subprocess argument, executable, environment,
filesystem path, provider response, raw evidence, tolerance, measurement, or verdict.

The preceding function node only converts the ADK text input to the tool argument dictionary.
It does not validate or reinterpret the prompt. The existing orchestration boundary performs the
authoritative bounded prompt validation.

## Result contract

The adapter version is `1.0`.

Successful output contains exactly:

    {
      "version": "1.0",
      "status": "ok",
      "result": <BoundedAgentOrchestrationResult safe JSON object>
    }

Known failures contain exactly:

    {
      "version": "1.0",
      "status": "error",
      "error": {
        "code": <stable orchestration code>,
        "path": <bounded path list>,
        "message": <canonical safe orchestration message>
      }
    }

Unexpected adapter or framework failures collapse to the existing canonical
`orchestration.internal_error` vocabulary. Raw exception text is never returned.

The successful result is produced through the existing orchestration result serializer and therefore
contains no raw provider response, child stdout, child stderr, raw binary evidence, environment
values, or temporary paths.

## Execution policy

Each convenience-runner call creates a fresh in-memory ADK session and discards it after the call.
This is framework execution scaffolding only; it is not product memory or persistence.

The workflow has no LLM agent, Gemini model, ADK planner, tool-selection model, retry configuration,
MCP, A2A, sub-agent, or cloud service.

The only model transport remains the OpenRouter planner already used by the existing orchestration
entry point. The ADK layer does not add another provider call or alter the one-repair limit.

## Dependency policy

`google-adk>=2.3,<2.4` is an optional `adk` dependency extra.

The ordinary FastAPI application does not import `ai_electronics_lab.adk`, does not start an ADK
service, and remains importable with only the existing development dependencies installed.

The verification script selects both the `dev` and `adk` extras so the complete repository test
suite remains reproducible.

## Required tests

Tests must prove:

- the created object is a genuine ADK `FunctionTool`;
- its callable schema exposes only `prompt`;
- the tool is present in and invoked through a genuine ADK `Workflow` and `Runner`;
- the tool delegates to the existing orchestration entry point through a deterministic service seam;
- success returns the bounded safe orchestration result;
- known failures preserve canonical codes and bounded paths;
- hostile exception messages are not disclosed;
- no OpenRouter key or live ngspice execution is needed;
- the ordinary FastAPI module remains importable without selecting the ADK extra.
