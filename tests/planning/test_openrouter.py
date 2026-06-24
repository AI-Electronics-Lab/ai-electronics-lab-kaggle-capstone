from __future__ import annotations

import asyncio
import json

import httpx2 as httpx
import pytest

from ai_electronics_lab.planning import (
    OPENROUTER_PLANNER_VERSION,
    CircuitPlannerError,
    OpenRouterPlannerConfig,
    load_openrouter_planner_config,
    plan_circuit_request,
)
from ai_electronics_lab.planning import openrouter as openrouter_module
from ai_electronics_lab.planning.openrouter import _plan_circuit_request_with_transport

SECRET = "sk-test-secret"
PROMPT = "Design a 1 kHz RC low-pass filter."
HOSTILE_PROMPT_FRAGMENT = "hostile-provider-prompt-fragment-sentinel"
HOSTILE_URL = "https://example.invalid/openrouter?token=sk-url-secret"
HOSTILE_CONTROL_KEY = "line1\nline2\x1fsk-control-secret"
HOSTILE_LONG_KEY = "sk-long-secret-" + "x" * 600
HOSTILE_SENTINELS = (SECRET, PROMPT, HOSTILE_URL, HOSTILE_CONTROL_KEY, HOSTILE_LONG_KEY)


def candidate(**overrides):
    values = {
        "schema_version": "1.0",
        "topology": "rc_low_pass",
        "analysis": "ac",
        "parameters": {"resistance_ohms": 1600, "capacitance_farads": 1e-7},
        "requested_frequencies_hz": [10.0, 1000.0, 100000.0],
        "assumptions": ["Ideal passive components."],
    }
    values.update(overrides)
    return values


def envelope(content, **choice_overrides):
    choice = {
        "message": {"role": "assistant", "content": content},
        "finish_reason": "stop",
    }
    choice.update(choice_overrides)
    return {"id": "discarded", "choices": [choice], "usage": {"discarded": True}}


def response_for(content, status_code=200):
    body = content if isinstance(content, bytes) else json.dumps(content).encode("utf-8")
    return httpx.Response(status_code, content=body)


def config(**overrides):
    values = {"api_key": SECRET}
    values.update(overrides)
    return OpenRouterPlannerConfig(**values)


def json_candidate(**overrides):
    return json.dumps(candidate(**overrides), separators=(",", ":"))


def transport_from_responses(*responses):
    calls = []

    async def handler(request):
        calls.append(request)
        response = responses[min(len(calls) - 1, len(responses) - 1)]
        if isinstance(response, Exception):
            raise response
        return response

    return httpx.MockTransport(handler), calls


def render_error(error):
    return "".join(
        (
            error.code,
            error.message,
            str(error),
            repr(error),
            json.dumps(error.to_dict(), sort_keys=True),
        )
    )


def assert_no_hostile_text(value, *extra_sentinels):
    rendered = value if isinstance(value, str) else json.dumps(value, sort_keys=True)
    for sentinel in (*HOSTILE_SENTINELS, *extra_sentinels):
        assert sentinel not in rendered


def assert_no_provider_controlled_text(value, *extra_sentinels):
    rendered = value if isinstance(value, str) else json.dumps(value, sort_keys=True)
    provider_sentinels = tuple(
        sentinel for sentinel in HOSTILE_SENTINELS if sentinel != PROMPT
    )
    for sentinel in (*provider_sentinels, *extra_sentinels):
        assert sentinel not in rendered


async def assert_planner_error(coro, code):
    with pytest.raises(CircuitPlannerError) as caught:
        await coro
    assert caught.value.code == code
    rendered = render_error(caught.value)
    assert_no_hostile_text(rendered)
    assert "raw-provider-body" not in rendered
    assert "ValueError" not in rendered
    assert "OverflowError" not in rendered
    assert "Exceeds the limit" not in rendered
    assert "int string conversion" not in rendered
    return caught.value


def run(coro):
    return asyncio.run(coro)


def test_public_exports_and_error_serialization_are_deterministic():
    error = CircuitPlannerError("planner.input.empty", ("prompt",))
    assert OPENROUTER_PLANNER_VERSION == "1.0"
    assert error.to_dict() == {
        "code": "planner.input.empty",
        "path": ["prompt"],
        "message": "Prompt must not be empty.",
    }
    cfg = config()
    assert SECRET not in repr(cfg)
    assert SECRET not in json.dumps(cfg.to_dict())


