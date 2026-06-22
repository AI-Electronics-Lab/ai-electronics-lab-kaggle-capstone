# AI Electronics Lab — Evidence-First Circuit Simulation Agent

A compact and reproducible Kaggle capstone that converts plain-language electronics
requests into validated circuit plans, deterministic SPICE simulations, engineering
artifacts, and explanations grounded in verified evidence.

## Engineering invariant

1. An agent proposes a structured `CircuitPlan`.
2. Deterministic code validates the plan.
3. Deterministic code constructs the SPICE netlist.
4. A bounded ngspice subprocess performs the simulation.
5. Deterministic checks verify the numerical evidence.
6. The final explanation uses only verified structured results.

## Initial supported scope

- RC low-pass filter
- RC high-pass filter
- resistive voltage divider

BJT circuits are intentionally deferred until the required scope is complete.

## Current foundation

The repository currently includes:

- a deterministic circuit graph and netlist intermediate representation;
- primitive component builders;
- deterministic SPICE rendering;
- schematic layout and SVG rendering;
- an RC low-pass topology block and prompt parser;
- focused unit and contract tests;
- specifications, architectural decisions, and extraction provenance.

## Requirements

- Linux
- Python 3.11 or newer
- uv
- ngspice for live simulation stages added later

## Local setup

1. Clone the repository.
2. Enter the repository directory.
3. Run `uv sync --extra dev --frozen`.
4. Run `uv run pytest`.
5. Run `uv run ruff check .`.

The current deterministic-core tests do not require an LLM key, database, Docker,
Cloudflare, Tailscale, or production infrastructure.

## Development workflow

Development happens on focused branches and is merged through reviewed pull requests.
The repository specifications under `specs/` are the source of truth.

## Security boundary

An LLM may propose structured data only. It may not construct unchecked shell commands,
arbitrary filesystem paths, or a trusted final netlist.
