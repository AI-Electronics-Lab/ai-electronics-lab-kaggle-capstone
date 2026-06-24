from __future__ import annotations

import inspect

from ai_electronics_lab.planning import (
    OPENROUTER_PLANNER_VERSION,
    CircuitPlannerError,
    OpenRouterPlannerConfig,
    load_openrouter_planner_config,
    plan_circuit_request,
)
from ai_electronics_lab.planning.planner import plan_circuit_request as planner_entrypoint


def test_public_package_exports_expected_planner_api():
    assert OPENROUTER_PLANNER_VERSION == "1.0"
    assert OpenRouterPlannerConfig.__name__ == "OpenRouterPlannerConfig"
    assert CircuitPlannerError.__name__ == "CircuitPlannerError"
    assert callable(load_openrouter_planner_config)
    assert planner_entrypoint is plan_circuit_request
    assert inspect.iscoroutinefunction(plan_circuit_request)


def test_public_signature_keeps_config_keyword_boundary():
    signature = inspect.signature(plan_circuit_request)
    assert list(signature.parameters) == ["prompt", "config"]
    assert signature.parameters["prompt"].annotation == "str"
    assert signature.parameters["config"].kind is inspect.Parameter.KEYWORD_ONLY
    assert signature.parameters["config"].annotation == "OpenRouterPlannerConfig | None"
    assert signature.return_annotation == "CircuitPlan"
