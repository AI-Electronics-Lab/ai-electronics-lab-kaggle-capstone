"""Bounded localhost FastAPI adapter over the deterministic simulation pipeline."""

from __future__ import annotations

import asyncio
import json
import math
from collections.abc import Callable
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, Response
from starlette.concurrency import run_in_threadpool

from ai_electronics_lab.contracts import (
    CircuitPlan,
    CircuitPlanValidationError,
    require_valid_circuit_plan,
)
from ai_electronics_lab.contracts.circuit_plan import (
    MAX_CAPACITANCE_FARADS,
    MAX_FREQUENCY_HZ,
    MAX_INPUT_VOLTAGE_VOLTS,
    MAX_RESISTANCE_OHMS,
    MIN_CAPACITANCE_FARADS,
    MIN_FREQUENCY_HZ,
    MIN_RESISTANCE_OHMS,
    SCHEMA_VERSION,
)
from ai_electronics_lab.simulation import (
    SIMULATION_RAW_PARSER_VERSION,
    SimulationDeck,
    SimulationDeckError,
    SimulationParsedResults,
    SimulationRawParseError,
    SimulationRunnerError,
    build_simulation_assembly_from_plan,
    build_simulation_deck_from_assembly,
    parse_simulation_execution_evidence,
    run_simulation_deck,
)
from ai_electronics_lab.simulation.core.schematic_renderer import (
    render_engineering_schematic_svg,
)

MAX_REQUEST_BODY_BYTES = 8 * 1024
MAX_UI_FREQUENCIES = 8

_MAX_SCHEMATIC_BYTES = 64 * 1024
_MAX_NETLIST_RESPONSE_BYTES = MAX_UI_FREQUENCIES * 64 * 1024
_INDEX_PATH = Path(__file__).with_name("index.html")

SimulationService = Callable[[object], dict[str, Any]]
Runner = Callable[[SimulationDeck], Any]
Parser = Callable[[Any], SimulationParsedResults]

_SECURITY_HEADERS = {
    "Cache-Control": "no-store",
    "Content-Security-Policy": (
        "default-src 'none'; "
        "style-src 'unsafe-inline'; "
        "script-src 'unsafe-inline'; "
        "img-src 'self' blob:; "
        "connect-src 'self'; "
        "base-uri 'none'; "
        "form-action 'self'; "
        "frame-ancestors 'none'"
    ),
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
}


class WebUIError(ValueError):
    """Stable user-safe failure at the local web boundary."""

    def __init__(
        self,
        code: str,
        path: tuple[str | int, ...],
        message: str,
        status_code: int,
    ) -> None:
        self.code = code
        self.path = path
        self.message = message
        self.status_code = status_code
        super().__init__(code)

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "path": list(self.path),
        }


def simulate_request(
    payload: object,
    *,
    runner: Runner = run_simulation_deck,
    parser: Parser = parse_simulation_execution_evidence,
) -> dict[str, Any]:
    """Validate one narrow UI request and execute the trusted pipeline."""

    try:
        plan = _build_plan(payload)
        validated_plan = require_valid_circuit_plan(plan)
        assembly = build_simulation_assembly_from_plan(validated_plan)
        deck = build_simulation_deck_from_assembly(assembly)
        schematic_svg = _render_schematic(validated_plan)
        evidence = runner(deck)
        parsed = parser(evidence)

        if type(parsed) is not SimulationParsedResults:
            raise WebUIError(
                "simulation.internal_error",
                (),
                "The simulation pipeline returned an unexpected result.",
                500,
            )

        return {
            "deck": _safe_deck_dict(deck),
            "evidence_kind": "deterministic_simulation_evidence",
            "notice": "Deterministic ngspice evidence; not an LLM assertion.",
            "plan": validated_plan.to_dict(),
            "results": _safe_results_dict(parsed),
            "schematic_svg": schematic_svg,
            "status": "ok",
        }
    except WebUIError:
        raise
    except CircuitPlanValidationError as exc:
        first_error = exc.errors[0]
        raise WebUIError(
            "request.plan_invalid",
            first_error.path,
            first_error.message,
            422,
        ) from None
    except SimulationDeckError:
        raise WebUIError(
            "simulation.deck_rejected",
            (),
            "The trusted simulation deck could not be created.",
            500,
        ) from None
    except SimulationRunnerError:
        raise WebUIError(
            "simulation.execution_failed",
            (),
            "The bounded local simulation could not complete.",
            503,
        ) from None
    except SimulationRawParseError:
        raise WebUIError(
            "simulation.evidence_invalid",
            (),
            "The bounded simulation evidence could not be parsed.",
            502,
        ) from None
    except (ArithmeticError, AssertionError, TypeError, ValueError):
        raise WebUIError(
            "simulation.internal_error",
            (),
            "The deterministic simulation pipeline could not complete.",
            500,
        ) from None


