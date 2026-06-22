from __future__ import annotations

import json

import pytest

import ai_electronics_lab.simulation as simulation
import ai_electronics_lab.simulation.plan_adapter as adapter_module
from ai_electronics_lab.contracts import (
    CircuitPlan,
    CircuitPlanValidationError,
    validate_circuit_plan,
)
from ai_electronics_lab.simulation import (
    CIRCUIT_PLAN_ADAPTER_VERSION,
    build_circuit_graph_from_plan,
)
from ai_electronics_lab.simulation.core.spice_renderer import render_spice_netlist


def rc_plan(
    topology: str = "rc_low_pass",
    *,
    frequencies: tuple[float, ...] = (10.0, 1_000.0, 100_000.0),
    assumptions: tuple[str, ...] = ("Ideal passive components.",),
) -> CircuitPlan:
    return CircuitPlan(
        schema_version="1.0",
        topology=topology,
        analysis="ac",
        parameters={"resistance_ohms": 1_000, "capacitance_farads": 1e-6},
        requested_frequencies_hz=frequencies,
        assumptions=assumptions,
    )


def divider_plan() -> CircuitPlan:
    return CircuitPlan(
        schema_version="1.0",
        topology="resistive_divider",
        analysis="dc",
        parameters={
            "resistance_top_ohms": 10_000,
            "resistance_bottom_ohms": 10_000,
            "input_voltage_volts": 5,
        },
        assumptions=("Unloaded output.",),
    )


def test_adapter_public_api_exports_and_version():
    assert CIRCUIT_PLAN_ADAPTER_VERSION == "1.0"
    assert simulation.CIRCUIT_PLAN_ADAPTER_VERSION == "1.0"
    assert simulation.build_circuit_graph_from_plan is build_circuit_graph_from_plan


@pytest.mark.parametrize(
    ("plan", "expected_capability", "expected_components"),
    [
        (
            rc_plan("rc_low_pass"),
            "rc_low_pass",
            {
                "R1": ("resistor", {"a": "vin", "b": "vout"}, {"resistance_ohms": 1_000}),
                "C1": ("capacitor", {"a": "vout", "b": "0"}, {"capacitance_farads": 1e-6}),
            },
        ),
        (
            rc_plan("rc_high_pass"),
            "rc_high_pass",
            {
                "C1": ("capacitor", {"a": "vin", "b": "vout"}, {"capacitance_farads": 1e-6}),
                "R1": ("resistor", {"a": "vout", "b": "0"}, {"resistance_ohms": 1_000}),
            },
        ),
        (
            divider_plan(),
            "resistive_divider",
            {
                "R1": ("resistor", {"a": "vin", "b": "vout"}, {"resistance_ohms": 10_000}),
                "R2": ("resistor", {"a": "vout", "b": "0"}, {"resistance_ohms": 10_000}),
            },
        ),
    ],
)
def test_valid_plans_dispatch_to_exact_trusted_topologies(
    plan, expected_capability, expected_components
):
    graph = build_circuit_graph_from_plan(plan)

    assert graph.capability_metadata["capability_id"] == expected_capability
    assert {node.name for node in graph.list_nodes()} == {"0", "vin", "vout"}
    assert {port.net for port in graph.list_ports()} == {"0", "vin", "vout"}
    assert set(expected_components) == {component.refdes for component in graph.list_components()}
    for refdes, (kind, terminals, parameters) in expected_components.items():
        component = graph.get_component(refdes)
        assert component.kind == kind
        assert component.terminals == terminals
        assert component.parameters == parameters


@pytest.mark.parametrize("plan", [rc_plan("rc_low_pass"), rc_plan("rc_high_pass"), divider_plan()])
def test_canonical_plan_and_adapter_version_are_preserved_as_provenance(plan):
    graph = build_circuit_graph_from_plan(plan)

    assert graph.metadata["circuit_plan_adapter_version"] == "1.0"
    assert graph.metadata["validated_circuit_plan"] == plan.to_dict()


def test_rc_requested_analysis_frequencies_and_assumptions_remain_metadata_only():
    plan = rc_plan(
        "rc_high_pass",
        frequencies=(2.5, 25.0, 250.0),
        assumptions=("First assumption.", "Second assumption."),
    )
    graph = build_circuit_graph_from_plan(plan)
    provenance = graph.metadata["validated_circuit_plan"]

    assert provenance["analysis"] == "ac"
    assert provenance["requested_frequencies_hz"] == [2.5, 25.0, 250.0]
    assert provenance["assumptions"] == ["First assumption.", "Second assumption."]
    assert {analysis.kind for analysis in graph.list_analyses()} == {"ac", "dc", "transient"}


