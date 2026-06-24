from __future__ import annotations

import json

import pytest

from ai_electronics_lab.planning import CircuitPlannerError
from ai_electronics_lab.planning.openrouter import _candidate_to_plan
from ai_electronics_lab.planning.structured_openrouter import _extract_flat_plan_candidate


def flat_low_pass(**overrides):
    values = {
        "topology": "rc_low_pass",
        "resistance_ohms": 1000.0,
        "capacitance_farads": 0.000001,
        "input_voltage_volts": 0.0,
        "resistance_top_ohms": 0.0,
        "resistance_bottom_ohms": 0.0,
        "requested_frequencies_hz": [10.0, 100.0, 1000.0],
    }
    values.update(overrides)
    return values


def decode(values):
    content = json.dumps(values, separators=(",", ":"))
    candidate = _extract_flat_plan_candidate(content)
    return _candidate_to_plan(candidate, repair=False)


def test_flat_low_pass_values_become_canonical_plan():
    plan = decode(flat_low_pass())

    assert plan.schema_version == "1.0"
    assert plan.topology == "rc_low_pass"
    assert plan.analysis == "ac"
    assert dict(plan.parameters) == {
        "resistance_ohms": 1000.0,
        "capacitance_farads": 0.000001,
    }
    assert plan.requested_frequencies_hz == (10.0, 100.0, 1000.0)
    assert plan.assumptions == ()


def test_flat_divider_values_become_canonical_plan():
    plan = decode(
        {
            "topology": "resistive_divider",
            "resistance_ohms": 0.0,
            "capacitance_farads": 0.0,
            "input_voltage_volts": 5.0,
            "resistance_top_ohms": 1000.0,
            "resistance_bottom_ohms": 2000.0,
            "requested_frequencies_hz": [],
        }
    )

    assert plan.analysis == "dc"
    assert dict(plan.parameters) == {
        "input_voltage_volts": 5.0,
        "resistance_top_ohms": 1000.0,
        "resistance_bottom_ohms": 2000.0,
    }
    assert plan.requested_frequencies_hz == ()


def test_flat_arguments_reject_additional_field():
    with pytest.raises(CircuitPlannerError) as caught:
        decode(flat_low_pass(extra=True))

    assert caught.value.code == "planner.output.invalid_json"
    assert caught.value.path == ("candidate", "unknown_field")


def test_flat_arguments_reject_missing_field():
    values = flat_low_pass()
    del values["capacitance_farads"]

    with pytest.raises(CircuitPlannerError) as caught:
        decode(values)

    assert caught.value.code == "planner.output.invalid_json"
    assert caught.value.path == ("candidate", "capacitance_farads")


def test_nonzero_irrelevant_rc_field_is_rejected():
    with pytest.raises(CircuitPlannerError) as caught:
        decode(flat_low_pass(input_voltage_volts=5.0))

    assert caught.value.code == "planner.plan.invalid"
    assert caught.value.path == ("input_voltage_volts",)


def test_invented_nested_plan_shape_is_rejected():
    invented = {
        "plan": {
            "circuit_type": "rc_low_pass",
            "components": {"resistor": "1 kOhm", "capacitor": "1 uF"},
            "analysis_frequencies_hz": [10, 100, 1000],
        }
    }

    with pytest.raises(CircuitPlannerError) as caught:
        decode(invented)

    assert caught.value.code == "planner.output.invalid_json"
    assert caught.value.path == ("candidate", "unknown_field")