def create_app(
    simulation_service: SimulationService = simulate_request,
) -> FastAPI:
    """Create the localhost application without external documentation assets."""

    application = FastAPI(
        title="AI Electronics Lab Local UI",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    application.state.simulation_service = simulation_service
    application.state.simulation_lock = asyncio.Lock()

    @application.middleware("http")
    async def add_security_headers(
        request: Request,
        call_next: Callable[..., Any],
    ) -> Response:
        response = await call_next(request)
        for name, value in _SECURITY_HEADERS.items():
            response.headers[name] = value
        return response

    @application.exception_handler(WebUIError)
    async def handle_web_ui_error(
        _request: Request,
        exc: WebUIError,
    ) -> Response:
        return _json_response(
            {
                "error": exc.to_dict(),
                "status": "error",
            },
            status_code=exc.status_code,
        )

    @application.exception_handler(Exception)
    async def handle_unexpected_error(
        _request: Request,
        _exc: Exception,
    ) -> Response:
        return _json_response(
            {
                "error": {
                    "code": "simulation.internal_error",
                    "message": (
                        "The local application could not complete the request."
                    ),
                    "path": [],
                },
                "status": "error",
            },
            status_code=500,
        )

    @application.get(
        "/",
        response_class=HTMLResponse,
        include_in_schema=False,
    )
    async def home() -> HTMLResponse:
        return HTMLResponse(_load_index_html())

    @application.post(
        "/api/simulate",
        include_in_schema=False,
    )
    async def simulate(request: Request) -> Response:
        payload = await _read_bounded_json(request)
        lock: asyncio.Lock = application.state.simulation_lock

        if lock.locked():
            raise WebUIError(
                "request.busy",
                (),
                "Another local simulation is already running.",
                429,
            )

        async with lock:
            result = await run_in_threadpool(
                application.state.simulation_service,
                payload,
            )

        return _json_response(result, status_code=200)

    return application


@lru_cache(maxsize=1)
def _load_index_html() -> str:
    return _INDEX_PATH.read_text(encoding="utf-8")


async def _read_bounded_json(request: Request) -> object:
    media_type = (
        request.headers.get("content-type", "")
        .split(";", 1)[0]
        .strip()
        .lower()
    )
    if media_type != "application/json":
        raise WebUIError(
            "request.content_type",
            (),
            "Content-Type must be application/json.",
            400,
        )

    content_encoding = (
        request.headers.get("content-encoding", "").strip().lower()
    )
    if content_encoding not in {"", "identity"}:
        raise WebUIError(
            "request.content_encoding",
            (),
            "Compressed request bodies are not accepted.",
            400,
        )

    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            declared_length = int(content_length)
        except ValueError:
            raise WebUIError(
                "request.content_length",
                (),
                "Content-Length must be a valid non-negative integer.",
                400,
            ) from None

        if declared_length < 0:
            raise WebUIError(
                "request.content_length",
                (),
                "Content-Length must be a valid non-negative integer.",
                400,
            )

        if declared_length > MAX_REQUEST_BODY_BYTES:
            raise WebUIError(
                "request.too_large",
                (),
                "Request body exceeds the local size limit.",
                413,
            )

    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > MAX_REQUEST_BODY_BYTES:
            raise WebUIError(
                "request.too_large",
                (),
                "Request body exceeds the local size limit.",
                413,
            )

    if not body:
        raise WebUIError(
            "request.empty",
            (),
            "Request body must not be empty.",
            400,
        )

    try:
        text = bytes(body).decode("utf-8")
    except UnicodeDecodeError:
        raise WebUIError(
            "request.encoding",
            (),
            "Request body must be valid UTF-8.",
            400,
        ) from None

    try:
        return json.loads(
            text,
            object_pairs_hook=_pairs_to_dict,
            parse_constant=_reject_json_constant,
        )
    except WebUIError:
        raise
    except (json.JSONDecodeError, RecursionError, ValueError):
        raise WebUIError(
            "request.malformed_json",
            (),
            "Request body must contain valid JSON.",
            400,
        ) from None


def _pairs_to_dict(
    pairs: list[tuple[str, Any]],
) -> dict[str, Any]:
    result: dict[str, Any] = {}

    for key, value in pairs:
        if key in result:
            raise WebUIError(
                "request.duplicate_key",
                (),
                "Duplicate JSON object keys are not accepted.",
                400,
            )
        result[key] = value

    return result


def _reject_json_constant(_value: str) -> Any:
    raise WebUIError(
        "request.non_finite",
        (),
        "Non-finite JSON numbers are not accepted.",
        400,
    )


def _build_plan(payload: object) -> CircuitPlan:
    if type(payload) is not dict:
        raise WebUIError(
            "request.object_required",
            (),
            "Request body must be a JSON object.",
            422,
        )

    if any(type(key) is not str for key in payload):
        raise WebUIError(
            "request.fields",
            (),
            "Request field names must be strings.",
            422,
        )

    topology = payload.get("topology")
    if type(topology) is not str or topology not in {
        "rc_low_pass",
        "rc_high_pass",
        "resistive_divider",
    }:
        raise WebUIError(
            "request.topology_unsupported",
            ("topology",),
            "Select one supported circuit topology.",
            422,
        )

    if topology in {"rc_low_pass", "rc_high_pass"}:
        expected = {
            "capacitance_farads",
            "frequencies_hz",
            "resistance_ohms",
            "topology",
        }
        _require_exact_keys(payload, expected)

        resistance = _strict_number(
            payload["resistance_ohms"],
            ("resistance_ohms",),
            minimum=MIN_RESISTANCE_OHMS,
            maximum=MAX_RESISTANCE_OHMS,
        )
        capacitance = _strict_number(
            payload["capacitance_farads"],
            ("capacitance_farads",),
            minimum=MIN_CAPACITANCE_FARADS,
            maximum=MAX_CAPACITANCE_FARADS,
        )
        frequencies = _strict_frequencies(
            payload["frequencies_hz"],
        )

        return CircuitPlan(
            schema_version=SCHEMA_VERSION,
            topology=topology,
            analysis="ac",
            parameters={
                "capacitance_farads": capacitance,
                "resistance_ohms": resistance,
            },
            requested_frequencies_hz=frequencies,
            assumptions=(),
        )

    expected = {
        "input_voltage_volts",
        "resistance_bottom_ohms",
        "resistance_top_ohms",
        "topology",
    }
    _require_exact_keys(payload, expected)

    input_voltage = _strict_number(
        payload["input_voltage_volts"],
        ("input_voltage_volts",),
        minimum=math.nextafter(0.0, 1.0),
        maximum=MAX_INPUT_VOLTAGE_VOLTS,
        magnitude=True,
        nonzero=True,
    )
    resistance_top = _strict_number(
        payload["resistance_top_ohms"],
        ("resistance_top_ohms",),
        minimum=MIN_RESISTANCE_OHMS,
        maximum=MAX_RESISTANCE_OHMS,
    )
    resistance_bottom = _strict_number(
        payload["resistance_bottom_ohms"],
        ("resistance_bottom_ohms",),
        minimum=MIN_RESISTANCE_OHMS,
        maximum=MAX_RESISTANCE_OHMS,
    )

    return CircuitPlan(
        schema_version=SCHEMA_VERSION,
        topology=topology,
        analysis="dc",
        parameters={
            "input_voltage_volts": input_voltage,
            "resistance_bottom_ohms": resistance_bottom,
            "resistance_top_ohms": resistance_top,
        },
        requested_frequencies_hz=(),
        assumptions=(),
    )


def _require_exact_keys(
    payload: dict[str, Any],
    expected: set[str],
) -> None:
    actual = set(payload)
    missing = sorted(expected - actual)

    if missing:
        raise WebUIError(
            "request.field_missing",
            (missing[0],),
            "A required request field is missing.",
            422,
        )

    if actual - expected:
        raise WebUIError(
            "request.field_unknown",
            (),
            "The request contains fields that are not allowed.",
            422,
        )


def _strict_frequencies(
    value: object,
) -> tuple[float | int, ...]:
    if type(value) is not list:
        raise WebUIError(
            "request.frequencies_type",
            ("frequencies_hz",),
            "Frequencies must be a JSON array.",
            422,
        )

    if not value:
        raise WebUIError(
            "request.frequencies_empty",
            ("frequencies_hz",),
            "At least one AC frequency is required.",
            422,
        )

    if len(value) > MAX_UI_FREQUENCIES:
        raise WebUIError(
            "request.frequencies_too_many",
            ("frequencies_hz",),
            f"At most {MAX_UI_FREQUENCIES} AC frequencies are allowed.",
            422,
        )

    frequencies = tuple(
        _strict_number(
            item,
            ("frequencies_hz", index),
            minimum=MIN_FREQUENCY_HZ,
            maximum=MAX_FREQUENCY_HZ,
        )
        for index, item in enumerate(value)
    )

    if any(
        current <= previous
        for previous, current in zip(
            frequencies,
            frequencies[1:],
        )
    ):
        raise WebUIError(
            "request.frequencies_order",
            ("frequencies_hz",),
            "Frequencies must be strictly increasing and unique.",
            422,
        )

    return frequencies


def _strict_number(
    value: object,
    path: tuple[str | int, ...],
    *,
    minimum: float | int,
    maximum: float | int,
    magnitude: bool = False,
    nonzero: bool = False,
) -> float | int:
    if type(value) not in {int, float}:
        raise WebUIError(
            "request.number_type",
            path,
            "Value must be a JSON number; booleans are not accepted.",
            422,
        )

    if type(value) is float and not math.isfinite(value):
        raise WebUIError(
            "request.number_non_finite",
            path,
            "Value must be finite.",
            422,
        )

    if nonzero and value == 0:
        raise WebUIError(
            "request.number_zero",
            path,
            "Value must be nonzero.",
            422,
        )

    comparable = abs(value) if magnitude else value
    if comparable < minimum or comparable > maximum:
        raise WebUIError(
            "request.number_out_of_range",
            path,
            "Value is outside the supported numeric range.",
            422,
        )

    return value


def _render_schematic(plan: CircuitPlan) -> str:
    parameters = plan.parameters

    if plan.topology in {"rc_low_pass", "rc_high_pass"}:
        components = {
            "C1_farad": float(
                parameters["capacitance_farads"],
            ),
            "R1_ohm": float(
                parameters["resistance_ohms"],
            ),
        }
    else:
        components = {
            "R1_ohm": float(
                parameters["resistance_top_ohms"],
            ),
            "R2_ohm": float(
                parameters["resistance_bottom_ohms"],
            ),
        }

    svg = render_engineering_schematic_svg(
        plan.topology,
        components,
    )
    encoded = svg.encode("utf-8")
    lowered = svg.lower()

    if len(encoded) > _MAX_SCHEMATIC_BYTES:
        raise WebUIError(
            "simulation.internal_error",
            (),
            "The deterministic schematic exceeded its output limit.",
            500,
        )

    if (
        "<script" in lowered
        or "javascript:" in lowered
        or "onload=" in lowered
        or "onerror=" in lowered
    ):
        raise WebUIError(
            "simulation.internal_error",
            (),
            "The deterministic schematic failed its safety check.",
            500,
        )

    return svg


def _safe_deck_dict(
    deck: SimulationDeck,
) -> dict[str, Any]:
    total_netlist_bytes = sum(
        len(run.netlist_text.encode("utf-8"))
        for run in deck.runs
    )

    if total_netlist_bytes > _MAX_NETLIST_RESPONSE_BYTES:
        raise WebUIError(
            "simulation.internal_error",
            (),
            "The trusted deck exceeded the browser output limit.",
            500,
        )

    return {
        "runs": [
            {
                "analysis_kind": run.analysis_kind,
                "frequency_hz": run.frequency_hz,
                "netlist_text": run.netlist_text,
                "probe_names": list(run.probe_names),
                "run_id": run.run_id,
            }
            for run in deck.runs
        ],
        "version": deck.version,
    }


def _safe_results_dict(
    parsed: SimulationParsedResults,
) -> dict[str, Any]:
    if parsed.version != SIMULATION_RAW_PARSER_VERSION:
        raise WebUIError(
            "simulation.internal_error",
            (),
            "The parsed result version is not supported.",
            500,
        )

    return {
        "runs": [
            {
                "analysis_kind": run.analysis_kind,
                "frequency_hz": run.frequency_hz,
                "run_id": run.run_id,
                "topology": run.topology,
                "vin_voltage": {
                    "imag": run.vin_voltage.imag,
                    "real": run.vin_voltage.real,
                },
                "vout_voltage": {
                    "imag": run.vout_voltage.imag,
                    "real": run.vout_voltage.real,
                },
            }
            for run in parsed.runs
        ],
        "version": parsed.version,
    }


def _json_response(
    content: dict[str, Any],
    *,
    status_code: int,
) -> Response:
    body = json.dumps(
        content,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    return Response(
        content=body,
        media_type="application/json",
        status_code=status_code,
    )


app = create_app()

__all__ = [
    "MAX_REQUEST_BODY_BYTES",
    "MAX_UI_FREQUENCIES",
    "WebUIError",
    "app",
    "create_app",
    "simulate_request",
]
