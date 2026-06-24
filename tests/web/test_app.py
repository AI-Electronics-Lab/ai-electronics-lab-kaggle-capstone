from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from ai_electronics_lab.contracts import CircuitPlan
from ai_electronics_lab.orchestration import (
    BoundedAgentOrchestrationResult,
    run_bounded_agent_orchestration,
)
from ai_electronics_lab.simulation import (
    SIMULATION_RAW_PARSER_VERSION,
    SimulationComplexValue,
    SimulationParsedResults,
    SimulationRawParseError,
    SimulationRunMeasurements,
    SimulationRunnerError,
)
from ai_electronics_lab.verification import SimulationVerificationError, verify_simulation_results
from ai_electronics_lab.web import (
    MAX_REQUEST_BODY_BYTES,
    WebUIError,
    create_app,
    simulate_request,
)

_NGSPICE_AVAILABLE = any(
    path.is_file()
    for path in (
        Path("/usr/bin/ngspice"),
        Path("/usr/local/bin/ngspice"),
    )
)


def _valid_rc(
    topology: str = "rc_low_pass",
) -> dict[str, object]:
    return {
        "topology": topology,
        "resistance_ohms": 1000,
        "capacitance_farads": 1e-6,
        "frequencies_hz": [10, 1000],
    }


def _valid_divider() -> dict[str, object]:
    return {
        "topology": "resistive_divider",
        "input_voltage_volts": 5,
        "resistance_top_ohms": 1000,
        "resistance_bottom_ohms": 2000,
    }


def _fake_parsed_results(
    deck: Any,
    topology: str,
    payload: dict[str, object],
) -> SimulationParsedResults:
    runs = []

    for run in deck.runs:
        if run.analysis_kind == "dc":
            input_voltage = float(payload["input_voltage_volts"])
            resistance_top = float(payload["resistance_top_ohms"])
            resistance_bottom = float(payload["resistance_bottom_ohms"])
            ratio = resistance_bottom / (resistance_top + resistance_bottom)
            vin = SimulationComplexValue(real=input_voltage, imag=0.0)
            vout = SimulationComplexValue(real=input_voltage * ratio, imag=0.0)
        else:
            frequency = float(run.frequency_hz)
            resistance = float(payload["resistance_ohms"])
            capacitance = float(payload["capacitance_farads"])
            x = 2.0 * math.pi * frequency * resistance * capacitance
            denominator = 1.0 + x * x
            if topology == "rc_low_pass":
                real = 1.0 / denominator
                imag = -x / denominator
            else:
                real = x * x / denominator
                imag = x / denominator
            vin = SimulationComplexValue(real=1.0, imag=0.0)
            vout = SimulationComplexValue(real=real, imag=imag)

        runs.append(
            SimulationRunMeasurements(
                run_id=run.run_id,
                topology=topology,
                analysis_kind=run.analysis_kind,
                frequency_hz=run.frequency_hz,
                vin_voltage=vin,
                vout_voltage=vout,
            )
        )

    return SimulationParsedResults(
        version=SIMULATION_RAW_PARSER_VERSION,
        runs=tuple(runs),
    )


def _simulate_without_ngspice(
    payload: dict[str, object],
) -> dict[str, Any]:
    captured: dict[str, Any] = {}

    def runner(deck: Any) -> object:
        captured["deck"] = deck
        return object()

    def parser(
        _evidence: object,
    ) -> SimulationParsedResults:
        return _fake_parsed_results(
            captured["deck"],
            str(payload["topology"]),
            payload,
        )

    return simulate_request(
        payload,
        runner=runner,
        parser=parser,
    )


def _orchestration_plan() -> CircuitPlan:
    return CircuitPlan(
        schema_version='1.0',
        topology='resistive_divider',
        analysis='dc',
        parameters={
            'input_voltage_volts': 5.0,
            'resistance_bottom_ohms': 10_000.0,
            'resistance_top_ohms': 10_000.0,
        },
        requested_frequencies_hz=(),
        assumptions=('Equal resistors produce a 0.5 output ratio.',),
    )


def _orchestration_parsed_results() -> SimulationParsedResults:
    run = SimulationRunMeasurements(
        run_id='dc-op',
        topology='resistive_divider',
        analysis_kind='dc',
        frequency_hz=None,
        vin_voltage=SimulationComplexValue(real=5.0, imag=0.0),
        vout_voltage=SimulationComplexValue(real=2.5, imag=0.0),
    )
    return SimulationParsedResults(
        version=SIMULATION_RAW_PARSER_VERSION,
        runs=(run,),
    )


