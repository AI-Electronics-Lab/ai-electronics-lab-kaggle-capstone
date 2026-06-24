# AI Electronics Lab — Evidence-First Circuit Simulation Agent

AI Electronics Lab turns a bounded natural-language request for a small supported circuit into
reproducible SPICE evidence and a deterministic engineering verdict.

## Frozen product scope

The finished capstone supports exactly three circuit topologies:

- RC low-pass filter;
- RC high-pass filter;
- unloaded resistive voltage divider.

The scope is intentionally frozen. Unsupported topologies are rejected rather than approximated or
simulated with fabricated evidence.

## Actual workflow

```text
natural-language prompt
→ bounded OpenRouter planner
→ validated CircuitPlan
→ deterministic simulation assembly
→ trusted SPICE deck
→ bounded local ngspice execution
→ bounded raw-result parser
→ deterministic analytical verifier
→ structured evidence and PASS/WARN/FAIL verdict
```

The browser UI also renders an engineering schematic and a safe stage trace for the completed
workflow.

## Deterministic trust boundary

The model may extract only bounded topology and numeric intent. Provider output remains untrusted
until deterministic code creates and validates the canonical `CircuitPlan`.

The model cannot author trusted connectivity, executable netlists, subprocess arguments, filesystem
paths, simulation evidence, analytical verification, or the final verdict. Deterministic code owns
all of those boundaries.

## Requirements

- Linux;
- Python 3.11, 3.12, or 3.13;
- `uv`;
- ngspice available at `/usr/bin/ngspice` or `/usr/local/bin/ngspice`;
- outbound HTTPS access to OpenRouter for natural-language planning;
- an OpenRouter API key.

There is no offline natural-language planner. The deterministic core and automated tests can run
without an API key, but a live natural-language request requires configured OpenRouter access.

## Installation

```bash
git clone https://github.com/AI-Electronics-Lab/ai-electronics-lab-kaggle-capstone.git
cd ai-electronics-lab-kaggle-capstone
uv sync --extra dev --frozen
```

Create the local environment file:

```bash
cp .env.example .env
chmod 600 .env
```

Set `OPENROUTER_API_KEY` in `.env`. Never commit `.env` or print the key in logs.

## Start the application

```bash
uv run --env-file .env uvicorn ai_electronics_lab.web.app:app \
  --host 127.0.0.1 \
  --port 18800 \
  --no-server-header
```

Open `http://127.0.0.1:18800/` from the same machine or through a trusted SSH tunnel. The application
is intentionally localhost-only.

## Example prompts

- `Design an RC low-pass filter with a 1000 ohm resistor and a 1 microfarad capacitor. Evaluate it at 10 Hz, 100 Hz, and 1000 Hz.`
- `Design an RC high-pass filter with a 2200 ohm resistor and a 100 nanofarad capacitor. Evaluate it at 100 Hz, 1000 Hz, and 10000 Hz.`
- `Design a resistive voltage divider with a 12 volt input, a 10000 ohm top resistor, and a 5000 ohm bottom resistor.`

## Verification

Run the same locked verification used by CI:

```bash
bash scripts/verify.sh
```

This synchronizes the development environment, runs Ruff, runs the full pytest suite, and performs
a package-import smoke test.

## Current competition-alignment status

- Agent Skill: included at `.agents/skills/verified-circuit-simulation/SKILL.md`; it guides
  development agents without changing runtime authority or product behavior.
- Google ADK adapter: not yet included; planned as a thin adapter that calls the existing
  orchestration entry point.
- The deterministic simulation core remains the source of truth for both future layers.

## Explicit limitations

This repository does not implement:

- plots or chart generation;
- downloadable artifact bundles;
- what-if or parent/child comparison runs;
- a prose explanation layer;
- persistence, memory, or user history;
- MCP;
- cloud deployment or remote hosting;
- Docker as a required execution path;
- BJT, power-electronics, or arbitrary user-defined topologies;
- arbitrary SPICE, commands, paths, tools, or model-authored verdicts.

The product is a compact localhost capstone, not a general-purpose circuit-design platform.
