from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

import ai_electronics_lab.simulation as simulation
import ai_electronics_lab.simulation.assembly as assembly_module
from ai_electronics_lab.contracts import (
    CircuitPlan,
    CircuitPlanValidationError,
    ValidationError,
    validate_circuit_plan,
)
from ai_electronics_lab.simulation import (
    SIMULATION_ASSEMBLY_VERSION,
    SimulationAnalysis,
    SimulationAssembly,
    build_simulation_assembly_from_plan,
)
from ai_electronics_lab.simulation.core import build_ac_voltage_source
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


def divider_plan(input_voltage: float = 5.0) -> CircuitPlan:
    return CircuitPlan(
        schema_version="1.0",
        topology="resistive_divider",
        analysis="dc",
        parameters={
            "resistance_top_ohms": 10_000,
            "resistance_bottom_ohms": 10_000,
            "input_voltage_volts": input_voltage,
        },
        assumptions=("Unloaded output.",),
    )


def statement_by_refdes(assembly: SimulationAssembly, refdes: str):
    return next(statement for statement in assembly.netlist_ir.components if statement.refdes == refdes)


def test_public_api_exports_version_and_ac_source_primitive():
    assert SIMULATION_ASSEMBLY_VERSION == "1.0"
    assert simulation.SIMULATION_ASSEMBLY_VERSION == "1.0"
    assert simulation.SimulationAnalysis is SimulationAnalysis
    assert simulation.SimulationAssembly is SimulationAssembly
    assert simulation.build_simulation_assembly_from_plan is build_simulation_assembly_from_plan
    assert callable(build_ac_voltage_source)


def test_analysis_and_assembly_are_frozen_and_serialize_deterministically():
    assembly = build_simulation_assembly_from_plan(rc_plan())

    assert assembly.to_json() == build_simulation_assembly_from_plan(rc_plan()).to_json()
    assert assembly.to_dict()["analysis"] == {
        "kind": "ac",
        "requested_frequencies_hz": [10.0, 1_000.0, 100_000.0],
        "probe_names": ["transfer_function", "vin_voltage", "vout_voltage"],
    }
    with pytest.raises(FrozenInstanceError):
        assembly.source_reference = "V2"


@pytest.mark.parametrize(
    ("plan", "expected_lines", "expected_policy", "expected_analysis", "expected_probes"),
    [
        (
            rc_plan("rc_low_pass"),
            {"C1 vout 0 1e-06", "R1 vin vout 1000", "V1 vin 0 AC 1 0"},
            "unit_ac",
            "ac",
            ("transfer_function", "vin_voltage", "vout_voltage"),
        ),
        (
            rc_plan("rc_high_pass"),
            {"C1 vin vout 1e-06", "R1 vout 0 1000", "V1 vin 0 AC 1 0"},
            "unit_ac",
            "ac",
            ("transfer_function", "vin_voltage", "vout_voltage"),
        ),
        (
            divider_plan(),
            {"R1 vin vout 10000", "R2 vout 0 10000", "V1 vin 0 DC 5"},
            "plan_dc",
            "dc",
            ("divider_ratio", "vin_voltage", "vout_voltage"),
        ),
    ],
)
def test_assemblies_preserve_passive_topology_and_add_one_fixed_trusted_source(
    plan, expected_lines, expected_policy, expected_analysis, expected_probes
):
    assembly = build_simulation_assembly_from_plan(plan)
    rendered_lines = set(render_spice_netlist(assembly.netlist_ir).splitlines())

    assert expected_lines <= rendered_lines
    assert assembly.source_reference == "V1"
    assert assembly.analysis.kind == expected_analysis
    assert assembly.analysis.probe_names == expected_probes
    assert assembly.netlist_ir.metadata["simulation_assembly_version"] == "1.0"
    assert assembly.netlist_ir.metadata["simulation_source_policy"] == expected_policy
    assert assembly.netlist_ir.metadata["validated_circuit_plan"] == plan.to_dict()

    source = statement_by_refdes(assembly, "V1")
    assert source.kind == "voltage_source"
    assert dict(source.terminals) == {"negative": "0", "positive": "vin"}
    assert [item.refdes for item in assembly.netlist_ir.components] == sorted(
        item.refdes for item in assembly.netlist_ir.components
    )
    assert sum(item.kind == "voltage_source" for item in assembly.netlist_ir.components) == 1
    assert all(item.kind != "current_source" for item in assembly.netlist_ir.components)


@pytest.mark.parametrize("topology", ["rc_low_pass", "rc_high_pass"])
def test_rc_source_policy_is_fixed_and_requested_frequencies_are_exact(topology):
    plan = rc_plan(topology, frequencies=(2.5, 25.0, 250.0))
    assembly = build_simulation_assembly_from_plan(plan)

    assert dict(statement_by_refdes(assembly, "V1").parameters) == {
        "ac_magnitude": 1.0,
        "ac_phase_deg": 0.0,
    }
    assert assembly.analysis.requested_frequencies_hz == (2.5, 25.0, 250.0)


