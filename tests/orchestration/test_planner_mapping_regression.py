import pytest

from ai_electronics_lab.orchestration import (
    BoundedAgentOrchestrationError,
    run_bounded_agent_orchestration,
)
from ai_electronics_lab.planning import CircuitPlannerError


@pytest.mark.parametrize(
    ("planner_code", "expected_code", "expected_status"),
    [
        ("planner.output.invalid_json", "orchestration.planner.invalid", 422),
        ("planner.plan.unsupported_topology", "orchestration.planner.invalid", 422),
        ("planner.provider.envelope_invalid", "orchestration.planner.unavailable", 503),
        ("planner.config.api_key_missing", "orchestration.planner.unavailable", 503),
    ],
)
def test_planner_failures_map_to_stable_orchestration_errors(
    planner_code: str,
    expected_code: str,
    expected_status: int,
) -> None:
    def planner(_prompt: str, *, config=None):
        del config
        raise CircuitPlannerError(planner_code)

    with pytest.raises(BoundedAgentOrchestrationError) as caught:
        run_bounded_agent_orchestration(
            "Design a supported circuit",
            planner=planner,
        )

    assert caught.value.code == expected_code
    assert caught.value.status_code == expected_status
    assert caught.value.message in {
        "The bounded planner returned an invalid CircuitPlan.",
        "The bounded planner could not complete.",
    }


def test_default_planner_configuration_failure_maps_to_unavailable(monkeypatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    with pytest.raises(BoundedAgentOrchestrationError) as caught:
        run_bounded_agent_orchestration("Design a supported circuit")

    assert caught.value.code == "orchestration.planner.unavailable"
    assert caught.value.status_code == 503
    assert caught.value.path == ("OPENROUTER_API_KEY",)
    assert caught.value.message == "The bounded planner could not complete."
