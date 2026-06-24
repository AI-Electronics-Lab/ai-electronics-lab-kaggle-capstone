"""Forced-tool OpenRouter adapter for bounded CircuitPlan value extraction."""

from __future__ import annotations

import asyncio
import json
import math
from collections.abc import Sequence
from typing import Any

import httpx2 as httpx

from ai_electronics_lab.contracts import CircuitPlan

from .openrouter import (
    _CANDIDATE_KEYS,
    _CHAT_COMPLETIONS_URL,
    _CONNECT_TIMEOUT_SECONDS,
    _MAX_CONTENT_BYTES,
    _MAX_REQUEST_BYTES,
    _READ_TIMEOUT_SECONDS,
    CircuitPlannerError,
    OpenRouterPlannerConfig,
    _candidate_to_plan,
    _decode_json_bytes,
    _decode_json_text,
    _is_repairable,
    _planner_error,
    _read_bounded_response,
    _validate_config_instance,
    _validate_prompt,
    load_openrouter_planner_config,
)
from .openrouter import (
    _build_request_body as _legacy_build_request_body,
)


def _number(description: str) -> dict[str, Any]:
    return {"type": "number", "description": description}


def _array(item_schema: dict[str, Any], description: str) -> dict[str, Any]:
    return {"type": "array", "items": item_schema, "description": description}


_FLAT_VALUE_KEYS = frozenset(
    {
        "topology",
        "resistance_ohms",
        "capacitance_farads",
        "input_voltage_volts",
        "resistance_top_ohms",
        "resistance_bottom_ohms",
        "requested_frequencies_hz",
    }
)
_REQUIRED_FLAT_VALUE_KEYS = [
    "topology",
    "resistance_ohms",
    "capacitance_farads",
    "input_voltage_volts",
    "resistance_top_ohms",
    "resistance_bottom_ohms",
    "requested_frequencies_hz",
]
_PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "topology": {
            "type": "string",
            "enum": ["rc_low_pass", "rc_high_pass", "resistive_divider"],
            "description": "Exactly one supported circuit topology.",
        },
        "resistance_ohms": _number(
            "RC resistance in ohms. Use zero only when topology is resistive_divider."
        ),
        "capacitance_farads": _number(
            "RC capacitance in farads. Use zero only when topology is resistive_divider."
        ),
        "input_voltage_volts": _number(
            "Divider input voltage in volts. Use zero for either RC topology."
        ),
        "resistance_top_ohms": _number(
            "Divider top resistance in ohms. Use zero for either RC topology."
        ),
        "resistance_bottom_ohms": _number(
            "Divider bottom resistance in ohms. Use zero for either RC topology."
        ),
        "requested_frequencies_hz": _array(
            _number("Frequency in hertz as an SI-base-unit number."),
            "Positive, unique, strictly increasing frequencies for RC; empty for a divider.",
        ),
    },
    "required": _REQUIRED_FLAT_VALUE_KEYS,
    "additionalProperties": False,
}

_TOOL_NAME = "submit_circuit_plan"
_TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": _TOOL_NAME,
        "description": (
            "Submit one flat bounded circuit-value extraction for deterministic "
            "CircuitPlan construction and validation."
        ),
        "parameters": _PLAN_SCHEMA,
    },
}
_TOOL_CHOICE = {
    "type": "function",
    "function": {"name": _TOOL_NAME},
}

_SYSTEM_MESSAGE = (
    "Call submit_circuit_plan exactly once with the seven flat schema fields. "
    "Use SI base units and numeric JSON values, never unit-bearing strings. "
    "Fill every field. For RC filters, use zero for all three divider-only fields and provide "
    "positive, unique, strictly increasing frequencies. For a resistive divider, use zero for "
    "the two RC-only fields and provide an empty requested_frequencies_hz array. "
    "When the user omits values, use deterministic demonstration defaults: "
    "RC resistance 1000 ohms, capacitance 0.000001 farads, frequencies [10,100,1000] Hz; "
    "divider input 5 volts with 1000-ohm top and bottom resistors. "
    "Do not invent components, nested analysis objects, schema fields, assumptions, netlists, "
    "SPICE, commands, paths, evidence, verification, status, prose, or explanations."
)