def test_direct_error_construction_normalizes_unsafe_path_and_message():
    error = CircuitPlannerError(
        "planner.input.empty",
        (SECRET,),
        f"hostile message {HOSTILE_URL} {HOSTILE_CONTROL_KEY}",
    )

    assert error.to_dict() == {
        "code": "planner.input.empty",
        "path": ["error_path"],
        "message": "Prompt must not be empty.",
    }
    assert_no_hostile_text(render_error(error))


def test_direct_error_construction_normalizes_unsafe_code_without_echoing():
    error = CircuitPlannerError(SECRET, ("prompt",), HOSTILE_URL)

    assert error.code == "planner.config.invalid"
    assert error.path == ("prompt",)
    assert error.message == "OpenRouter planner configuration is invalid."
    assert_no_hostile_text(render_error(error))


def test_direct_error_construction_rejects_hostile_path_and_message_objects_safely():
    class HostilePath:
        def __iter__(self):
            raise RuntimeError(SECRET)

    class HostileMessage:
        def __eq__(self, _other):
            raise RuntimeError(HOSTILE_URL)

        def __str__(self):
            raise RuntimeError(HOSTILE_CONTROL_KEY)

    error = CircuitPlannerError("planner.input.empty", HostilePath(), HostileMessage())

    assert error.to_dict() == {
        "code": "planner.input.empty",
        "path": ["error_path"],
        "message": "Prompt must not be empty.",
    }
    assert_no_hostile_text(render_error(error))


