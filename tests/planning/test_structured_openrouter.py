from __future__ import annotations

import asyncio
import json

import httpx2 as httpx
import pytest

from ai_electronics_lab.planning import CircuitPlannerError, OpenRouterPlannerConfig
from ai_electronics_lab.planning.structured_openrouter import (
    _extract_plan_candidate,
    _plan_circuit_request_with_transport,
)

SECRET = "sk-test-secret"
PROMPT = "Analyze an RC low-pass filter with explicit component values."
TOOL_NAME = "submit_circuit_plan"


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


def envelope(plan, *, tool_name=TOOL_NAME, content=None) -> dict:
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
                                "arguments": json.dumps({"plan": plan}, separators=(",", ":")),
                            },
                        }
                    ],
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


def test_forced_tool_request_returns_valid_plan_and_requires_tool_support():
    transport, calls = transport_from_responses(response(envelope(low_pass_plan())))

    plan = run(
        _plan_circuit_request_with_transport(
            PROMPT,
            config=config(),
            transport=transport,
        )
    )

    assert plan.topology == "rc_low_pass"
    assert len(calls) == 1
    body = json.loads(calls[0].content)
    assert "response_format" not in body
    assert body["provider"] == {"require_parameters": True}
    assert body["reasoning"] == {"effort": "low", "exclude": True}
    assert body["tool_choice"] == {
        "type": "function",
        "function": {"name": TOOL_NAME},
    }
    assert len(body["tools"]) == 1
    function = body["tools"][0]["function"]
    assert function["name"] == TOOL_NAME
    assert function["parameters"]["required"] == ["plan"]
    assert function["parameters"]["additionalProperties"] is False


def test_forced_tool_repair_uses_only_stable_validation_context():
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
    assert repair_body["tool_choice"]["function"]["name"] == TOOL_NAME


def test_forced_tool_response_rejects_unexpected_tool_name():
    transport, _calls = transport_from_responses(
        response(envelope(low_pass_plan(), tool_name="other_tool"))
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


def test_forced_tool_response_rejects_parallel_prose_content():
    transport, _calls = transport_from_responses(
        response(envelope(low_pass_plan(), content="untrusted prose"))
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


def test_structured_wrapper_must_contain_exactly_one_plan_key():
    content = json.dumps(
        {"plan": low_pass_plan(), "extra": True},
        separators=(",", ":"),
    )

    with pytest.raises(CircuitPlannerError) as caught:
        _extract_plan_candidate(content)

    assert caught.value.code == "planner.output.invalid_json"
    assert caught.value.path == ("candidate", "unknown_field")


def test_forced_tool_system_prompt_defines_deterministic_defaults():
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
    assert "submit_circuit_plan tool" in system_message
    assert "deterministic demonstration defaults" in system_message
    assert "1000 ohms" in system_message
    assert "0.000001 farads" in system_message
    assert "[10,100,1000]" in system_message
