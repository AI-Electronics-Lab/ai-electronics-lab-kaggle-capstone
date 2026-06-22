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