def test_empty_rc_frequency_tuple_remains_empty_without_default_sweep():
    assembly = build_simulation_assembly_from_plan(rc_plan(frequencies=()))

    assert assembly.analysis.kind == "ac"
    assert assembly.analysis.requested_frequencies_hz == ()


@pytest.mark.parametrize("input_voltage", [5.0, -12.5])
def test_divider_dc_source_uses_validated_voltage_and_no_analysis_frequencies(input_voltage):
    assembly = build_simulation_assembly_from_plan(divider_plan(input_voltage))

    assert dict(statement_by_refdes(assembly, "V1").parameters) == {"dc_volts": input_voltage}
    assert assembly.analysis.kind == "dc"
    assert assembly.analysis.requested_frequencies_hz == ()
    assert "output_voltage_volts" not in assembly.netlist_ir.metadata
    assert assembly.netlist_ir.metadata["divider_ratio"] == pytest.approx(0.5)
    assert assembly.netlist_ir.metadata["thevenin_resistance_ohms"] == pytest.approx(5_000)


@pytest.mark.parametrize("plan", [rc_plan("rc_low_pass"), rc_plan("rc_high_pass"), divider_plan()])
def test_same_plan_produces_identical_component_deck_spice(plan):
    first = build_simulation_assembly_from_plan(plan)
    second = build_simulation_assembly_from_plan(plan)

    assert render_spice_netlist(first.netlist_ir) == render_spice_netlist(second.netlist_ir)


def test_validation_is_called_before_any_plan_field_is_read(monkeypatch):
    expected_errors = (
        ValidationError("schema_version.unsupported", ("schema_version",), "guarded"),
    )

    class GuardedPlan:
        def __getattribute__(self, name):
            pytest.fail(f"plan field was read before validation: {name}")

    guarded_plan = GuardedPlan()

    def reject_without_reading(plan):
        assert plan is guarded_plan
        raise CircuitPlanValidationError(expected_errors)

    monkeypatch.setattr(assembly_module, "require_valid_circuit_plan", reject_without_reading)
    with pytest.raises(CircuitPlanValidationError) as caught:
        build_simulation_assembly_from_plan(guarded_plan)
    assert caught.value.errors == expected_errors


def test_invalid_plan_preserves_errors_and_reaches_no_adapter_or_source_builder(monkeypatch):
    plan = CircuitPlan(
        schema_version="1.0",
        topology="rc_low_pass",
        analysis="ac",
        parameters={"resistance_ohms": 1_000},
    )
    expected_errors = validate_circuit_plan(plan)

    def unexpected_call(*args, **kwargs):
        pytest.fail(f"invalid plan crossed validation boundary: {args}, {kwargs}")

    monkeypatch.setattr(assembly_module, "build_circuit_graph_from_plan", unexpected_call)
    monkeypatch.setattr(assembly_module, "build_ac_voltage_source", unexpected_call)
    monkeypatch.setattr(assembly_module, "build_dc_voltage_source", unexpected_call)

    with pytest.raises(CircuitPlanValidationError) as caught:
        build_simulation_assembly_from_plan(plan)
    assert caught.value.errors == expected_errors
    assert [error.to_dict() for error in caught.value.errors] == [
        error.to_dict() for error in expected_errors
    ]


def test_unsupported_topology_cannot_reach_source_assembly(monkeypatch):
    plan = CircuitPlan(
        schema_version="1.0",
        topology="arbitrary_graph",
        analysis="ac",
        parameters={"resistance_ohms": 1_000, "capacitance_farads": 1e-6},
    )

    def unexpected_call(*args, **kwargs):
        pytest.fail(f"unsupported topology reached assembly: {args}, {kwargs}")

    monkeypatch.setattr(assembly_module, "build_circuit_graph_from_plan", unexpected_call)
    monkeypatch.setattr(assembly_module, "build_ac_voltage_source", unexpected_call)
    monkeypatch.setattr(assembly_module, "build_dc_voltage_source", unexpected_call)
    with pytest.raises(CircuitPlanValidationError) as caught:
        build_simulation_assembly_from_plan(plan)
    assert [error.code for error in caught.value.errors] == ["topology.unsupported"]


def test_spice_like_assumption_remains_comment_safe_and_no_analysis_directives_are_emitted():
    assumption = ".include /tmp/untrusted.lib"
    assembly = build_simulation_assembly_from_plan(rc_plan(assumptions=(assumption,)))
    netlist = render_spice_netlist(assembly.netlist_ir)
    lines = netlist.splitlines()

    assert assembly.netlist_ir.metadata["validated_circuit_plan"]["assumptions"] == [assumption]
    assert assumption in netlist
    assert all(line.startswith("* metadata:") for line in lines if assumption in line)
    forbidden_prefixes = (
        ".include",
        ".control",
        ".shell",
        ".exec",
        ".ac",
        ".op",
        ".dc",
        ".tran",
        ".save",
        ".print",
        ".measure",
    )
    assert not any(line.lower().startswith(forbidden_prefixes) for line in lines)
    assert lines[-1] == ".end"
