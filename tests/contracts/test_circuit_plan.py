from __future__ import annotations

import json
from dataclasses import FrozenInstanceError

import pytest

from ai_electronics_lab.contracts import (
    CircuitPlan,
    CircuitPlanValidationError,
    require_valid_circuit_plan,
    validate_circuit_plan,
)


def rc_plan(**overrides):
    values = {
        "schema_version": "1.0",
        "topology": "rc_low_pass",
        "analysis": "ac",
        "parameters": {"resistance_ohms": 1_600, "capacitance_farads": 100e-9},
        "requested_frequencies_hz": (10.0, 1_000.0, 100_000.0),
        "assumptions": ("Ideal passive components.",),
    }
    values.update(overrides)
    return CircuitPlan(**values)


@pytest.mark.parametrize("topology", ["rc_low_pass", "rc_high_pass"])
def test_valid_rc_plans(topology):
    plan = rc_plan(topology=topology)
    assert validate_circuit_plan(plan) == ()
    assert require_valid_circuit_plan(plan) is plan


def test_valid_resistive_divider_plan():
    plan = CircuitPlan(
        schema_version="1.0",
        topology="resistive_divider",
        analysis="dc",
        parameters={
            "resistance_top_ohms": 10_000,
            "resistance_bottom_ohms": 10_000,
            "input_voltage_volts": -5.0,
        },
    )
    assert validate_circuit_plan(plan) == ()


def test_json_serialization_is_deterministic():
    expected = (
        '{"schema_version":"1.0","topology":"rc_low_pass","analysis":"ac",'
        '"parameters":{"capacitance_farads":1e-07,"resistance_ohms":1600},'
        '"requested_frequencies_hz":[10.0,1000.0,100000.0],'
        '"assumptions":["Ideal passive components."]}'
    )
    assert rc_plan().to_json() == expected
    assert json.loads(rc_plan().to_json()) == rc_plan().to_dict()


def test_plan_is_immutable_and_defensively_copies_inputs():
    parameters = {"resistance_ohms": 1_600, "capacitance_farads": 100e-9}
    frequencies = [10.0, 1_000.0]
    assumptions = ["Initial assumption."]
    plan = rc_plan(parameters=parameters, requested_frequencies_hz=frequencies, assumptions=assumptions)
    parameters["resistance_ohms"] = 9_999
    frequencies.append(2_000.0)
    assumptions[0] = "Changed."

    assert plan.parameters["resistance_ohms"] == 1_600
    assert plan.requested_frequencies_hz == (10.0, 1_000.0)
    assert plan.assumptions == ("Initial assumption.",)
    with pytest.raises(TypeError):
        plan.parameters["resistance_ohms"] = 1
    with pytest.raises(FrozenInstanceError):
        plan.analysis = "dc"


def test_unsupported_topology_and_mismatched_analysis_have_stable_codes():
    assert [error.code for error in validate_circuit_plan(rc_plan(topology="bjt"))] == [
        "topology.unsupported"
    ]
    assert [error.code for error in validate_circuit_plan(rc_plan(analysis="dc"))] == [
        "analysis.topology_mismatch"
    ]


def test_mutable_topology_and_analysis_values_return_structured_errors():
    plan = rc_plan(topology={"mutable": True}, analysis=["ac"])
    assert [error.code for error in validate_circuit_plan(plan)] == [
        "topology.unsupported",
        "analysis.unsupported",
    ]


def test_missing_and_unknown_parameters_are_rejected():
    errors = validate_circuit_plan(rc_plan(parameters={"resistance_ohms": 1_000, "gain": 2}))
    assert [error.code for error in errors] == ["parameter.missing", "parameter.unknown"]


@pytest.mark.parametrize(
    ("key", "value", "code"),
    [
        ("resistance_ohms", True, "number.boolean"),
        ("resistance_ohms", float("nan"), "number.non_finite"),
        ("resistance_ohms", float("inf"), "number.non_finite"),
        ("resistance_ohms", 0, "number.out_of_range"),
        ("resistance_ohms", 1e9 + 1, "number.out_of_range"),
        ("capacitance_farads", 1e-16, "number.out_of_range"),
    ],
)
def test_invalid_parameter_numbers(key, value, code):
    parameters = {"resistance_ohms": 1_000, "capacitance_farads": 1e-6}
    parameters[key] = value
    assert [error.code for error in validate_circuit_plan(rc_plan(parameters=parameters))] == [code]


@pytest.mark.parametrize("frequencies", [(100.0, 10.0), (10.0, 10.0)])
def test_frequency_ordering_and_duplicates_are_rejected(frequencies):
    errors = validate_circuit_plan(rc_plan(requested_frequencies_hz=frequencies))
    assert [error.code for error in errors] == ["frequencies.not_strictly_increasing"]


def test_frequencies_are_rejected_for_dc_divider():
    plan = CircuitPlan(
        "1.0",
        "resistive_divider",
        "dc",
        {"resistance_top_ohms": 10, "resistance_bottom_ohms": 10, "input_voltage_volts": 5},
        (1.0,),
    )
    assert [error.code for error in validate_circuit_plan(plan)] == [
        "frequencies.not_allowed_for_dc"
    ]


@pytest.mark.parametrize(
    ("assumptions", "code"),
    [
        (("",), "assumption.malformed"),
        ((" leading",), "assumption.malformed"),
        (("line\nbreak",), "assumption.malformed"),
        (("x" * 241,), "assumption.too_long"),
        ((["mutable nested value"],), "value.mutable"),
    ],
)
def test_malformed_assumptions_are_rejected(assumptions, code):
    assert [error.code for error in validate_circuit_plan(rc_plan(assumptions=assumptions))] == [code]


def test_unsupported_schema_version_has_structured_error():
    error = validate_circuit_plan(rc_plan(schema_version="2.0"))[0]
    assert error.to_dict() == {
        "code": "schema_version.unsupported",
        "path": ["schema_version"],
        "message": "schema_version must be '1.0'",
    }


def test_nested_mutable_parameter_is_frozen_and_rejected():
    mutable_value = [1_000]
    plan = rc_plan(parameters={"resistance_ohms": mutable_value, "capacitance_farads": 1e-6})
    mutable_value.append(2_000)
    assert plan.parameters["resistance_ohms"] == (1_000,)
    assert [error.code for error in validate_circuit_plan(plan)] == ["value.mutable"]


def test_raising_helper_exposes_structured_errors():
    plan = rc_plan(analysis="dc")
    with pytest.raises(CircuitPlanValidationError) as caught:
        require_valid_circuit_plan(plan)
    assert caught.value.errors == validate_circuit_plan(plan)
    assert caught.value.errors[0].code == "analysis.topology_mismatch"