def test_load_config_reads_only_openrouter_contract(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", f" {SECRET} ")
    monkeypatch.setenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1/")
    monkeypatch.setenv("OPENROUTER_MODEL", "openai/gpt-oss-120b:free")
    monkeypatch.setenv("OPENROUTER_TIMEOUT_SECONDS", "3")
    monkeypatch.setenv("OPENROUTER_MAX_TOKENS", "128")
    monkeypatch.setenv("LLM_API_KEY", "ignored")

    cfg = load_openrouter_planner_config()

    assert cfg.api_key == SECRET
    assert cfg.base_url == "https://openrouter.ai/api/v1"
    assert cfg.timeout_seconds == 3.0
    assert cfg.max_tokens == 128


@pytest.mark.parametrize(
    "base_url",
    [
        "https://openrouter.ai/api/v1",
        "https://openrouter.ai/api/v1/",
        "https://openrouter.ai:443/api/v1",
        "https://openrouter.ai:443/api/v1/",
    ],
)
def test_config_accepts_only_canonical_openrouter_base_urls(base_url):
    cfg = config(base_url=base_url)

    assert cfg.base_url == "https://openrouter.ai/api/v1"


@pytest.mark.parametrize(
    "base_url",
    [
        "http://openrouter.ai/api/v1",
        "https://example.com/api/v1",
        "https://openrouter.ai:444/api/v1",
        "https://user@openrouter.ai/api/v1",
        "https://openrouter.ai/api/v1/chat",
        "https://openrouter.ai/api/v1//",
        "https://openrouter.ai/api/v1?x=1",
    ],
)
def test_config_rejects_unapproved_base_url(base_url):
    with pytest.raises(CircuitPlannerError) as caught:
        config(base_url=base_url)
    assert caught.value.code == "planner.config.invalid"


@pytest.mark.parametrize(
    "base_url",
    [
        "https://openrouter.ai:bad/api/v1",
        "https://openrouter.ai:/api/v1",
        "https://openrouter.ai:+443/api/v1",
        "https://openrouter.ai:-443/api/v1",
        "https://openrouter.ai: 443/api/v1",
        "https://openrouter.ai:443x/api/v1",
        "https://openrouter.ai:443.0/api/v1",
        "https://openrouter.ai:99999/api/v1",
        "https://openrouter.ai:0443/api/v1",
    ],
)
def test_config_rejects_malformed_base_url_ports_without_raw_urlparse_text(base_url):
    with pytest.raises(CircuitPlannerError) as caught:
        config(base_url=base_url)

    assert caught.value.code == "planner.config.invalid"
    rendered = str(caught.value) + repr(caught.value) + json.dumps(caught.value.to_dict())
    assert "Port could not" not in rendered
    assert "ValueError" not in rendered
    assert base_url not in rendered


@pytest.mark.parametrize(
    "base_url",
    [
        "https://openrouter.ai:bad/api/v1",
        "https://openrouter.ai:/api/v1",
        "https://openrouter.ai:+443/api/v1",
        "https://openrouter.ai: 443/api/v1",
        "https://openrouter.ai:99999/api/v1",
    ],
)
def test_env_config_rejects_malformed_base_url_ports_without_raw_urlparse_text(
    monkeypatch, base_url
):
    monkeypatch.setenv("OPENROUTER_API_KEY", SECRET)
    monkeypatch.setenv("OPENROUTER_BASE_URL", base_url)

    with pytest.raises(CircuitPlannerError) as caught:
        load_openrouter_planner_config()

    assert caught.value.code == "planner.config.invalid"
    rendered = str(caught.value) + repr(caught.value) + json.dumps(caught.value.to_dict())
    assert "Port could not" not in rendered
    assert "ValueError" not in rendered
    assert base_url not in rendered


SEMICOLON_PARAMETER_BASE_URLS = [
    "https://openrouter.ai/api/v1;param",
    "https://openrouter.ai/api/v1/;param",
    "https://openrouter.ai/api/v1;%2fchat",
    "https://openrouter.ai:443/api/v1;param",
    "https://openrouter.ai/api/v1;param%20value",
    "https://openrouter.ai/api/v1;%3bparam",
    "https://openrouter.ai/api/v1;param?x=1",
    "https://openrouter.ai/api/v1;param#frag",
    "https://openrouter.ai/api/v1;param?x=1#frag",
]


def assert_safe_config_error(caught, rejected_value):
    assert caught.value.code == "planner.config.invalid"
    rendered = str(caught.value) + repr(caught.value) + json.dumps(caught.value.to_dict())
    assert rejected_value not in rendered
    assert "param" not in rendered
    assert "%2f" not in rendered
    assert "%20" not in rendered
    assert "%3b" not in rendered
    assert "urlparse" not in rendered
    assert "urllib" not in rendered
    assert "ValueError" not in rendered


@pytest.mark.parametrize("base_url", SEMICOLON_PARAMETER_BASE_URLS)
def test_config_rejects_semicolon_base_url_parameters_safely(base_url):
    with pytest.raises(CircuitPlannerError) as caught:
        config(base_url=base_url)

    assert_safe_config_error(caught, base_url)


@pytest.mark.parametrize("base_url", SEMICOLON_PARAMETER_BASE_URLS)
def test_env_config_rejects_semicolon_base_url_parameters_safely(monkeypatch, base_url):
    monkeypatch.setenv("OPENROUTER_API_KEY", SECRET)
    monkeypatch.setenv("OPENROUTER_BASE_URL", base_url)

    with pytest.raises(CircuitPlannerError) as caught:
        load_openrouter_planner_config()

    assert_safe_config_error(caught, base_url)


@pytest.mark.parametrize(
    ("kwargs", "code"),
    [
        ({"api_key": ""}, "planner.config.api_key_missing"),
        ({"api_key": "x\n"}, "planner.config.invalid"),
        ({"model": ""}, "planner.config.invalid"),
        ({"model": "x\n"}, "planner.config.invalid"),
        ({"timeout_seconds": True}, "planner.config.invalid"),
        ({"timeout_seconds": 0.5}, "planner.config.invalid"),
        ({"timeout_seconds": float("inf")}, "planner.config.invalid"),
        ({"max_tokens": True}, "planner.config.invalid"),
        ({"max_tokens": 63}, "planner.config.invalid"),
    ],
)
def test_config_rejects_invalid_values(kwargs, code):
    with pytest.raises(CircuitPlannerError) as caught:
        config(**kwargs)
    assert caught.value.code == code


def test_exact_request_construction_and_forbidden_fields_absent():
    transport, calls = transport_from_responses(response_for(envelope(json_candidate())))

    plan = run(_plan_circuit_request_with_transport(PROMPT, config=config(max_tokens=128), transport=transport))

    assert plan.topology == "rc_low_pass"
    assert len(calls) == 1
    request = calls[0]
    assert str(request.url) == "https://openrouter.ai/api/v1/chat/completions"
    assert request.method == "POST"
    assert request.headers["authorization"] == f"Bearer {SECRET}"
    assert request.headers["content-type"] == "application/json"
    assert request.headers["accept"] == "application/json"
    body = json.loads(request.content)
    assert body == {
        "model": "openai/gpt-oss-120b:free",
        "messages": [
            {"role": "system", "content": body["messages"][0]["content"]},
            {"role": "user", "content": PROMPT},
        ],
        "temperature": 0,
        "stream": False,
        "max_tokens": 128,
        "reasoning": {"effort": "low", "exclude": True},
    }
    forbidden = {"response_format", "tools", "functions", "plugins", "web_search", "models"}
    assert forbidden.isdisjoint(body)


@pytest.mark.parametrize(
    "expected",
    [
        candidate(topology="rc_low_pass"),
        candidate(topology="rc_high_pass"),
        candidate(
            topology="resistive_divider",
            analysis="dc",
            parameters={
                "resistance_top_ohms": 10000,
                "resistance_bottom_ohms": 10000,
                "input_voltage_volts": 5.0,
            },
            requested_frequencies_hz=[],
        ),
    ],
)
def test_valid_plans_for_all_supported_topologies(expected):
    transport, _calls = transport_from_responses(
        response_for(envelope(json.dumps(expected, separators=(",", ":"))))
    )

    plan = run(
        _plan_circuit_request_with_transport("Design supported circuit.", config=config(), transport=transport)
    )

    assert plan.schema_version == expected["schema_version"]
    assert plan.topology == expected["topology"]
    assert plan.analysis == expected["analysis"]
    assert plan.to_dict()["parameters"] == expected["parameters"]
    assert plan.to_dict()["requested_frequencies_hz"] == expected["requested_frequencies_hz"]
    assert plan.to_dict()["assumptions"] == expected["assumptions"]
    assert json.loads(plan.to_json()) == plan.to_dict()


@pytest.mark.parametrize(
    ("prompt", "code"),
    [
        (None, "planner.input.type"),
        ("   ", "planner.input.empty"),
        ("x" * 4001, "planner.input.too_large"),
        ("😀" * 4097, "planner.input.too_large"),
    ],
)
def test_prompt_rejection_happens_before_config_or_network(prompt, code):
    transport, calls = transport_from_responses(response_for(envelope(json_candidate())))
    run(
        assert_planner_error(
            _plan_circuit_request_with_transport(prompt, config=None, transport=transport),
            code,
        )
    )
    assert calls == []


def test_config_rejection_happens_before_network(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    transport, calls = transport_from_responses(response_for(envelope(json_candidate())))

    run(
        assert_planner_error(
            _plan_circuit_request_with_transport(PROMPT, config=None, transport=transport),
            "planner.config.api_key_missing",
        )
    )
    assert calls == []


@pytest.mark.parametrize(
    ("response", "code"),
    [
        (httpx.TimeoutException("raw-provider-body"), "planner.provider.timeout"),
        (httpx.ConnectError("raw-provider-body"), "planner.provider.network_error"),
        (response_for({"raw-provider-body": True}, 500), "planner.provider.http_error"),
        (response_for({"choices": []}, 302), "planner.provider.http_error"),
        (httpx.Response(200, content=b"x" * 65537), "planner.provider.response_oversized"),
        (httpx.Response(200, content=b"\xff"), "planner.provider.envelope_invalid"),
        (httpx.Response(200, content=b"{"), "planner.provider.envelope_invalid"),
        (
            httpx.Response(200, content=b'{"choices":[],"choices":[]}'),
            "planner.provider.envelope_invalid",
        ),
        (
            httpx.Response(200, content=b'{"choices":[{"x":NaN}]}'),
            "planner.provider.envelope_invalid",
        ),
    ],
)
def test_provider_transport_and_json_failures_do_not_repair(response, code):
    transport, calls = transport_from_responses(response)

    run(
        assert_planner_error(
            _plan_circuit_request_with_transport(PROMPT, config=config(), transport=transport),
            code,
        )
    )
    assert len(calls) == 1


@pytest.mark.parametrize(
    ("provider", "code"),
    [
        ({"choices": []}, "planner.provider.envelope_invalid"),
        ({"choices": [{}, {}]}, "planner.provider.envelope_invalid"),
        (
            {"choices": [{"error": {"message": "raw-provider-body"}, "finish_reason": "stop"}]},
            "planner.provider.envelope_invalid",
        ),
        (
            {"choices": [{"message": {}, "finish_reason": "stop"}]},
            "planner.provider.content_missing",
        ),
        (
            {"choices": [{"message": {"content": 4}, "finish_reason": "stop"}]},
            "planner.provider.content_missing",
        ),
        (
            {"choices": [{"message": {"content": json_candidate()}, "finish_reason": "length"}]},
            "planner.provider.envelope_invalid",
        ),
        (
            {
                "choices": [
                    {
                        "message": {"content": json_candidate(), "tool_calls": [{"id": "x"}]},
                        "finish_reason": "stop",
                    }
                ]
            },
            "planner.provider.envelope_invalid",
        ),
        (
            {"choices": [{"message": {"content": "x" * 16385}, "finish_reason": "stop"}]},
            "planner.provider.response_oversized",
        ),
    ],
)
def test_provider_envelope_failures_do_not_repair(provider, code):
    transport, calls = transport_from_responses(response_for(provider))

    run(
        assert_planner_error(
            _plan_circuit_request_with_transport(PROMPT, config=config(), transport=transport),
            code,
        )
    )
    assert len(calls) == 1


@pytest.mark.parametrize(
    "content",
    [
        "```json\n{}\n```",
        "prefix {}",
        "{} suffix",
        "{}{}",
        '{"schema_version":"1.0","schema_version":"1.0"}',
        '{"schema_version":NaN}',
        "[" * 81 + "]" * 81,
    ],
)
def test_candidate_json_failures_can_repair(content):
    transport, calls = transport_from_responses(
        response_for(envelope(content)),
        response_for(envelope(json_candidate())),
    )

    plan = run(_plan_circuit_request_with_transport(PROMPT, config=config(), transport=transport))

    assert plan.topology == "rc_low_pass"
    assert len(calls) == 2
    repair_body = json.loads(calls[1].content)
    repair_message = repair_body["messages"][1]["content"]
    repair_context = json.loads(repair_message.split("Repair context JSON:\n", 1)[1])

    assert set(repair_context) == {
        "original_bounded_prompt",
        "stable_validation_errors",
    }
    assert repair_context["original_bounded_prompt"] == PROMPT
    assert repair_message.count(PROMPT) == 1
    assert content not in repair_message
    assert "planner.output.invalid_json" in repair_message


@pytest.mark.parametrize(
    "bad_candidate",
    [
        {"schema_version": "1.0"},
        {**candidate(), "netlist": "raw-provider-body"},
        {**candidate(), "extra": True},
    ],
)
def test_candidate_field_failures_can_repair(bad_candidate):
    transport, calls = transport_from_responses(
        response_for(envelope(json.dumps(bad_candidate))),
        response_for(envelope(json_candidate())),
    )

    plan = run(_plan_circuit_request_with_transport(PROMPT, config=config(), transport=transport))

    assert plan.topology == "rc_low_pass"
    assert len(calls) == 2


@pytest.mark.parametrize("hostile_key", [SECRET, HOSTILE_URL, HOSTILE_PROMPT_FRAGMENT, HOSTILE_CONTROL_KEY])
def test_unknown_top_level_candidate_keys_use_fixed_safe_repair_path(hostile_key, caplog):
    bad_candidate = {**candidate(), hostile_key: True}
    transport, calls = transport_from_responses(
        response_for(envelope(json.dumps(bad_candidate))),
        response_for(envelope(json_candidate())),
    )

    plan = run(_plan_circuit_request_with_transport(PROMPT, config=config(), transport=transport))

    assert plan.topology == "rc_low_pass"
    assert len(calls) == 2
    repair_content = json.loads(calls[1].content)["messages"][1]["content"]
    assert '"path":["candidate","unknown_field"]' in repair_content
    assert_no_provider_controlled_text(repair_content, hostile_key)
    assert_no_hostile_text(caplog.text, hostile_key)


def test_unknown_long_control_candidate_key_uses_fixed_safe_repair_path(caplog):
    hostile_key = HOSTILE_CONTROL_KEY + HOSTILE_LONG_KEY
    bad_candidate = {**candidate(), hostile_key: True}
    transport, calls = transport_from_responses(
        response_for(envelope(json.dumps(bad_candidate))),
        response_for(envelope(json_candidate())),
    )

    plan = run(_plan_circuit_request_with_transport(PROMPT, config=config(), transport=transport))

    assert plan.topology == "rc_low_pass"
    repair_content = json.loads(calls[1].content)["messages"][1]["content"]
    assert '"path":["candidate","unknown_field"]' in repair_content
    assert_no_provider_controlled_text(repair_content, hostile_key)
    assert_no_hostile_text(caplog.text, hostile_key)


def test_unknown_topology_parameter_key_uses_fixed_safe_repair_path(caplog):
    hostile_parameters = {
        "resistance_ohms": 1600,
        "capacitance_farads": 1e-7,
        SECRET: 1,
    }
    transport, calls = transport_from_responses(
        response_for(envelope(json_candidate(parameters=hostile_parameters))),
        response_for(envelope(json_candidate())),
    )

    plan = run(_plan_circuit_request_with_transport(PROMPT, config=config(), transport=transport))

    assert plan.topology == "rc_low_pass"
    repair_content = json.loads(calls[1].content)["messages"][1]["content"]
    assert '"path":["parameters","unknown_field"]' in repair_content
    assert_no_provider_controlled_text(repair_content)
    assert_no_hostile_text(caplog.text)


def test_duplicate_candidate_key_uses_fixed_safe_repair_path(caplog):
    bad = (
        f'{{"{SECRET}":1,"{SECRET}":2,'
        '"schema_version":"1.0","topology":"rc_low_pass","analysis":"ac",'
        '"parameters":{"resistance_ohms":1600,"capacitance_farads":1e-7},'
        '"requested_frequencies_hz":[10.0,1000.0,100000.0],'
        '"assumptions":["Ideal passive components."]}'
    )
    transport, calls = transport_from_responses(
        response_for(envelope(bad)),
        response_for(envelope(json_candidate())),
    )

    plan = run(_plan_circuit_request_with_transport(PROMPT, config=config(), transport=transport))

    assert plan.topology == "rc_low_pass"
    repair_content = json.loads(calls[1].content)["messages"][1]["content"]
    assert '"path":["candidate","duplicate_key"]' in repair_content
    assert_no_provider_controlled_text(repair_content)
    assert_no_hostile_text(caplog.text)


def test_duplicate_provider_envelope_key_uses_fixed_safe_error_path(caplog):
    body = (
        f'{{"{SECRET}":1,"{SECRET}":2,'
        '"choices":[{"message":{"content":"{}"},"finish_reason":"stop"}]}'
    ).encode()
    transport, calls = transport_from_responses(httpx.Response(200, content=body))

    error = run(
        assert_planner_error(
            _plan_circuit_request_with_transport(PROMPT, config=config(), transport=transport),
            "planner.provider.envelope_invalid",
        )
    )

    assert error.path == ("provider_envelope", "duplicate_key")
    assert len(calls) == 1
    assert_no_hostile_text(caplog.text)


def test_duplicate_nested_candidate_key_uses_fixed_safe_repair_path(caplog):
    bad = raw_json_candidate(
        parameters_json=(
            f'{{"{SECRET}":1,"{SECRET}":2,'
            '"resistance_ohms":1600,"capacitance_farads":1e-7}'
        )
    )
    transport, calls = transport_from_responses(
        response_for(envelope(bad)),
        response_for(envelope(json_candidate())),
    )

    plan = run(_plan_circuit_request_with_transport(PROMPT, config=config(), transport=transport))

    assert plan.topology == "rc_low_pass"
    repair_content = json.loads(calls[1].content)["messages"][1]["content"]
    assert '"path":["candidate","duplicate_key"]' in repair_content
    assert_no_provider_controlled_text(repair_content)
    assert_no_hostile_text(caplog.text)


def test_second_invalid_response_exhausts_repair_without_hostile_text(caplog):
    bad_candidate = {**candidate(), SECRET: True}
    transport, calls = transport_from_responses(
        response_for(envelope(json.dumps(bad_candidate))),
        response_for(envelope(json.dumps(bad_candidate))),
    )

    error = run(
        assert_planner_error(
            _plan_circuit_request_with_transport(PROMPT, config=config(), transport=transport),
            "planner.repair.exhausted",
        )
    )

    assert error.path == ()
    assert len(calls) == 2
    repair_content = json.loads(calls[1].content)["messages"][1]["content"]
    assert_no_provider_controlled_text(repair_content)
    assert_no_hostile_text(caplog.text)


def test_known_safe_schema_paths_remain_deterministic_and_useful():
    with pytest.raises(CircuitPlannerError) as caught:
        openrouter_module._candidate_to_plan(
            json_candidate(parameters={"resistance_ohms": 0, "capacitance_farads": 1e-7}),
            repair=False,
        )

    assert caught.value.code == "planner.plan.invalid"
    assert caught.value.path == ("parameters", "resistance_ohms")

    with pytest.raises(CircuitPlannerError) as missing:
        openrouter_module._candidate_to_plan(
            json.dumps({key: value for key, value in candidate().items() if key != "analysis"}),
            repair=False,
        )

    assert missing.value.code == "planner.output.invalid_json"
    assert missing.value.path == ("candidate", "analysis")


def test_unsupported_topology_is_not_repairable():
    bad = json_candidate(topology="bjt_common_emitter")
    transport, calls = transport_from_responses(response_for(envelope(bad)))

    run(
        assert_planner_error(
            _plan_circuit_request_with_transport(PROMPT, config=config(), transport=transport),
            "planner.plan.unsupported_topology",
        )
    )
    assert len(calls) == 1


def test_circuit_plan_validation_can_repair():
    bad = json_candidate(parameters={"resistance_ohms": 0, "capacitance_farads": 1e-7})
    transport, calls = transport_from_responses(
        response_for(envelope(bad)),
        response_for(envelope(json_candidate())),
    )

    plan = run(_plan_circuit_request_with_transport(PROMPT, config=config(), transport=transport))

    assert plan.parameters["resistance_ohms"] == 1600
    assert len(calls) == 2


def test_repair_exhaustion_after_second_invalid_candidate():
    bad = json_candidate(parameters={"resistance_ohms": 0, "capacitance_farads": 1e-7})
    transport, calls = transport_from_responses(
        response_for(envelope(bad)),
        response_for(envelope(bad)),
    )

    run(
        assert_planner_error(
            _plan_circuit_request_with_transport(PROMPT, config=config(), transport=transport),
            "planner.repair.exhausted",
        )
    )
    assert len(calls) == 2


def test_provider_failure_after_repairable_first_failure_is_not_repair_exhaustion():
    transport, calls = transport_from_responses(
        response_for(envelope("{}")),
        response_for({"raw-provider-body": True}, 500),
    )

    run(
        assert_planner_error(
            _plan_circuit_request_with_transport(PROMPT, config=config(), transport=transport),
            "planner.provider.http_error",
        )
    )
    assert len(calls) == 2



def raw_json_candidate(*, parameters_json=None, requested_frequencies_json=None):
    parameters = parameters_json or '{"resistance_ohms":1600,"capacitance_farads":1e-7}'
    frequencies = requested_frequencies_json or "[10.0,1000.0,100000.0]"
    return (
        '{"schema_version":"1.0","topology":"rc_low_pass","analysis":"ac",'
        f'"parameters":{parameters},"requested_frequencies_hz":{frequencies},'
        '"assumptions":["Ideal passive components."]}'
    )


def test_public_planner_constructs_isolated_async_client_without_real_network(monkeypatch):
    constructed = []
    streamed = []

    class StreamContext:
        def __init__(self, response):
            self.response = response

        async def __aenter__(self):
            return self.response

        async def __aexit__(self, exc_type, exc, traceback):
            return False

    class RecordingAsyncClient:
        def __init__(self, **kwargs):
            constructed.append(kwargs)

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return False

        def stream(self, method, url, *, headers, content):
            streamed.append(
                {
                    "method": method,
                    "url": url,
                    "headers": headers,
                    "content": content,
                }
            )
            return StreamContext(response_for(envelope(json_candidate())))

    monkeypatch.setenv("HTTP_PROXY", "http://proxy.invalid:8080")
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.invalid:8443")
    monkeypatch.setenv("ALL_PROXY", "http://proxy.invalid:8000")
    monkeypatch.setenv("NO_PROXY", "openrouter.ai")
    monkeypatch.setenv("NETRC", "/tmp/hostile-netrc")
    monkeypatch.setattr(openrouter_module.httpx, "AsyncClient", RecordingAsyncClient)

    plan = run(plan_circuit_request(PROMPT, config=config()))

    assert plan.topology == "rc_low_pass"
    assert len(constructed) == 1
    assert constructed[0]["trust_env"] is False
    assert constructed[0]["follow_redirects"] is False
    assert constructed[0]["verify"] is True
    assert constructed[0]["transport"] is None
    assert "mounts" not in constructed[0]
    assert streamed[0]["headers"]["Authorization"] == f"Bearer {SECRET}"
    assert b"proxy.invalid" not in streamed[0]["content"]
    assert b"hostile-netrc" not in streamed[0]["content"]


def test_candidate_integer_longer_than_python_limit_can_repair_without_raw_valueerror():
    huge_literal = "1" * (openrouter_module._MAX_JSON_INTEGER_DIGITS + 1)
    bad = raw_json_candidate(
        parameters_json=(
            f'{{"resistance_ohms":{huge_literal},"capacitance_farads":1e-7}}'
        )
    )
    transport, calls = transport_from_responses(
        response_for(envelope(bad)),
        response_for(envelope(json_candidate())),
    )

    plan = run(_plan_circuit_request_with_transport(PROMPT, config=config(), transport=transport))

    assert plan.topology == "rc_low_pass"
    assert len(calls) == 2
    assert "planner.output.invalid_json" in json.loads(calls[1].content)["messages"][1]["content"]


def test_candidate_smaller_huge_integer_validation_overflow_can_repair_safely():
    huge_literal = "9" * (openrouter_module._MAX_JSON_INTEGER_DIGITS - 1)
    bad = raw_json_candidate(
        parameters_json=(
            f'{{"resistance_ohms":{huge_literal},"capacitance_farads":1e-7}}'
        )
    )
    transport, calls = transport_from_responses(
        response_for(envelope(bad)),
        response_for(envelope(json_candidate())),
    )

    plan = run(_plan_circuit_request_with_transport(PROMPT, config=config(), transport=transport))

    assert plan.parameters["resistance_ohms"] == 1600
    assert len(calls) == 2
    repair_prompt = json.loads(calls[1].content)["messages"][1]["content"]
    assert "planner.plan.invalid" in repair_prompt
    assert huge_literal not in repair_prompt


@pytest.mark.parametrize(
    "parameters_json",
    [
        '{"resistance_ohms":9999999999999999999999999999999999999999,"capacitance_farads":1e-7}',
        '{"resistance_ohms":1600,"capacitance_farads":9999999999999999999999999999999999999999}',
        (
            '{"resistance_top_ohms":9999999999999999999999999999999999999999,'
            '"resistance_bottom_ohms":10000,"input_voltage_volts":5.0}'
        ),
        (
            '{"resistance_top_ohms":10000,"resistance_bottom_ohms":10000,'
            '"input_voltage_volts":9999999999999999999999999999999999999999}'
        ),
    ],
)
def test_huge_topology_parameter_values_can_repair(parameters_json):
    topology = "resistive_divider" if "resistance_top_ohms" in parameters_json else "rc_low_pass"
    analysis = "dc" if topology == "resistive_divider" else "ac"
    frequencies = "[]" if topology == "resistive_divider" else "[10.0,1000.0,100000.0]"
    bad = raw_json_candidate(parameters_json=parameters_json, requested_frequencies_json=frequencies)
    bad = bad.replace('"topology":"rc_low_pass"', f'"topology":"{topology}"')
    bad = bad.replace('"analysis":"ac"', f'"analysis":"{analysis}"')
    transport, calls = transport_from_responses(
        response_for(envelope(bad)),
        response_for(envelope(json_candidate())),
    )

    plan = run(_plan_circuit_request_with_transport(PROMPT, config=config(), transport=transport))

    assert plan.topology == "rc_low_pass"
    assert len(calls) == 2


def test_huge_requested_frequency_value_can_repair():
    bad = raw_json_candidate(requested_frequencies_json="[1,9999999999999999999999999999999999999999]")
    transport, calls = transport_from_responses(
        response_for(envelope(bad)),
        response_for(envelope(json_candidate())),
    )

    plan = run(_plan_circuit_request_with_transport(PROMPT, config=config(), transport=transport))

    assert plan.topology == "rc_low_pass"
    assert len(calls) == 2


def test_second_huge_integer_candidate_exhausts_repair_without_raw_exception_details():
    huge_literal = "9" * (openrouter_module._MAX_JSON_INTEGER_DIGITS - 1)
    bad = raw_json_candidate(
        requested_frequencies_json=f"[1,{huge_literal}]",
    )
    transport, calls = transport_from_responses(
        response_for(envelope(bad)),
        response_for(envelope(bad)),
    )

    error = run(
        assert_planner_error(
            _plan_circuit_request_with_transport(PROMPT, config=config(), transport=transport),
            "planner.repair.exhausted",
        )
    )

    rendered = str(error) + repr(error) + json.dumps(error.to_dict())
    assert huge_literal not in rendered
    assert len(calls) == 2