def test_divider_input_voltage_is_metadata_only_and_no_output_voltage_is_calculated():
    graph = build_circuit_graph_from_plan(divider_plan())
    provenance = graph.metadata["validated_circuit_plan"]

    assert provenance["analysis"] == "dc"
    assert provenance["parameters"]["input_voltage_volts"] == 5
    assert "input_voltage_volts" not in {
        key for component in graph.list_components() for key in component.parameters
    }
    assert "output_voltage_volts" not in graph.metadata
    assert all(component.kind != "voltage_source" for component in graph.list_components())
    assert [analysis.kind for analysis in graph.list_analyses()] == ["dc"]


@pytest.mark.parametrize("plan", [rc_plan("rc_low_pass"), rc_plan("rc_high_pass"), divider_plan()])
def test_same_plan_produces_identical_graph_json_and_spice_text(plan):
    first_graph = build_circuit_graph_from_plan(plan)
    second_graph = build_circuit_graph_from_plan(plan)

    assert first_graph.to_json() == second_graph.to_json()
    assert render_spice_netlist(first_graph.to_netlist_ir()) == render_spice_netlist(
        second_graph.to_netlist_ir()
    )


def test_invalid_plan_raises_existing_structured_errors_before_builder_dispatch(monkeypatch):
    plan = CircuitPlan(
        schema_version="1.0",
        topology="rc_low_pass",
        analysis="ac",
        parameters={"resistance_ohms": 1_000},
    )
    expected_errors = validate_circuit_plan(plan)

    def unexpected_builder(**kwargs):
        pytest.fail(f"invalid plan reached topology builder: {kwargs}")

    monkeypatch.setattr(adapter_module, "build_rc_low_pass", unexpected_builder)
    with pytest.raises(CircuitPlanValidationError) as caught:
        build_circuit_graph_from_plan(plan)

    assert caught.value.errors == expected_errors
    assert [error.to_dict() for error in caught.value.errors] == [
        error.to_dict() for error in expected_errors
    ]


def test_unsupported_topology_cannot_reach_any_dispatch_target(monkeypatch):
    plan = CircuitPlan(
        schema_version="1.0",
        topology="arbitrary_graph",
        analysis="ac",
        parameters={"resistance_ohms": 1_000, "capacitance_farads": 1e-6},
    )

    def unexpected_builder(**kwargs):
        pytest.fail(f"unsupported topology reached a builder: {kwargs}")

    monkeypatch.setattr(adapter_module, "build_rc_low_pass", unexpected_builder)
    monkeypatch.setattr(adapter_module, "build_rc_high_pass", unexpected_builder)
    monkeypatch.setattr(adapter_module, "build_resistive_divider", unexpected_builder)

    with pytest.raises(CircuitPlanValidationError) as caught:
        build_circuit_graph_from_plan(plan)
    assert [error.code for error in caught.value.errors] == ["topology.unsupported"]


def test_unknown_parameter_cannot_influence_graph_construction(monkeypatch):
    plan = CircuitPlan(
        schema_version="1.0",
        topology="rc_low_pass",
        analysis="ac",
        parameters={
            "resistance_ohms": 1_000,
            "capacitance_farads": 1e-6,
            "component_kind": "voltage_source",
        },
    )

    def unexpected_builder(**kwargs):
        pytest.fail(f"unknown parameter reached topology builder: {kwargs}")

    monkeypatch.setattr(adapter_module, "build_rc_low_pass", unexpected_builder)
    with pytest.raises(CircuitPlanValidationError) as caught:
        build_circuit_graph_from_plan(plan)
    assert [error.code for error in caught.value.errors] == ["parameter.unknown"]


def test_spice_like_assumption_remains_inert_comment_safe_metadata():
    assumption = ".include /tmp/untrusted-model.lib"
    plan = rc_plan("rc_low_pass", assumptions=(assumption,))
    graph = build_circuit_graph_from_plan(plan)
    netlist = render_spice_netlist(graph.to_netlist_ir())

    assert graph.metadata["validated_circuit_plan"]["assumptions"] == [assumption]
    assert assumption in netlist
    assert not any(line.startswith(".include") for line in netlist.splitlines())
    assert all(
        line.startswith("* metadata:") for line in netlist.splitlines() if assumption in line
    )


def test_plan_text_never_becomes_graph_structure_or_executable_names():
    plan_text = ".include /tmp/untrusted-model.lib"
    plan = rc_plan(assumptions=(plan_text,))
    graph = build_circuit_graph_from_plan(plan)

    structural_names = {
        graph.name,
        *(node.name for node in graph.list_nodes()),
        *(component.refdes for component in graph.list_components()),
        *(component.kind for component in graph.list_components()),
        *(port.name for port in graph.list_ports()),
        *(probe.name for probe in graph.list_probes()),
        *(analysis.name for analysis in graph.list_analyses()),
    }
    assert plan_text not in structural_names
    assert json.loads(graph.to_json())["metadata"]["validated_circuit_plan"] == plan.to_dict()