def _orchestration_result(prompt: str) -> BoundedAgentOrchestrationResult:
    plan = _orchestration_plan()
    parsed = _orchestration_parsed_results()
    return run_bounded_agent_orchestration(
        prompt,
        planner=lambda received_prompt, *, config=None: plan,
        runner=lambda deck: object(),
        parser=lambda evidence: parsed,
        verifier=verify_simulation_results,
    )


def _all_mapping_keys(value: object) -> set[str]:
    keys: set[str] = set()

    if isinstance(value, dict):
        for key, item in value.items():
            keys.add(str(key))
            keys.update(_all_mapping_keys(item))
    elif isinstance(value, list):
        for item in value:
            keys.update(_all_mapping_keys(item))

    return keys


def test_home_page_is_self_contained_and_hardened() -> None:
    client = TestClient(create_app())
    response = client.get("/")

    assert response.status_code == 200
    assert "AI Electronics Lab" in response.text
    assert "Run Orchestration" in response.text
    assert "Run Simulation" in response.text
    assert 'id="orchestration-form"' in response.text
    assert 'id="prompt-input"' in response.text
    assert 'data-prompt-example="divider"' in response.text
    assert 'id="stage-trace-panel"' in response.text
    assert 'id="stage-trace-list"' in response.text
    assert '/api/orchestrate' in response.text
    assert "innerHTML" not in response.text
    assert "<script src=" not in response.text
    assert "<link rel=" not in response.text
    assert "https://" not in response.text
    assert "Deterministic analytical verification" in response.text
    assert 'id="verification-panel"' in response.text
    assert 'id="verification-summary"' in response.text
    assert 'id="verification-runs"' in response.text
    assert "renderStageTrace" in response.text
    assert "renderVerification" in response.text
    assert ".textContent" in response.text
    assert '].join("\\n");' in response.text
    assert '].join("\n");' not in response.text
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["cache-control"] == "no-store"
    assert (
        "default-src 'none'"
        in response.headers["content-security-policy"]
    )


def test_generated_documentation_routes_are_disabled() -> None:
    client = TestClient(create_app())

    assert client.get("/docs").status_code == 404
    assert client.get("/redoc").status_code == 404
    assert client.get("/openapi.json").status_code == 404


@pytest.mark.parametrize(
    "topology",
    ["rc_low_pass", "rc_high_pass"],
)
def test_valid_rc_request_reaches_safe_parsed_results(
    topology: str,
) -> None:
    result = _simulate_without_ngspice(
        _valid_rc(topology),
    )

    assert result["status"] == "ok"
    assert (
        result["evidence_kind"]
        == "deterministic_simulation_evidence"
    )
    assert result["plan"]["topology"] == topology
    assert len(result["deck"]["runs"]) == 2
    assert result["deck"]["runs"][0]["run_id"] == "ac-01"
    assert (
        ".ac lin 1 10 10"
        in result["deck"]["runs"][0]["netlist_text"]
    )
    assert set(result["results"]["runs"][0]["vout_voltage"]) == {"imag", "real"}
    assert result["verification_kind"] == "deterministic_analytical_verification"
    assert result["verification"]["status"] == "PASS"
    assert result["verification"]["runs"][0]["status"] == "PASS"
    assert result["schematic_svg"].startswith("<svg")


def test_valid_divider_request_reaches_safe_parsed_results() -> None:
    result = _simulate_without_ngspice(
        _valid_divider(),
    )

    assert result["status"] == "ok"
    assert result["plan"]["analysis"] == "dc"
    assert result["deck"]["runs"][0]["run_id"] == "dc-op"
    assert ".op" in result["deck"]["runs"][0]["netlist_text"]
    assert result["results"]["runs"][0]["frequency_hz"] is None
    assert result["verification"]["status"] == "PASS"
    assert result["verification"]["runs"][0]["comparisons"][1]["metric"] == "divider_ratio"
    assert result["schematic_svg"].startswith("<svg")