_REPAIR_MESSAGE = (
    "Correct the seven flat submit_circuit_plan arguments so they satisfy the tool schema and "
    "the deterministic validation error codes. Preserve the user's requested topology and values. "
    "Use SI-base-unit numbers, every required field, exact zero for irrelevant fields, and no "
    "additional or nested fields."
)


def _stable_repair_context(
    prompt: str,
    repair_errors: Sequence[CircuitPlannerError],
) -> str:
    context = {
        "original_bounded_prompt": prompt,
        "stable_validation_errors": [
            {"code": error.code, "path": list(error.path)} for error in repair_errors[:8]
        ],
    }
    return json.dumps(context, ensure_ascii=True, separators=(",", ":"))


def _build_request_body(
    prompt: str,
    config: OpenRouterPlannerConfig,
    repair_errors: Sequence[CircuitPlannerError],
) -> dict[str, Any]:
    legacy = _legacy_build_request_body(prompt, config, ())
    user_content = prompt
    if repair_errors:
        user_content = f"{_REPAIR_MESSAGE}\n{_stable_repair_context(prompt, repair_errors)}"
    legacy["messages"] = [
        {"role": "system", "content": _SYSTEM_MESSAGE},
        {"role": "user", "content": user_content},
    ]
    legacy["tools"] = [_TOOL_DEFINITION]
    legacy["tool_choice"] = _TOOL_CHOICE
    legacy["provider"] = {"require_parameters": True}
    return legacy


async def plan_circuit_request(
    prompt: str,
    *,
    config: OpenRouterPlannerConfig | None = None,
) -> CircuitPlan:
    """Return one validated CircuitPlan using one forced OpenRouter tool call."""

    return await _plan_circuit_request_with_transport(prompt, config=config, transport=None)


