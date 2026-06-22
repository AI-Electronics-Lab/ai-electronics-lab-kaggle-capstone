# Architecture

    Browser
      |
    FastAPI application
      |
    Bounded agent workflow
      |
    Structured CircuitPlan
      |
    Deterministic validator
      |
    Deterministic netlist builder
      |
    Bounded local ngspice subprocess
      |
    Result parser and analytical checks
      |
    Evidence verifier
      |
    Verified explanation and artifacts

## Shared electronics core

The same deterministic modules will serve:

- the local web application;
- the ADK workflow;
- the MCP server;
- the CLI and evaluation runner.

Business logic must not be duplicated between interfaces.

## Persistence

Use SQLite or local JSON under `./data`. Production PostgreSQL is outside scope.

## Agent workflow

Planner → validation → simulation → verification → explanation.

At most one bounded repair attempt is permitted in the initial implementation.

## Security boundary

The LLM may propose structured data only. It may not provide arbitrary subprocess
arguments, filesystem paths, or executable netlist text.