def test_api_valid_request_uses_same_origin_json_contract() -> None:
    client = TestClient(
        create_app(
            simulation_service=_simulate_without_ngspice,
        )
    )
    response = client.post(
        "/api/simulate",
        json=_valid_rc(),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.headers["content-type"].startswith(
        "application/json"
    )


def test_malformed_json_is_rejected_before_service_execution() -> None:
    called = False

    def service(
        _payload: object,
    ) -> dict[str, Any]:
        nonlocal called
        called = True
        return {}

    client = TestClient(
        create_app(simulation_service=service),
    )
    response = client.post(
        "/api/simulate",
        content=b"{",
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 400
    assert (
        response.json()["error"]["code"]
        == "request.malformed_json"
    )
    assert called is False


def test_duplicate_json_keys_are_rejected() -> None:
    client = TestClient(
        create_app(
            simulation_service=_simulate_without_ngspice,
        )
    )
    response = client.post(
        "/api/simulate",
        content=(
            b'{"topology":"rc_low_pass",'
            b'"topology":"rc_high_pass"}'
        ),
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 400
    assert (
        response.json()["error"]["code"]
        == "request.duplicate_key"
    )


def test_non_finite_json_constant_is_rejected() -> None:
    client = TestClient(
        create_app(
            simulation_service=_simulate_without_ngspice,
        )
    )
    response = client.post(
        "/api/simulate",
        content=(
            b'{"topology":"rc_low_pass",'
            b'"resistance_ohms":NaN,'
            b'"capacitance_farads":0.000001,'
            b'"frequencies_hz":[10]}'
        ),
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 400
    assert (
        response.json()["error"]["code"]
        == "request.non_finite"
    )


def test_oversized_body_is_rejected() -> None:
    client = TestClient(
        create_app(
            simulation_service=_simulate_without_ngspice,
        )
    )
    response = client.post(
        "/api/simulate",
        content=(
            b"{"
            + (b" " * MAX_REQUEST_BODY_BYTES)
            + b"}"
        ),
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 413
    assert (
        response.json()["error"]["code"]
        == "request.too_large"
    )


def test_wrong_content_type_is_rejected() -> None:
    client = TestClient(
        create_app(
            simulation_service=_simulate_without_ngspice,
        )
    )
    response = client.post(
        "/api/simulate",
        content=b"{}",
        headers={"Content-Type": "text/plain"},
    )

    assert response.status_code == 400
    assert (
        response.json()["error"]["code"]
        == "request.content_type"
    )


def test_unsupported_topology_is_not_reflected() -> None:
    attack = "<script>alert(1)</script>"
    client = TestClient(
        create_app(
            simulation_service=_simulate_without_ngspice,
        )
    )
    response = client.post(
        "/api/simulate",
        json={"topology": attack},
    )

    assert response.status_code == 422
    assert (
        response.json()["error"]["code"]
        == "request.topology_unsupported"
    )
    assert attack not in response.text


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("resistance_ohms", True),
        ("resistance_ohms", 0),
        ("resistance_ohms", 10**10000),
        ("capacitance_farads", False),
        ("capacitance_farads", 2),
    ],
    ids=[
        "resistance-boolean",
        "resistance-zero",
        "resistance-huge-integer",
        "capacitance-boolean",
        "capacitance-out-of-range",
    ],
)
def test_invalid_rc_numbers_are_rejected_without_execution(
    field: str,
    value: object,
) -> None:
    payload = _valid_rc()
    payload[field] = value

    with pytest.raises(WebUIError) as captured:
        _simulate_without_ngspice(payload)

    assert captured.value.status_code == 422


@pytest.mark.parametrize(
    "frequencies",
    [
        [],
        [100, 10],
        [10, 10],
        [True],
        [10**10000],
        [1, 2, 3, 4, 5, 6, 7, 8, 9],
    ],
    ids=[
        "empty",
        "descending",
        "duplicate",
        "boolean",
        "huge-integer",
        "too-many",
    ],
)
def test_invalid_frequency_sets_are_rejected(
    frequencies: list[object],
) -> None:
    payload = _valid_rc()
    payload["frequencies_hz"] = frequencies

    with pytest.raises(WebUIError):
        _simulate_without_ngspice(payload)


def test_unknown_fields_are_rejected() -> None:
    payload = _valid_rc()
    payload["spice_directive"] = ".shell anything"

    with pytest.raises(WebUIError) as captured:
        _simulate_without_ngspice(payload)

    assert captured.value.code == "request.field_unknown"


def test_runner_error_is_mapped_without_internal_text() -> None:
    secret = "SECRET child stderr /tmp/private-path"

    def runner(_deck: Any) -> object:
        raise SimulationRunnerError(
            "runner.process.failed",
            ("runs", 0),
            secret,
        )

    with pytest.raises(WebUIError) as captured:
        simulate_request(
            _valid_rc(),
            runner=runner,
        )

    assert (
        captured.value.code
        == "simulation.execution_failed"
    )
    assert secret not in captured.value.message
    assert captured.value.path == ()


def test_parser_error_is_mapped_without_internal_text() -> None:
    secret = "SECRET raw payload detail"

    def runner(_deck: Any) -> object:
        return object()

    def parser(
        _evidence: object,
    ) -> SimulationParsedResults:
        raise SimulationRawParseError(
            "raw.payload.invalid",
            ("runs", 0, "raw_output"),
            secret,
        )

    with pytest.raises(WebUIError) as captured:
        simulate_request(
            _valid_rc(),
            runner=runner,
            parser=parser,
        )

    assert (
        captured.value.code
        == "simulation.evidence_invalid"
    )
    assert secret not in captured.value.message
    assert captured.value.path == ()


def test_verifier_error_is_mapped_without_internal_text() -> None:
    secret = "SECRET verifier path /tmp/private"

    def verifier(_plan: object, _parsed: object) -> object:
        raise SimulationVerificationError(
            "verification.results.mismatch",
            ("runs", 0),
            secret,
        )

    captured: dict[str, Any] = {}

    def real_runner(deck: Any) -> object:
        captured["deck"] = deck
        return object()

    def real_parser(_evidence: object) -> SimulationParsedResults:
        return _fake_parsed_results(
            captured["deck"],
            "rc_low_pass",
            _valid_rc(),
        )

    with pytest.raises(WebUIError) as error:
        simulate_request(
            _valid_rc(),
            runner=real_runner,
            parser=real_parser,
            verifier=verifier,  # type: ignore[arg-type]
        )

    assert error.value.status_code == 502
    assert error.value.code == "simulation.verification_invalid"
    assert error.value.path == ()
    assert error.value.message == "The deterministic simulation evidence could not be verified."
    assert secret not in error.value.message


def test_success_response_contains_only_safe_verification_values() -> None:
    result = _simulate_without_ngspice(_valid_divider())
    verification = result["verification"]
    assert verification["version"] == "1.0"
    assert verification["status"] == "PASS"
    assert verification["tolerance_policy"] == {
        "absolute_tolerance": 1e-9,
        "denominator_floor": 1e-12,
        "relative_tolerance": 1e-6,
        "warning_multiplier": 10.0,
    }
    assert verification["runs"][0]["reason_codes"] == [
        "verification.within_tolerance"
    ]


def test_unexpected_exception_response_does_not_disclose_exception() -> None:
    secret = "SECRET_TOKEN=/tmp/private/path"

    def service(
        _payload: object,
    ) -> dict[str, Any]:
        raise RuntimeError(secret)

    client = TestClient(
        create_app(simulation_service=service),
        raise_server_exceptions=False,
    )
    response = client.post(
        "/api/simulate",
        json=_valid_rc(),
    )

    assert response.status_code == 500
    assert (
        response.json()["error"]["code"]
        == "simulation.internal_error"
    )
    assert secret not in response.text


def test_success_response_omits_raw_and_process_evidence() -> None:
    result = _simulate_without_ngspice(
        _valid_rc(),
    )
    keys = _all_mapping_keys(result)

    assert "raw_output" not in keys
    assert "raw_output_base64" not in keys
    assert "stdout" not in keys
    assert "stderr" not in keys
    assert "executable" not in keys
    assert "environment" not in keys
    assert "temp_path" not in keys


@pytest.mark.skipif(
    not _NGSPICE_AVAILABLE,
    reason="approved local ngspice executable is unavailable",
)
@pytest.mark.parametrize(
    "payload",
    [
        {
            "topology": "rc_low_pass",
            "resistance_ohms": 1000,
            "capacitance_farads": 1e-6,
            "frequencies_hz": [1000],
        },
        {
            "topology": "rc_high_pass",
            "resistance_ohms": 1000,
            "capacitance_farads": 1e-6,
            "frequencies_hz": [1000],
        },
        {
            "topology": "resistive_divider",
            "input_voltage_volts": 5,
            "resistance_top_ohms": 1000,
            "resistance_bottom_ohms": 2000,
        },
    ],
    ids=["low-pass", "high-pass", "divider"],
)
def test_optional_real_ngspice_pipeline_smoke(payload: dict[str, object]) -> None:
    result = simulate_request(payload)

    assert result["status"] == "ok"
    assert result["verification"]["status"] == "PASS"
    assert all(run["status"] == "PASS" for run in result["verification"]["runs"])


class _BusyOrchestrationLock:
    def locked(self) -> bool:
        return True


def test_orchestrate_route_preserves_manual_simulation_route() -> None:
    captured: dict[str, object] = {}

    def orchestration_service(prompt: str) -> BoundedAgentOrchestrationResult:
        captured['prompt'] = prompt
        return _orchestration_result(prompt)

    client = TestClient(
        create_app(
            simulation_service=_simulate_without_ngspice,
            orchestration_service=orchestration_service,
        )
    )

    orchestration_response = client.post(
        '/api/orchestrate',
        json={'prompt': 'Design a resistive divider'},
    )
    simulation_response = client.post(
        '/api/simulate',
        json=_valid_divider(),
    )

    assert orchestration_response.status_code == 200
    assert orchestration_response.json()['status'] == 'PASS'
    assert orchestration_response.json()['version'] == '1.0'
    assert 'explanation' not in orchestration_response.json()
    assert orchestration_response.json()['stage_trace'][0]['stage'] == 'request.received'
    assert captured['prompt'] == 'Design a resistive divider'
    assert simulation_response.status_code == 200
    assert simulation_response.json()['status'] == 'ok'


def test_orchestrate_rejects_arbitrary_dict_result() -> None:
    client = TestClient(
        create_app(
            simulation_service=_simulate_without_ngspice,
            orchestration_service=lambda prompt: {'prompt': prompt, 'status': 'ok'},
        )
    )

    response = client.post(
        '/api/orchestrate',
        json={'prompt': 'Design a resistive divider'},
    )

    assert response.status_code == 500
    assert response.json()['error']['code'] == 'orchestration.internal_error'


@pytest.mark.parametrize(
    ('body', 'headers', 'status_code', 'code'),
    [
        (b'', {'Content-Type': 'application/json'}, 400, 'orchestration.request.empty'),
        (b'{', {'Content-Type': 'application/json'}, 400, 'orchestration.request.malformed_json'),
        (
            b'{"prompt":"x","prompt":"y"}',
            {'Content-Type': 'application/json'},
            400,
            'orchestration.request.duplicate_key',
        ),
        (
            b'{"prompt":NaN}',
            {'Content-Type': 'application/json'},
            400,
            'orchestration.request.non_finite',
        ),
        (
            b'{' + (b' ' * MAX_REQUEST_BODY_BYTES) + b'}',
            {'Content-Type': 'application/json'},
            413,
            'orchestration.request.too_large',
        ),
        (
            b'{}',
            {'Content-Type': 'text/plain'},
            400,
            'orchestration.request.content_type',
        ),
        (
            b'{"topology":"x"}',
            {'Content-Type': 'application/json'},
            422,
            'orchestration.request.object_required',
        ),
    ],
)
def test_orchestrate_request_hardening(body, headers, status_code, code) -> None:
    client = TestClient(
        create_app(
            simulation_service=_simulate_without_ngspice,
            orchestration_service=lambda prompt: _orchestration_result(prompt),
        )
    )

    response = client.post('/api/orchestrate', content=body, headers=headers)

    assert response.status_code == status_code
    assert response.json()['error']['code'] == code


@pytest.mark.parametrize(
    ('prompt', 'expected_code'),
    [
        ('   ', 'orchestration.request.prompt_invalid'),
        ('a' * 4001, 'orchestration.request.prompt_invalid'),
        ('Design a resistive divider', 'orchestration.request.prompt_invalid'),
    ],
)
def test_orchestrate_prompt_validation_rejects_invalid_prompts(prompt, expected_code) -> None:
    called = False

    def orchestration_service(_prompt: str) -> BoundedAgentOrchestrationResult:
        nonlocal called
        called = True
        return _orchestration_result(_prompt)

    client = TestClient(
        create_app(
            simulation_service=_simulate_without_ngspice,
            orchestration_service=orchestration_service,
        )
    )

    response = client.post(
        '/api/orchestrate',
        json={'prompt': prompt},
    )

    assert response.status_code == 422
    assert response.json()['error']['code'] == expected_code
    assert called is False


def test_orchestrate_prompt_validation_and_busy_lock() -> None:
    client = TestClient(
        create_app(
            simulation_service=_simulate_without_ngspice,
            orchestration_service=lambda prompt: _orchestration_result(prompt),
        )
    )

    client.app.state.orchestration_lock = _BusyOrchestrationLock()
    busy_response = client.post(
        '/api/orchestrate',
        json={'prompt': 'Design a resistive divider'},
    )

    assert busy_response.status_code == 429
    assert busy_response.json()['error']['code'] == 'orchestration.request.busy'
