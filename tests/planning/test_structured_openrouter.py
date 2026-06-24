from __future__ import annotations

import asyncio
import json

import httpx2 as httpx
import pytest

from ai_electronics_lab.planning import CircuitPlannerError, OpenRouterPlannerConfig
from ai_electronics_lab.planning.structured_openrouter import _plan_circuit_request_with_transport

PROMPT = "Analyze an RC low-pass filter with explicit component values."
TOOL_NAME = "submit_circuit_plan"
FLAT_KEYS = {
    "topology",
    "resistance_ohms",
    "capacitance_farads",
    "input_voltage_volts",
    "resistance_top_ohms",
    "resistance_bottom_ohms",
    "requested_frequencies_hz",
}


def config() -> OpenRouterPlannerConfig:
    return OpenRouterPlannerConfig(api_key="fixture-value", max_tokens=800)


def flat_low_pass(**overrides):
    values = {
        "topology": "rc_low_pass",
        "resistance_ohms": 1000.0,
        "capacitance_farads": 0.000001,
        "input_voltage_volts": 0.0,
        "resistance_top_ohms": 0.0,
        "resistance_bottom_ohms": 0.0,
        "requested_frequencies_hz": [10.0, 100.0, 1000.0],
    }
    values.update(overrides)
    return values


def envelope(arguments, *, tool_name=TOOL_NAME, content=None) -> dict:
    return {
        "choices": [
            {
                "finish_reason": "tool_calls",
                "message": {
                    "content": content,
                    "tool_calls": [
                        {
                            "id": "call_test",
                            "type": "function",
                            "function": {
                                "name": tool_name,
                                "arguments": json.dumps(arguments, separators=(",", ":")),
                            },
                        }
                    ],
                },
            }
        ]
    }


def response(payload) -> httpx.Response:
    encoded = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return httpx.Response(200, content=encoded)


def transport_from_responses(*responses):
    calls = []

    async def handler(request):
        calls.append(request)
        return responses[min(len(calls) - 1, len(responses) - 1)]

    return httpx.MockTransport(handler), calls


def run(coro):
    return asyncio.run(coro)


def test_flat_forced_tool_request_returns_valid_plan():
    transport, calls = transport_from_responses(response(envelope(flat_low_pass())))

    plan = run(
        _plan_circuit_request_with_transport(
            PROMPT,
            config=config(),
            transport=transport,
        )
    )

    assert plan.topology == "rc_low_pass"
    assert plan.analysis == "ac"
    assert plan.requested_frequencies_hz == (10.0, 100.0, 1000.0)
    assert len(calls) == 1

    body = json.loads(calls[0].content)
    assert "response_format" not in body
    assert body["provider"] == {"require_parameters": True}
    assert body["tool_choice"] == {
        "type": "function",
        "function": {"name": TOOL_NAME},
    }
    parameters = body["tools"][0]["function"]["parameters"]
    assert set(parameters["properties"]) == FLAT_KEYS
    assert set(parameters["required"]) == FLAT_KEYS
    assert parameters["additionalProperties"] is False
    assert "anyOf" not in json.dumps(parameters)


def test_flat_repair_uses_only_stable_error_context():
    invalid = flat_low_pass(requested_frequencies_hz=[1000.0, 100.0, 10.0])
    transport, calls = transport_from_responses(
        response(envelope(invalid)),
        response(envelope(flat_low_pass())),
    )

    plan = run(
        _plan_circuit_request_with_transport(
            PROMPT,
            config=config(),
            transport=transport,
        )
    )

    assert plan.topology == "rc_low_pass"
    assert len(calls) == 2
    repair_message = json.loads(calls[1].content)["messages"][1]["content"]
    assert "planner.plan.invalid" in repair_message
    assert "requested_frequencies_hz" in repair_message
    assert "[1000.0,100.0,10.0]" not in repair_message


def test_nonzero_irrelevant_field_can_use_single_repair():
    transport, calls = transport_from_responses(
        response(envelope(flat_low_pass(input_voltage_volts=5.0))),
        response(envelope(flat_low_pass())),
    )

    plan = run(
        _plan_circuit_request_with_transport(
            PROMPT,
            config=config(),
            transport=transport,
        )
    )

    assert plan.topology == "rc_low_pass"
    assert len(calls) == 2
    repair_message = json.loads(calls[1].content)["messages"][1]["content"]
    assert "input_voltage_volts" in repair_message


def test_unexpected_tool_name_is_rejected():
    transport, _calls = transport_from_responses(
        response(envelope(flat_low_pass(), tool_name="other_tool"))
    )

    with pytest.raises(CircuitPlannerError) as caught:
        run(
            _plan_circuit_request_with_transport(
                PROMPT,
                config=config(),
                transport=transport,
            )
        )

    assert caught.value.code == "planner.provider.envelope_invalid"


def test_parallel_prose_is_rejected():
    transport, _calls = transport_from_responses(
        response(envelope(flat_low_pass(), content="untrusted prose"))
    )

    with pytest.raises(CircuitPlannerError) as caught:
        run(
            _plan_circuit_request_with_transport(
                PROMPT,
                config=config(),
                transport=transport,
            )
        )

    assert caught.value.code == "planner.provider.envelope_invalid"
    assert caught.value.path == ("choices", 0, "message", "content")


def test_system_prompt_defines_flat_defaults_and_zero_policy():
    transport, calls = transport_from_responses(response(envelope(flat_low_pass())))

    run(
        _plan_circuit_request_with_transport(
            "Show a low-pass filter.",
            config=config(),
            transport=transport,
        )
    )

    system_message = json.loads(calls[0].content)["messages"][0]["content"]
    assert "seven flat schema fields" in system_message
    assert "deterministic demonstration defaults" in system_message
    assert "zero for all three divider-only fields" in system_message