async def _plan_circuit_request_with_transport(
    prompt: str,
    *,
    config: OpenRouterPlannerConfig | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> CircuitPlan:
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

    envelope = _decode_json_bytes(response_bytes, provider=True)
    return _extract_tool_plan_candidate(envelope)


def _extract_tool_plan_candidate(envelope: Any) -> str:
    if type(envelope) is not dict:
        raise _planner_error("planner.provider.envelope_invalid")
    choices = envelope.get("choices")
    if type(choices) is not list or len(choices) != 1:
        raise _planner_error("planner.provider.envelope_invalid", ("choices",))
    choice = choices[0]
    if type(choice) is not dict:
        raise _planner_error("planner.provider.envelope_invalid", ("choices", 0))
    if "error" in choice:
        raise _planner_error("planner.provider.envelope_invalid", ("choices", 0, "error"))
    if choice.get("finish_reason") != "tool_calls":
        raise _planner_error(
            "planner.provider.envelope_invalid", ("choices", 0, "finish_reason")
        )
    message = choice.get("message")
    if type(message) is not dict:
        raise _planner_error("planner.provider.envelope_invalid", ("choices", 0, "message"))
    if message.get("content") not in (None, ""):
        raise _planner_error(
            "planner.provider.envelope_invalid", ("choices", 0, "message", "content")
        )
    tool_calls = message.get("tool_calls")
    if type(tool_calls) is not list or len(tool_calls) != 1:
        raise _planner_error(
            "planner.provider.envelope_invalid", ("choices", 0, "message", "tool_calls")
        )
    tool_call = tool_calls[0]
    if type(tool_call) is not dict or tool_call.get("type") != "function":
        raise _planner_error(
            "planner.provider.envelope_invalid", ("choices", 0, "message", "tool_calls")
        )
    function = tool_call.get("function")
    if type(function) is not dict or function.get("name") != _TOOL_NAME:
        raise _planner_error(
            "planner.provider.envelope_invalid", ("choices", 0, "message", "tool_calls")
        )
    arguments = function.get("arguments")
    if type(arguments) is not str or arguments == "":
        raise _planner_error(
            "planner.provider.envelope_invalid", ("choices", 0, "message", "tool_calls")
        )
    if len(arguments.encode("utf-8")) > _MAX_CONTENT_BYTES:
        raise _planner_error("planner.provider.response_oversized")
    return _extract_flat_plan_candidate(arguments)


def _extract_flat_plan_candidate(content: str) -> str:
    stripped = content.strip(" \t\r\n")
    if not stripped or stripped.startswith("```"):
        raise _planner_error("planner.output.invalid_json")
    values = _decode_json_text(stripped, provider=False)
    if type(values) is not dict:
        raise _planner_error("planner.output.invalid_json")

    keys = set(values)
    if keys == _FLAT_VALUE_KEYS:
        return _flat_values_to_candidate(values)
    if keys == {"plan"} or keys == _CANDIDATE_KEYS:
        return _extract_plan_candidate(stripped)

    extra = keys - _FLAT_VALUE_KEYS
    if extra:
        raise _planner_error("planner.output.invalid_json", ("candidate", "unknown_field"))
    missing = sorted(_FLAT_VALUE_KEYS - keys, key=str)
    if missing:
        raise _planner_error("planner.output.invalid_json", ("candidate", missing[0]))
    raise _planner_error("planner.output.invalid_json")


def _flat_values_to_candidate(values: dict[str, Any]) -> str:
    topology = values["topology"]
    if topology in {"rc_low_pass", "rc_high_pass"}:
        _require_zero(values, "input_voltage_volts")
        _require_zero(values, "resistance_top_ohms")
        _require_zero(values, "resistance_bottom_ohms")
        analysis = "ac"
        parameters = {
            "resistance_ohms": values["resistance_ohms"],
            "capacitance_farads": values["capacitance_farads"],
        }
    elif topology == "resistive_divider":
        _require_zero(values, "resistance_ohms")
        _require_zero(values, "capacitance_farads")
        analysis = "dc"
        parameters = {
            "input_voltage_volts": values["input_voltage_volts"],
            "resistance_top_ohms": values["resistance_top_ohms"],
            "resistance_bottom_ohms": values["resistance_bottom_ohms"],
        }
    elif type(topology) is str:
        raise _planner_error("planner.plan.unsupported_topology", ("topology",))
    else:
        raise _planner_error("planner.plan.invalid", ("topology",))

    candidate = {
        "schema_version": "1.0",
        "topology": topology,
        "analysis": analysis,
        "parameters": parameters,
        "requested_frequencies_hz": values["requested_frequencies_hz"],
        "assumptions": [],
    }
    try:
        return json.dumps(candidate, allow_nan=False, separators=(",", ":"))
    except (TypeError, ValueError):
        raise _planner_error("planner.output.invalid_json") from None


def _require_zero(values: dict[str, Any], key: str) -> None:
    value = values[key]
    if type(value) not in {int, float} or not math.isfinite(value) or value != 0:
        raise _planner_error("planner.plan.invalid", (key,))


def _extract_plan_candidate(content: str) -> str:
    stripped = content.strip(" \t\r\n")
    if not stripped or stripped.startswith("```"):
        raise _planner_error("planner.output.invalid_json")
    wrapper = _decode_json_text(stripped, provider=False)
    if type(wrapper) is not dict:
        raise _planner_error("planner.output.invalid_json")
    if set(wrapper) == {"plan"}:
        candidate = wrapper["plan"]
    elif set(wrapper) == _CANDIDATE_KEYS:
        candidate = wrapper
    else:
        raise _planner_error("planner.output.invalid_json", ("candidate", "unknown_field"))
    if type(candidate) is not dict:
        raise _planner_error("planner.output.invalid_json", ("candidate",))
    try:
        return json.dumps(candidate, allow_nan=False, separators=(",", ":"))
    except (TypeError, ValueError):
        raise _planner_error("planner.output.invalid_json") from None


__all__ = ["plan_circuit_request"]
