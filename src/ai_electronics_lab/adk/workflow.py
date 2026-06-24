"""Google ADK graph workflow over the verified circuit-simulation tool."""

from __future__ import annotations

import json
from typing import Any

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.workflow import START, Workflow
from google.genai import types

from ai_electronics_lab.orchestration import run_bounded_agent_orchestration

from .tools import (
    ADK_WORKFLOW_ADAPTER_VERSION,
    OrchestrationService,
    build_safe_internal_error_payload,
    create_verified_simulation_tool,
)

VERIFIED_SIMULATION_WORKFLOW_NAME = 'verified_circuit_simulation_workflow'
_ADK_APP_NAME = 'ai_electronics_lab_verified_simulation'
_ADK_USER_ID = 'local_verified_simulation_user'


def _prepare_verified_simulation_tool_arguments(
    node_input: str,
) -> dict[str, str]:
    """Map ADK text input to the single bounded tool argument."""

    return {'prompt': node_input}


def create_verified_simulation_workflow(
    *,
    orchestration_service: OrchestrationService = run_bounded_agent_orchestration,
) -> Workflow:
    """Create the public ADK graph containing the registered simulation tool."""

    tool = create_verified_simulation_tool(
        orchestration_service=orchestration_service,
    )
    return Workflow(
        name=VERIFIED_SIMULATION_WORKFLOW_NAME,
        description=(
            'Delegate one bounded natural-language circuit request to the existing '
            'verified simulation orchestration pipeline.'
        ),
        edges=[
            (
                START,
                _prepare_verified_simulation_tool_arguments,
                tool,
            ),
        ],
    )


def _is_safe_adapter_payload(payload: object) -> bool:
    if type(payload) is not dict:
        return False
    if payload.get('version') != ADK_WORKFLOW_ADAPTER_VERSION:
        return False

    status = payload.get('status')
    if status == 'ok':
        return set(payload) == {'version', 'status', 'result'} and type(
            payload.get('result')
        ) is dict

    if status != 'error' or set(payload) != {'version', 'status', 'error'}:
        return False

    error = payload.get('error')
    if type(error) is not dict:
        return False
    if set(error) != {'code', 'path', 'message'}:
        return False
    if type(error.get('code')) is not str:
        return False
    if type(error.get('message')) is not str:
        return False

    path = error.get('path')
    return type(path) is list and all(type(item) in {str, int} for item in path)


def _copy_safe_payload(payload: dict[str, Any]) -> dict[str, Any]:
    serialized = json.dumps(
        payload,
        sort_keys=True,
        separators=(',', ':'),
        ensure_ascii=False,
        allow_nan=False,
    )
    copied = json.loads(serialized)
    if not _is_safe_adapter_payload(copied):
        raise ValueError('ADK adapter payload failed its closed schema')
    return copied


async def run_verified_simulation_workflow(
    prompt: str,
    *,
    orchestration_service: OrchestrationService = run_bounded_agent_orchestration,
) -> dict[str, Any]:
    """Execute one fresh in-memory ADK workflow invocation."""

    try:
        workflow = create_verified_simulation_workflow(
            orchestration_service=orchestration_service,
        )
        session_service = InMemorySessionService()
        runner = Runner(
            app_name=_ADK_APP_NAME,
            node=workflow,
            session_service=session_service,
        )
        session = await session_service.create_session(
            app_name=_ADK_APP_NAME,
            user_id=_ADK_USER_ID,
        )
        message = types.Content(
            role='user',
            parts=[types.Part(text=prompt)],
        )

        terminal_payload: dict[str, Any] | None = None
        async for event in runner.run_async(
            user_id=_ADK_USER_ID,
            session_id=session.id,
            new_message=message,
        ):
            candidate = event.output
            if _is_safe_adapter_payload(candidate):
                terminal_payload = candidate

        if terminal_payload is None:
            return build_safe_internal_error_payload()

        return _copy_safe_payload(terminal_payload)
    except Exception:
        return build_safe_internal_error_payload()
