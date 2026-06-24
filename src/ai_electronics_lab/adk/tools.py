"""Genuine Google ADK tools over the existing bounded orchestration boundary."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from typing import Any

from google.adk.tools.function_tool import FunctionTool

from ai_electronics_lab.orchestration import (
    BoundedAgentOrchestrationError,
    BoundedAgentOrchestrationResult,
    run_bounded_agent_orchestration,
)

ADK_WORKFLOW_ADAPTER_VERSION = '1.0'
VERIFIED_SIMULATION_TOOL_NAME = 'run_verified_circuit_simulation'

OrchestrationService = Callable[[str], BoundedAgentOrchestrationResult]


def build_safe_internal_error_payload() -> dict[str, Any]:
    """Return the canonical orchestration internal-error payload."""

    error = BoundedAgentOrchestrationError('orchestration.internal_error')
    return {
        'version': ADK_WORKFLOW_ADAPTER_VERSION,
        'status': 'error',
        'error': error.to_dict(),
    }


def _build_safe_known_error_payload(
    error: BoundedAgentOrchestrationError,
) -> dict[str, Any]:
    canonical = BoundedAgentOrchestrationError(
        error.code,
        error.path,
        status_code=error.status_code,
    )
    return {
        'version': ADK_WORKFLOW_ADAPTER_VERSION,
        'status': 'error',
        'error': canonical.to_dict(),
    }


def create_verified_simulation_tool(
    *,
    orchestration_service: OrchestrationService = run_bounded_agent_orchestration,
) -> FunctionTool:
    """Create the ADK tool that delegates to the verified orchestration pipeline."""

    async def run_verified_circuit_simulation(prompt: str) -> dict[str, Any]:
        """Run one bounded circuit request through the verified simulation pipeline."""

        try:
            result = await asyncio.to_thread(orchestration_service, prompt)
        except BoundedAgentOrchestrationError as error:
            return _build_safe_known_error_payload(error)
        except Exception:
            return build_safe_internal_error_payload()

        if type(result) is not BoundedAgentOrchestrationResult:
            return build_safe_internal_error_payload()

        try:
            safe_result = json.loads(result.to_json())
        except (TypeError, ValueError):
            return build_safe_internal_error_payload()

        return {
            'version': ADK_WORKFLOW_ADAPTER_VERSION,
            'status': 'ok',
            'result': safe_result,
        }

    return FunctionTool(run_verified_circuit_simulation)
