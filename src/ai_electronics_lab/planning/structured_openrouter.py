"""Structured-output OpenRouter adapter for bounded CircuitPlan generation."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Sequence
from typing import Any

import httpx2 as httpx

from .openrouter import (
    CircuitPlannerError,
    OpenRouterPlannerConfig,
    _CHAT_COMPLETIONS_URL,
    _CONNECT_TIMEOUT_SECONDS,
    _MAX_REQUEST_BYTES,
    _READ_TIMEOUT_SECONDS,
    _build_request_body as _legacy_build_request_body,
    _candidate_to_plan,
    _decode_json_text,
    _extract_provider_content,
    _is_repairable,
    _planner_error,
    _read_bounded_response,
    _repair_prompt,
    _validate_config_instance,
    _validate_prompt,
    load_openrouter_planner_config,
)


def _number(description: str) -> dict[str, Any]:
    return {"type": "number", "description": description}


def _string(description: str) -> dict[str, Any]:
    return {"type": "string", "description": description}


def _array(item_schema: dict[str, Any], description: str) -> dict[str, Any]:
    return {"type": "array", "items": item_schema, "description": description}


def _plan_variant(
    *,
    topology: str,
    analysis: str,
    parameters: dict[str, dict[str, Any]],
    frequency_description: str,
) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "schema_version": {
                "type": "string",
                "enum": ["1.0"],
                "description": "CircuitPlan schema version; always 1.0.",
            },
            "topology": {
                "type": "string",
                "enum": [topology],
                "description": f"Selected supported topology; always {topology}.",
            },
            "analysis": {
                "type": "string",
                "enum": [analysis],
                "description": f"Analysis required by the topology; always {analysis}.",
            },
            "parameters": {
                "type": "object",
                "properties": parameters,
                "required": list(parameters),
                "additionalProperties": False,
            },
            "requested_frequencies_hz": _array(
                _number("Frequency in hertz as an SI-base-unit number."),
                frequency_description,
            ),
            "assumptions": _array(
                _string("A short trimmed printable engineering assumption."),
                "Zero or more short engineering assumptions; never include explanations or results.",
            ),
        },
        "required": [
            "schema_version",
            "topology",
            "analysis",
            "parameters",
            "requested_frequencies_hz",
            "assumptions",
        ],
        "additionalProperties": False,
    }


_PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "plan": {
            "description": "Exactly one bounded CircuitPlan candidate matching the user request.",
            "anyOf": [
                _plan_variant(
                    topology="rc_low_pass",
                    analysis="ac",
                    parameters={
                        "resistance_ohms": _number(
                            "Positive resistance in ohms. Convert kΩ and MΩ to ohms."
                        ),
                        "capacitance_farads": _number(
                            "Positive capacitance in farads. Convert µF, uF, nF, and pF to farads."
                        ),
                    },
                    frequency_description=(
                        "One or more positive, unique, strictly increasing frequencies in hertz."
                    ),
                ),
                _plan_variant(
                    topology="rc_high_pass",
                    analysis="ac",
                    parameters={
                        "resistance_ohms": _number(
                            "Positive resistance in ohms. Convert kΩ and MΩ to ohms."
                        ),
                        "capacitance_farads": _number(
                            "Positive capacitance in farads. Convert µF, uF, nF, and pF to farads."
                        ),
                    },
                    frequency_description=(
                        "One or more positive, unique, strictly increasing frequencies in hertz."
                    ),
                ),
                _plan_variant(
                    topology="resistive_divider",
                    analysis="dc",
                    parameters={
                        "input_voltage_volts": _number(
                            "Non-zero finite input voltage magnitude in volts."
                        ),
                        "resistance_top_ohms": _number(
                            "Positive top resistance in ohms. Convert kΩ and MΩ to ohms."
                        ),
                        "resistance_bottom_ohms": _number(
                            "Positive bottom resistance in ohms. Convert kΩ and MΩ to ohms."
                        ),
                    },
                    frequency_description="Always an empty array for a DC resistive divider.",
                ),
            ],
        }
    },
    "required": ["plan"],
    "additionalProperties": False,
}

_RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "bounded_circuit_plan",
        "strict": True,
        "schema": _PLAN_SCHEMA,
    },
}

_SYSTEM_MESSAGE = (
    "Create exactly one bounded circuit plan using the supplied JSON schema. "
    "Use SI base units and numeric JSON values, never unit-bearing strings. "
    "For RC filters, frequencies must be positive, unique, and strictly increasing. "
    "For a resistive divider, requested_frequencies_hz must be empty. "
    "When the user omits values, use deterministic demonstration defaults: "
    "RC resistance 1000 ohms, capacitance 0.000001 farads, frequencies [10,100,1000] Hz; "
    "divider input 5 volts with 1000-ohm top and bottom resistors. "
    "Do not include netlists, SPICE, commands, paths, evidence, verification, status, or explanations."
)

_REPAIR_MESSAGE = (
    "Correct the plan so it satisfies both the supplied JSON schema and the deterministic validation "
    "error codes. Preserve the user's requested topology and values. Use SI-base-unit numbers."
)


def _build_request_body(
    prompt: str,
    config: OpenRouterPlannerConfig,
    repair_errors: Sequence[CircuitPlannerError],
) -> dict[str, Any]:
    legacy = _legacy_build_request_body(prompt, config, ())
    if repair_errors:
        user_content = (
            f"{_REPAIR_MESSAGE}\n"
            f"{_repair_prompt(prompt, repair_errors).split('Repair context JSON:\n', 1)[1]}"
        )
    else:
        user_content = prompt
    legacy["messages"] = [
        {"role": "system", "content": _SYSTEM_MESSAGE},
        {"role": "user", "content": user_content},
    ]
    legacy["response_format"] = _RESPONSE_FORMAT
    legacy["provider"] = {"require_parameters": True}
    return legacy


async def plan_circuit_request(
    prompt: str,
    *,
    config: OpenRouterPlannerConfig | None = None,
):
    """Return one validated CircuitPlan using OpenRouter structured outputs."""

    return await _plan_circuit_request_with_transport(prompt, config=config, transport=None)


async def _plan_circuit_request_with_transport(
    prompt: str,
    *,
    config: OpenRouterPlannerConfig | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
):
    bounded_prompt = _validate_prompt(prompt)
    planner_config = config if config is not None else load_openrouter_planner_config()
    try:
        _validate_config_instance(planner_config)
    except CircuitPlannerError:
        raise
    except (TypeError, ValueError):
        raise _planner_error("planner.config.invalid") from None

    try:
        async with asyncio.timeout(planner_config.timeout_seconds):
            try:
                candidate = await _request_candidate(
                    bounded_prompt,
                    planner_config,
                    repair_errors=(),
                    transport=transport,
                )
                return _candidate_to_plan(candidate, repair=False)
            except CircuitPlannerError as first_error:
                if not _is_repairable(first_error):
                    raise
                candidate = await _request_candidate(
                    bounded_prompt,
                    planner_config,
                    repair_errors=(first_error,),
                    transport=transport,
                )
                try:
                    return _candidate_to_plan(candidate, repair=True)
                except CircuitPlannerError as repair_error:
                    if _is_repairable(repair_error):
                        raise _planner_error("planner.repair.exhausted") from None
                    raise
    except TimeoutError:
        raise _planner_error("planner.provider.timeout") from None


async def _request_candidate(
    prompt: str,
    config: OpenRouterPlannerConfig,
    *,
    repair_errors: Sequence[CircuitPlannerError],
    transport: httpx.AsyncBaseTransport | None,
) -> str:
    body = _build_request_body(prompt, config, repair_errors)
    encoded_body = json.dumps(body, allow_nan=False, separators=(",", ":")).encode("utf-8")
    if len(encoded_body) > _MAX_REQUEST_BYTES:
        raise _planner_error("planner.input.too_large")

    timeout = httpx.Timeout(
        config.timeout_seconds,
        connect=min(_CONNECT_TIMEOUT_SECONDS, config.timeout_seconds),
        read=min(_READ_TIMEOUT_SECONDS, config.timeout_seconds),
        write=min(_CONNECT_TIMEOUT_SECONDS, config.timeout_seconds),
        pool=min(_CONNECT_TIMEOUT_SECONDS, config.timeout_seconds),
    )
    try:
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=False,
            trust_env=False,
            verify=True,
            transport=transport,
        ) as client:
            async with client.stream(
                "POST",
                _CHAT_COMPLETIONS_URL,
                headers={
                    "Authorization": f"Bearer {config.api_key}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                content=encoded_body,
            ) as response:
                if response.status_code < 200 or response.status_code >= 300:
                    raise _planner_error("planner.provider.http_error")
                response_bytes = await _read_bounded_response(response)
    except TimeoutError:
        raise _planner_error("planner.provider.timeout") from None
    except httpx.TimeoutException:
        raise _planner_error("planner.provider.timeout") from None
    except CircuitPlannerError:
        raise
    except httpx.RequestError:
        raise _planner_error("planner.provider.network_error") from None

    envelope = _decode_json_text(
        response_bytes.decode("utf-8", errors="strict").lstrip(" \t\r\n"),
        provider=True,
    )
    content = _extract_provider_content(envelope)
    return _extract_plan_candidate(content)


def _extract_plan_candidate(content: str) -> str:
    stripped = content.strip(" \t\r\n")
    if not stripped or stripped.startswith("```"):
        raise _planner_error("planner.output.invalid_json")
    wrapper = _decode_json_text(stripped, provider=False)
    if type(wrapper) is not dict or set(wrapper) != {"plan"}:
        raise _planner_error("planner.output.invalid_json", ("candidate", "unknown_field"))
    candidate = wrapper["plan"]
    if type(candidate) is not dict:
        raise _planner_error("planner.output.invalid_json", ("candidate",))
    try:
        return json.dumps(candidate, allow_nan=False, separators=(",", ":"))
    except (TypeError, ValueError):
        raise _planner_error("planner.output.invalid_json") from None


__all__ = ["plan_circuit_request"]
