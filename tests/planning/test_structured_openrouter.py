from __future__ import annotations

import asyncio
import json

import httpx2 as httpx
import pytest

from ai_electronics_lab.planning import CircuitPlannerError, OpenRouterPlannerConfig
from ai_electronics_lab.planning.structured_openrouter import (
    _plan_circuit_request_with_transport,
)

SECRET = "sk-test-secret"
PROMPT = (
    "Analyze an RC low-pass filter with 1 kΩ resistance, "
    "1 µF capacitance, and frequencies 10, 100, and 1000 Hz."
)


def config() -> OpenRouterPlannerConfig:
    return OpenRouterPlannerConfig(api_key=SECRET, max_tokens=800)


def low_pass_plan(**overrides):
    plan = {
        "schema_version": "1.0",
        "topology": "rc_low_pass",
        "analysis": "ac",
        "parameters": {
            "resistance_ohms": 1000.0,
            "capacitance_farads": 0.000001,
        },
        "requested_frequencies_hz": [10.0, 100.0, 1000.0],
        "assumptions": ["Ideal passive components."],
    }
    plan.update(overrides)
    return plan


def envelope(plan) -> dict:
    return {
        "choices": [
            {
                "finish_reason": "stop",
                "message": {
                    "role": "assistant",
                    "content": json.dumps({"plan": plan}, separators=(",", ":")),
                },
            }
        ]
    }


def response(payload) -> httpx.Response:
    encoded = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return httpx.Response(200, content=b"\n  " + encoded)


def transport_from_responses(*responses):
    calls = []

    async def handler(request):
        calls.append(request)
        return responses[min(len(calls) - 1, len(responses) - 1)]

    return httpx.MockTransport(handler), calls


def run(coro):
    return asyncio.run(coro)


def test_structured_request_returns_valid_plan_and_requires_schema_support():
    transport, calls = transport_from_responses(response(envelope(low_pass_plan())))

    plan = run(
        _plan_circuit_request_with_transport(
            PROMPT,
            config=config(),
            transport=transport,
        )
    )

    assert plan.topology == "rc_low_pass"
    assert plan.analysis == "ac"
    assert plan.to_dict()["parameters"] == {
        "capacitance_farads": 0.000001,
        "resistance_ohms": 1000.0,
    }
    assert len(calls) == 1

    body = json.loads(calls[0].content)
    assert body["response_format"]["type"] == "json_schema"
    assert body["response_format"]["json_schema"]["strict"] is True
    assert body["response_format"]["json_schema"]["schema"]["required"] == ["plan"]
    assert body["provider"] == {"require_parameters": True}
    assert body["reasoning"] == {"effort": "low", "exclude": True}
    assert body["stream"] is False
    assert body["temperature"] == 0
    assert body["max_tokens"] == 800
    assert "tools" not in body
    assert "functions" not in body


def test_structured_repair_uses_only_stable_validation_context():
    invalid = low_pass_plan(requested_frequencies_hz=[1000.0, 100.0, 10.0])
    transport, calls = transport_from_responses(
        response(envelope(invalid)),
        response(envelope(low_pass_plan())),
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
    repair_body = json.loads(calls[1].content)
    repair_message = repair_body["messages"][1]["content"]
    assert "planner.plan.invalid" in repair_message
    assert "requested_frequencies_hz" in repair_message
    assert "1000.0" not in repair_message
    assert repair_body["response_format"]["json_schema"]["strict"] is True


def test_structured_wrapper_must_contain_exactly_one_plan_key():
    bad_envelope = {
        "choices": [
            {
                "finish_reason": "stop",
                "message": {
                    "content": json.dumps(
                        {"plan": low_pass_plan(), "extra": True},
                        separators=(",", ":"),
                    )
                },
            }
        ]
    }
    transport, calls = transport_from_responses(response(bad_envelope))

    with pytest.raises(CircuitPlannerError) as caught:
        run(
            _plan_circuit_request_with_transport(
                PROMPT,
                config=config(),
                transport=transport,
            )
        )

    assert caught.value.code == "planner.output.invalid_json"
    assert caught.value.path == ("candidate", "unknown_field")
    assert len(calls) == 2


def test_structured_system_prompt_defines_deterministic_defaults():
    transport, calls = transport_from_responses(response(envelope(low_pass_plan())))

    plan = run(
        _plan_circuit_request_with_transport(
            "Show a low-pass filter.",
            config=config(),
            transport=transport,
        )
    )

    assert plan.topology == "rc_low_pass"
    body = json.loads(calls[0].content)
    system_message = body["messages"][0]["content"]
    assert "deterministic demonstration defaults" in system_message
    assert "1000 ohms" in system_message
    assert "0.000001 farads" in system_message
    assert "[10,100,1000]" in system_message
