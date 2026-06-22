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
