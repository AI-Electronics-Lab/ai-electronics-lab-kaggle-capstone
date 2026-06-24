from __future__ import annotations

import json

import pytest

from ai_electronics_lab.contracts import CircuitPlan
from ai_electronics_lab.orchestration import (
    BOUNDED_AGENT_ORCHESTRATION_VERSION,
    BoundedAgentOrchestrationError,
    BoundedAgentOrchestrationResult,
    BoundedAgentTraceEvent,
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
from ai_electronics_lab.verification import (
    SIMULATION_VERIFIER_VERSION,
    SimulationVerificationError,
    SimulationVerificationResults,
    VerificationComparison,
    VerificationComplexValue,
    VerificationRunResult,
    VerificationTolerancePolicy,
    verify_simulation_results,
)


def divider_plan() -> CircuitPlan:
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


def divider_parsed_results() -> SimulationParsedResults:
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


def failing_verification_results() -> SimulationVerificationResults:
    comparison = VerificationComparison(
        metric='divider_ratio',
        expected=VerificationComplexValue(real=1.0, imag=0.0),
        measured=VerificationComplexValue(real=2.0, imag=0.0),
        absolute_error=1.0,
        relative_error=1.0,
        pass_limit=1.001e-6,
        warning_limit=1.001e-5,
        status='FAIL',
        reason_code='verification.outside_tolerance',
    )
    run = VerificationRunResult(
        run_id='dc-op',
        topology='resistive_divider',
        analysis_kind='dc',
        frequency_hz=None,
        cutoff_frequency_hz=None,
        status='FAIL',
        reason_codes=('verification.outside_tolerance',),
        comparisons=(comparison,),
    )
    return SimulationVerificationResults(
        version=SIMULATION_VERIFIER_VERSION,
        status='FAIL',
        tolerance_policy=VerificationTolerancePolicy(),
        runs=(run,),
    )


def test_successful_run_returns_frozen_result_and_safe_result() -> None:
    plan = divider_plan()
    parsed = divider_parsed_results()

    def planner(prompt: str, *, config=None):
        assert prompt == 'Design a resistive divider'
        assert config is None
        return plan

    def runner(deck):
        assert deck.version == '1.0'
        return object()

    def parser(_evidence):
        return parsed

    def verifier(received_plan, received_parsed):
        return verify_simulation_results(received_plan, received_parsed)

    result = run_bounded_agent_orchestration(
        '  Design a resistive divider  ',
        planner=planner,
        runner=runner,
        parser=parser,
        verifier=verifier,
    )

    payload = result.to_dict()
    assert BOUNDED_AGENT_ORCHESTRATION_VERSION == '1.0'
    assert result.status == 'PASS'
    assert [event.to_dict() for event in result.stage_trace] == [
        {'stage': 'request.received', 'status': 'started'},
        {'stage': 'request.validated', 'status': 'completed'},
        {'stage': 'planner.requested', 'status': 'started'},
        {'stage': 'planner.completed', 'status': 'completed'},
        {'stage': 'plan.validated', 'status': 'completed'},
        {'stage': 'assembly.completed', 'status': 'completed'},
        {'stage': 'deck.completed', 'status': 'completed'},
        {'stage': 'simulation.started', 'status': 'started'},
        {'stage': 'simulation.completed', 'status': 'completed'},
        {'stage': 'parse.completed', 'status': 'completed'},
        {'stage': 'verification.completed', 'status': 'completed'},
        {'stage': 'request.completed', 'status': 'completed'},
    ]
    assert set(payload) == {
        'version',
        'status',
        'stage_trace',
        'plan',
        'assembly',
        'deck',
        'parsed_results',
        'verification',
    }
    assert 'evidence' not in payload
    assert 'explanation' not in payload
    serialized = json.loads(result.to_json())
    assert serialized['status'] == 'PASS'
    assert serialized['version'] == payload['version']
    assert serialized['stage_trace'] == payload['stage_trace']
    assert result.stage_trace[0].stage == 'request.received'
    assert result.stage_trace[-1].stage == 'request.completed'


def test_result_freezes_mutable_stage_trace_and_event_paths() -> None:
    base = run_bounded_agent_orchestration(
        'Design a resistive divider',
        planner=lambda prompt, *, config=None: divider_plan(),
        runner=lambda deck: object(),
        parser=lambda evidence: divider_parsed_results(),
        verifier=verify_simulation_results,
    )
    trace = [BoundedAgentTraceEvent('request.received', 'started', path=['prompt'])]
    result = BoundedAgentOrchestrationResult(
        version=base.version,
        status=base.status,
        stage_trace=trace,
        plan=base.plan,
        assembly=base.assembly,
        deck=base.deck,
        parsed_results=base.parsed_results,
        verification=base.verification,
    )

    trace.append(BoundedAgentTraceEvent('request.validated', 'completed'))
    assert isinstance(result.stage_trace, tuple)
    assert len(result.stage_trace) == 1
    assert result.stage_trace[0].path == ('prompt',)
    with pytest.raises(ValueError):
        BoundedAgentTraceEvent('not-a-stage', 'started')


@pytest.mark.parametrize(
    'prompt',
    [
        '',
        '   ',
        'x' * 4001,
        'helloworld',
        True,
    ],
)
def test_invalid_prompts_fail_before_pipeline(prompt: object) -> None:
    called = False

    def planner(_prompt: str, *, config=None):
        nonlocal called
        called = True
        return divider_plan()

    with pytest.raises(BoundedAgentOrchestrationError) as caught:
        run_bounded_agent_orchestration(prompt, planner=planner)

    assert caught.value.code == 'orchestration.request.prompt_invalid'
    assert not called


def test_hostile_planner_error_is_sanitized() -> None:
    hostile = '"; rm -rf / # /tmp/secret'

    def planner(_prompt: str, *, config=None):
        raise RuntimeError(hostile)

    with pytest.raises(BoundedAgentOrchestrationError) as caught:
        run_bounded_agent_orchestration('Design a resistive divider', planner=planner)

    rendered = ''.join(
        [
            str(caught.value),
            repr(caught.value),
            json.dumps(caught.value.to_dict(), sort_keys=True),
        ]
    )
    assert caught.value.code == 'orchestration.internal_error'
    assert hostile not in rendered


def test_invalid_plan_maps_to_planner_invalid() -> None:
    bad_plan = CircuitPlan(
        schema_version='1.0',
        topology='bjt',
        analysis='ac',
        parameters={},
        requested_frequencies_hz=(),
        assumptions=(),
    )

    with pytest.raises(BoundedAgentOrchestrationError) as caught:
        run_bounded_agent_orchestration(
            'Design an invalid plan',
            planner=lambda prompt, *, config=None: bad_plan,
        )

    assert caught.value.code == 'orchestration.planner.invalid'
    assert caught.value.path == ('topology',)


@pytest.mark.parametrize(
    ('exc_factory', 'expected_code'),
    [
        (
            lambda: SimulationRunnerError('runner.subprocess.start_failed', ('runs', 0), 'runner failed'),
            'orchestration.execution_failed',
        ),
        (
            lambda: SimulationRawParseError('raw.payload.invalid', ('runs', 0, 'raw_output'), 'parser failed'),
            'orchestration.evidence_invalid',
        ),
        (
            lambda: SimulationVerificationError('verification.results.mismatch', ('runs', 0), 'verification failed'),
            'orchestration.verification_invalid',
        ),
    ],
)
def test_dependency_failures_map_to_stable_codes(exc_factory, expected_code: str) -> None:
    plan = divider_plan()

    def planner(_prompt: str, *, config=None):
        return plan

    def runner(_deck):
        return object()

    def parser(_evidence):
        return divider_parsed_results()

    def verifier(_plan, _parsed):
        raise exc_factory()

    if expected_code == 'orchestration.execution_failed':
        def runner(_deck):  # type: ignore[misc]
            return (_ for _ in ()).throw(exc_factory())

        def parser(_evidence):  # type: ignore[misc]
            return divider_parsed_results()

        verifier = verify_simulation_results
    elif expected_code == 'orchestration.evidence_invalid':
        def runner(_deck):  # type: ignore[misc]
            return object()

        def parser(_evidence):  # type: ignore[misc]
            return (_ for _ in ()).throw(exc_factory())

        verifier = verify_simulation_results
    else:
        def runner(_deck):  # type: ignore[misc]
            return object()

        def parser(_evidence):  # type: ignore[misc]
            return divider_parsed_results()

        def verifier(_plan, _parsed):  # type: ignore[misc]
            return (_ for _ in ()).throw(exc_factory())

    with pytest.raises(BoundedAgentOrchestrationError) as caught:
        run_bounded_agent_orchestration('Design a resistive divider', planner=planner, runner=runner, parser=parser, verifier=verifier)

    assert caught.value.code == expected_code


def test_verification_failure_remains_bounded_without_explanation() -> None:
    plan = divider_plan()
    parsed = divider_parsed_results()

    def planner(_prompt: str, *, config=None):
        return plan

    result = run_bounded_agent_orchestration(
        'Design a resistive divider',
        planner=planner,
        runner=lambda _deck: object(),
        parser=lambda _evidence: parsed,
        verifier=lambda _plan, _parsed: failing_verification_results(),
    )

    payload = result.to_dict()
    assert result.status == 'FAIL'
    assert payload['verification']['status'] == 'FAIL'
    assert 'explanation' not in payload
    serialized = json.loads(result.to_json())
    assert serialized['status'] == 'FAIL'
    assert serialized['version'] == payload['version']
    assert serialized['stage_trace'] == payload['stage_trace']
