from __future__ import annotations

import asyncio
import inspect
import json
from collections.abc import Callable
from typing import Any

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.tools.function_tool import FunctionTool
from google.adk.workflow import Workflow
from google.genai import types

from ai_electronics_lab.adk import (
    ADK_WORKFLOW_ADAPTER_VERSION,
    VERIFIED_SIMULATION_TOOL_NAME,
    VERIFIED_SIMULATION_WORKFLOW_NAME,
    create_verified_simulation_tool,
    create_verified_simulation_workflow,
    run_verified_simulation_workflow,
)
from ai_electronics_lab.contracts import CircuitPlan
from ai_electronics_lab.orchestration import (
    BoundedAgentOrchestrationError,
    BoundedAgentOrchestrationResult,
    run_bounded_agent_orchestration,
)
from ai_electronics_lab.simulation import (
    SIMULATION_RAW_PARSER_VERSION,
    SimulationComplexValue,
    SimulationParsedResults,
    SimulationRunMeasurements,
)
from ai_electronics_lab.verification import verify_simulation_results


def _divider_plan() -> CircuitPlan:
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


def _divider_parsed_results() -> SimulationParsedResults:
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


def _successful_service(
    calls: list[str],
) -> Callable[[str], BoundedAgentOrchestrationResult]:
    plan = _divider_plan()
    parsed = _divider_parsed_results()

    def service(prompt: str) -> BoundedAgentOrchestrationResult:
        calls.append(prompt)
        return run_bounded_agent_orchestration(
            prompt,
            planner=lambda _prompt, *, config=None: plan,
            runner=lambda _deck: object(),
            parser=lambda _evidence: parsed,
            verifier=verify_simulation_results,
        )

    return service


async def _run_workflow_events(
    workflow: Workflow,
    prompt: str,
) -> list[Any]:
    session_service = InMemorySessionService()
    runner = Runner(
        app_name=VERIFIED_SIMULATION_WORKFLOW_NAME,
        node=workflow,
        session_service=session_service,
    )
    session = await session_service.create_session(
        app_name=VERIFIED_SIMULATION_WORKFLOW_NAME,
        user_id='test-user',
    )
    message = types.Content(
        role='user',
        parts=[types.Part(text=prompt)],
    )

    events = []
    async for event in runner.run_async(
        user_id='test-user',
        session_id=session.id,
        new_message=message,
    ):
        events.append(event)
    return events


def test_tool_is_genuine_and_exposes_only_the_prompt_argument() -> None:
    tool = create_verified_simulation_tool(
        orchestration_service=_successful_service([]),
    )

    assert type(tool) is FunctionTool
    assert tool.name == VERIFIED_SIMULATION_TOOL_NAME
    assert tuple(inspect.signature(tool.func).parameters) == ('prompt',)

    exposed = set(inspect.signature(tool.func).parameters)
    forbidden = {
        'command',
        'environment',
        'executable',
        'filesystem_path',
        'netlist',
        'provider_response',
        'raw_output',
        'stderr',
        'stdout',
        'tolerance',
        'verdict',
    }
    assert exposed.isdisjoint(forbidden)


def test_workflow_registers_and_invokes_the_function_tool() -> None:
    calls: list[str] = []
    prompt = 'Design a resistive divider'
    workflow = create_verified_simulation_workflow(
        orchestration_service=_successful_service(calls),
    )

    assert type(workflow) is Workflow
    assert workflow.name == VERIFIED_SIMULATION_WORKFLOW_NAME

    events = asyncio.run(_run_workflow_events(workflow, prompt))
    tool_events = [
        event
        for event in events
        if event.output is not None
        and f'/{VERIFIED_SIMULATION_TOOL_NAME}@'
        in (getattr(getattr(event, 'node_info', None), 'path', '') or '')
    ]

    assert calls == [prompt]
    assert len(tool_events) == 1

    payload = tool_events[0].output
    assert set(payload) == {'version', 'status', 'result'}
    assert payload['version'] == ADK_WORKFLOW_ADAPTER_VERSION
    assert payload['status'] == 'ok'
    assert payload['result']['status'] == 'PASS'
    assert payload['result']['plan']['topology'] == 'resistive_divider'

    serialized = json.dumps(payload, sort_keys=True)
    for forbidden in (
        'provider_response',
        'raw_output',
        'stderr',
        'stdout',
        'temporary_path',
        'executable_path',
    ):
        assert forbidden not in serialized


def test_public_runner_returns_safe_success_without_api_key(
    monkeypatch,
) -> None:
    monkeypatch.delenv('OPENROUTER_API_KEY', raising=False)
    calls: list[str] = []

    payload = asyncio.run(
        run_verified_simulation_workflow(
            'Design a resistive divider',
            orchestration_service=_successful_service(calls),
        )
    )

    assert calls == ['Design a resistive divider']
    assert payload['version'] == ADK_WORKFLOW_ADAPTER_VERSION
    assert payload['status'] == 'ok'
    assert payload['result']['verification']['status'] == 'PASS'


def test_known_orchestration_failure_is_canonical_and_bounded() -> None:
    hostile = '"; rm -rf / # /tmp/provider-secret'

    def service(_prompt: str) -> BoundedAgentOrchestrationResult:
        raise BoundedAgentOrchestrationError(
            'orchestration.execution_failed',
            ('runs', 0),
            hostile,
        )

    payload = asyncio.run(
        run_verified_simulation_workflow(
            'Design a resistive divider',
            orchestration_service=service,
        )
    )

    assert payload == {
        'version': ADK_WORKFLOW_ADAPTER_VERSION,
        'status': 'error',
        'error': {
            'code': 'orchestration.execution_failed',
            'path': ['runs', 0],
            'message': 'The bounded local simulation could not complete.',
        },
    }
    assert hostile not in json.dumps(payload, sort_keys=True)


def test_invalid_prompt_uses_existing_orchestration_validation() -> None:
    payload = asyncio.run(run_verified_simulation_workflow(''))

    assert payload == {
        'version': ADK_WORKFLOW_ADAPTER_VERSION,
        'status': 'error',
        'error': {
            'code': 'orchestration.request.prompt_invalid',
            'path': ['prompt'],
            'message': 'Prompt violates the bounded prompt contract.',
        },
    }


def test_unexpected_service_failure_does_not_expose_exception_text() -> None:
    hostile = 'raw provider response and /tmp/private-path'

    def service(_prompt: str) -> BoundedAgentOrchestrationResult:
        raise RuntimeError(hostile)

    payload = asyncio.run(
        run_verified_simulation_workflow(
            'Design a resistive divider',
            orchestration_service=service,
        )
    )

    assert payload['status'] == 'error'
    assert payload['error']['code'] == 'orchestration.internal_error'
    assert hostile not in json.dumps(payload, sort_keys=True)
