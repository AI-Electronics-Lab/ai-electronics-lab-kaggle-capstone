# Minimal localhost FastAPI UI

## Purpose

Version 1.0 provides the first browser-visible integration surface over the existing
deterministic circuit simulation pipeline:

    bounded JSON request
    -> CircuitPlan
    -> deterministic plan validation
    -> trusted topology adapter
    -> simulation assembly
    -> bounded SPICE deck
    -> bounded ngspice runner
    -> bounded raw parser
    -> safe structured browser response

The UI is a local demonstration adapter. It is not a general natural-language planner, an LLM
agent, a deterministic electrical verifier, or a production deployment.

## Runtime boundary

The application must bind explicitly to:

    127.0.0.1:18800

It must not bind to 0.0.0.0 by default. Windows browser access uses an SSH local-forwarding
tunnel.

The application requires no LLM API key, cloud service, database, Docker service,
authentication, persistent storage, upload directory, or external browser asset.

## Dependencies

Runtime dependencies are limited to the tested minor release lines: FastAPI `>=0.138,<0.139` and Uvicorn `>=0.49,<0.50`. HTTPX2 `>=2.4,<2.5` is test-only because the current Starlette TestClient requires HTTPX2.

No FastAPI standard extra, frontend framework, Node toolchain, template engine, multipart
parser, watcher, analytics library, or external asset dependency is added.

## Routes

### GET /

Returns one UTF-8 self-contained HTML document containing its own CSS and JavaScript.

FastAPI documentation and OpenAPI routes are disabled because the default documentation
interfaces load external assets and are outside this local demonstration boundary.

### POST /api/simulate

Accepts only application/json.

The decoded body must be no more than 8,192 bytes. Duplicate JSON object keys, non-finite JSON
constants, malformed UTF-8, compressed request bodies, and malformed JSON are rejected before
simulation.

The endpoint executes at most one simulation request at a time. A concurrent request is rejected
with a stable busy error rather than starting another ngspice execution.

## Input schemas

Only exact built-in JSON objects, strings, arrays, integers, and floating-point numbers are
accepted. Boolean values are never accepted as numbers. Unknown fields are rejected.

### RC low-pass

    {
      "topology": "rc_low_pass",
      "resistance_ohms": 1000,
      "capacitance_farads": 0.000001,
      "frequencies_hz": [10, 100, 1000]
    }

### RC high-pass

    {
      "topology": "rc_high_pass",
      "resistance_ohms": 1000,
      "capacitance_farads": 0.000001,
      "frequencies_hz": [10, 100, 1000]
    }

### Resistive divider

    {
      "topology": "resistive_divider",
      "input_voltage_volts": 5,
      "resistance_top_ohms": 1000,
      "resistance_bottom_ohms": 2000
    }

The UI permits at most eight strictly increasing AC frequencies even though the lower-level
contract supports a larger bounded maximum. This narrower limit keeps the first browser response
compact.

The existing circuit-plan numeric bounds remain authoritative:

- resistance: 1 ohm through 1e9 ohms;
- capacitance: 1e-15 farads through 1 farad;
- frequency: 1e-6 hertz through 1e9 hertz;
- divider input voltage: finite, nonzero magnitude no greater than 1e6 volts.

Huge integers are rejected by direct integer range comparisons before any conversion to a C
double.

## Orchestration boundary

HTTP handling does not reproduce circuit, deck, runner, or parser logic.

The service function:

1. validates the narrow UI schema;
2. constructs a versioned CircuitPlan;
3. calls require_valid_circuit_plan;
4. calls build_simulation_assembly_from_plan;
5. calls build_simulation_deck_from_assembly;
6. renders the existing deterministic engineering SVG from validated values;
7. calls run_simulation_deck;
8. calls parse_simulation_execution_evidence;
9. copies only explicitly allowed fields into the response.

The assembly function remains responsible for invoking the trusted plan adapter.

## Successful response

A successful response contains only:

- stable status and evidence-kind labels;
- the validated plan;
- trusted deck version, run identifiers, analysis kinds, frequencies, probe names, and netlist
  text;
- deterministic schematic SVG;
- parsed Vin and Vout complex voltage measurements.

The response does not contain:

- raw binary bytes or base64 raw evidence;
- child stdout or stderr;
- executable or temporary paths;
- process environment data;
- exception strings;
- credentials or secrets.

The response label states that the values are deterministic simulation evidence, not an LLM
assertion. PR #10 does not claim electrical PASS, WARN, or FAIL.

## Error contract

Errors use this stable shape:

    {
      "error": {
        "code": "request.malformed_json",
        "message": "Request body must contain valid JSON.",
        "path": []
      },
      "status": "error"
    }

Request errors use HTTP 400 or 422. Busy requests use 429. Bounded execution failures use 503.
Raw-evidence parsing failures use 502. Unexpected failures use 500.

Runner or parser exception text, subprocess output, paths, and internal object representations
are never copied to the browser.

## HTML and SVG safety

The page contains no external scripts, stylesheets, fonts, images, or network calls other than
the same-origin simulation endpoint.

Dynamic text is assigned through textContent. The page does not use dynamic innerHTML.

The deterministic SVG is loaded into an image through a browser Blob URL rather than inserted as
HTML. Server-side SVG output is size-bounded and rejected if it contains script or event-handler
constructs.

Responses include a restrictive Content Security Policy, nosniff, no-referrer, no-store, and
frame-denial headers.

## Startup

From the repository root:

    uv run uvicorn ai_electronics_lab.web.app:app           --host 127.0.0.1           --port 18800           --no-server-header

Windows SSH tunnel:

    ssh -L 18800:127.0.0.1:18800 developer@development-host

Browser address:

    http://127.0.0.1:18800

## Acceptance scenarios

1. GET / returns a local self-contained page with no external assets.
2. FastAPI documentation and OpenAPI routes are disabled.
3. A valid RC low-pass request reaches parsed voltage measurements.
4. A valid RC high-pass request reaches parsed voltage measurements.
5. A valid divider request reaches parsed voltage measurements.
6. Malformed, oversized, duplicate-key, or non-JSON input is rejected before simulation.
7. Unsupported topology and unknown fields are rejected.
8. Boolean, non-finite, huge, out-of-range, duplicate, and unordered numbers are rejected.
9. Runner and parser failures map to stable safe errors.
10. User-controlled text cannot create HTML or script injection.
11. Responses omit raw evidence, child output, paths, environment data, and exception text.
12. Focused tests, complete tests, Ruff, import smoke, source compilation, and whitespace checks
    pass.
13. One optional real-ngspice integration test runs when an approved local ngspice executable
    exists.
14. All implementation remains unstaged and uncommitted until independent audit and
    authorization.

## Explicit exclusions

PR #10 does not add natural-language planning, an LLM provider, deterministic evidence verdicts,
natural-language explanations, history, persistence, uploads, accounts, authentication, public
deployment, Docker, systemd, Cloudflare, MCP, ADK, or arbitrary SPICE editing.
