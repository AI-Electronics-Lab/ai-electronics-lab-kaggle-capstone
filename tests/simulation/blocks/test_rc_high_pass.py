from __future__ import annotations

import json
from types import MappingProxyType

import pytest

from ai_electronics_lab.simulation.blocks.filters import (
    RC_HIGH_PASS_BLOCK,
    build_rc_high_pass,
    build_rc_low_pass,
)
from ai_electronics_lab.simulation.core import (
    CircuitComponent,
    CircuitGraphError,
    RegistryContract,
)
from ai_electronics_lab.simulation.core.spice_renderer import render_spice_netlist


def high_pass_graph():
    return build_rc_high_pass(
        resistance_ohms=1_000,
        capacitance_farads=1e-6,
        vin="vin",
        vout="vout",
    )


def test_rc_high_pass_block_exposes_and_registers_its_descriptor():
    descriptor = RC_HIGH_PASS_BLOCK.to_registry_descriptor()

    assert descriptor.kind == "topology_block"
    assert descriptor.identifier == "rc_high_pass"
    assert descriptor.summary == "Isolated RC high-pass topology block MVP"
    assert descriptor.version == "m8.8"
    assert descriptor.metadata == {
        "category": "filters",
        "caveat_tags": ["ideal_passive", "no_loading_accounted"],
        "failure_modes": ["invalid_rc_values", "invalid_node_tokens"],
        "generated_subgraph": ["vin", "C", "vout", "R", "gnd"],
        "metrics": ["cutoff_frequency_hz", "time_constant_s"],
        "maturity": "mvp",
        "parameters": ["resistance_ohms", "capacitance_farads"],
        "ports": ["vin", "vout", "gnd"],
        "supported_analyses": ["dc", "ac", "transient"],
    }

    registry = RegistryContract()
    assert RC_HIGH_PASS_BLOCK.register(registry) == descriptor
    assert registry.contains("topology_block", "rc_high_pass")


def test_valid_high_pass_graph_has_required_metadata_ports_probes_and_analyses():
    graph = high_pass_graph()

    assert graph.validate_rc_high_pass_topology() is None
    assert graph.capability_metadata["capability_id"] == "rc_high_pass"
    assert graph.capability_metadata["category"] == "filters"
    assert graph.capability_metadata["maturity"] == "mvp"
    assert graph.archetype_metadata["archetype_id"] == "rc_high_pass_vertical_slice"
    assert graph.archetype_metadata["topology"] == "series_capacitor_shunt_resistor"
    assert [(port.name, port.role, port.net) for port in graph.list_ports()] == [
        ("GND", "ground", "0"),
        ("VIN", "input", "vin"),
        ("VOUT", "output", "vout"),
    ]
    assert [probe.name for probe in graph.list_probes()] == [
        "vin_voltage",
        "vout_voltage",
        "transfer_function",
    ]
    assert [(analysis.name, analysis.kind) for analysis in graph.list_analyses()] == [
        ("ac", "ac"),
        ("dc", "dc"),
        ("transient", "transient"),
    ]


def test_high_pass_connectivity_is_series_capacitor_and_shunt_resistor():
    graph = high_pass_graph()

    assert graph.get_component("C1").kind == "capacitor"
    assert graph.get_component("C1").terminals == {"a": "vin", "b": "vout"}
    assert graph.get_component("R1").kind == "resistor"
    assert graph.get_component("R1").terminals == {"a": "vout", "b": "0"}


def test_high_pass_graph_json_is_deterministic():
    first = high_pass_graph().to_json()
    second = high_pass_graph().to_json()

    assert first == second
    payload = json.loads(first)
    assert payload["name"] == "rc_high_pass"
    assert [component["refdes"] for component in payload["components"]] == ["C1", "R1"]


def test_high_pass_spice_rendering_is_deterministic_and_has_expected_connectivity():
    netlist = render_spice_netlist(high_pass_graph().to_netlist_ir())

    assert netlist == render_spice_netlist(high_pass_graph().to_netlist_ir())
    assert "C1 vin vout 1e-06" in netlist.splitlines()
    assert "R1 vout 0 1000" in netlist.splitlines()


@pytest.mark.parametrize(
    ("resistance", "capacitance", "match"),
    [
        (0, 1e-6, "greater than zero"),
        (-1, 1e-6, "greater than zero"),
        (True, 1e-6, "numeric"),
        ("1000", 1e-6, "numeric"),
        (float("nan"), 1e-6, "finite"),
        (float("inf"), 1e-6, "finite"),
        (1_000, 0, "greater than zero"),
        (1_000, -1e-6, "greater than zero"),
        (1_000, True, "numeric"),
        (1_000, float("nan"), "finite"),
        (1_000, float("inf"), "finite"),
    ],
)
def test_high_pass_rejects_invalid_resistance_and_capacitance(resistance, capacitance, match):
    with pytest.raises(CircuitGraphError, match=match):
        build_rc_high_pass(
            resistance_ohms=resistance,
            capacitance_farads=capacitance,
            vin="vin",
            vout="vout",
        )


@pytest.mark.parametrize(
    ("vin", "vout", "gnd", "match"),
    [
        (None, "vout", "0", "non-empty string"),
        (" vin", "vout", "0", "node name"),
        ("vin", "v out", "0", "whitespace"),
        ("vin", "vin", "0", "different nodes"),
        ("0", "vout", "0", "ground node"),
        ("vin", "0", "0", "ground node"),
    ],
)
def test_high_pass_rejects_invalid_or_reused_node_tokens(vin, vout, gnd, match):
    with pytest.raises(CircuitGraphError, match=match):
        build_rc_high_pass(
            resistance_ohms=1_000,
            capacitance_farads=1e-6,
            vin=vin,
            vout=vout,
            gnd=gnd,
        )


def test_high_pass_validator_rejects_incorrect_capability_metadata():
    graph = high_pass_graph()
    graph._capability_metadata = MappingProxyType({**graph.capability_metadata, "capability_id": "rc_low_pass"})

    with pytest.raises(CircuitGraphError, match="capability metadata"):
        graph.validate_rc_high_pass_topology()


def test_high_pass_validator_rejects_incorrect_archetype_metadata():
    graph = high_pass_graph()
    graph._archetype_metadata = MappingProxyType({**graph.archetype_metadata, "archetype_id": "wrong"})

    with pytest.raises(CircuitGraphError, match="archetype metadata"):
        graph.validate_rc_high_pass_topology()


def test_high_pass_validator_rejects_incorrect_topology_metadata():
    graph = high_pass_graph()
    graph._archetype_metadata = MappingProxyType(
        {**graph.archetype_metadata, "topology": "series_resistor_shunt_capacitor"}
    )

    with pytest.raises(CircuitGraphError, match="topology metadata"):
        graph.validate_rc_high_pass_topology()


@pytest.mark.parametrize("mutation", ["missing", "extra"])
def test_high_pass_validator_rejects_missing_or_extra_components(mutation):
    graph = high_pass_graph()
    if mutation == "missing":
        graph._components.pop("C1")
    else:
        graph.add_component(
            "R2",
            "resistor",
            {"a": "vin", "b": "0"},
            parameters={"resistance_ohms": 2_000},
        )

    with pytest.raises(CircuitGraphError, match="only C1 and R1"):
        graph.validate_rc_high_pass_topology()


def test_high_pass_validator_rejects_component_self_short():
    graph = high_pass_graph()
    graph._components["C1"] = CircuitComponent(
        "C1",
        "capacitor",
        {"a": "vin", "b": "vin"},
        parameters={"capacitance_farads": 1e-6},
    )

    with pytest.raises(CircuitGraphError, match="direct short"):
        graph.validate_rc_high_pass_topology()


def test_high_pass_validator_rejects_inverse_low_pass_topology():
    graph = high_pass_graph()
    graph._components["C1"] = CircuitComponent(
        "C1",
        "capacitor",
        {"a": "vout", "b": "0"},
        parameters={"capacitance_farads": 1e-6},
    )
    graph._components["R1"] = CircuitComponent(
        "R1",
        "resistor",
        {"a": "vin", "b": "vout"},
        parameters={"resistance_ohms": 1_000},
    )

    with pytest.raises(CircuitGraphError, match="capacitor must connect input to output"):
        graph.validate_rc_high_pass_topology()


def test_high_pass_artifact_manifest_mismatch_is_rejected():
    graph = high_pass_graph()

    with pytest.raises(CircuitGraphError, match="artifact manifest"):
        graph.validate_artifact_consistency(
            {
                "netlist": "unexpected.net",
                "report": "report.md",
                "visual_report_data": "visual_report_data.json",
            }
        )


def test_existing_low_pass_topology_remains_unchanged():
    graph = build_rc_low_pass(
        resistance_ohms=1_000,
        capacitance_farads=1e-6,
        vin="vin",
        vout="vout",
    )

    assert graph.validate_rc_low_pass_topology() is None
    assert graph.get_component("R1").terminals == {"a": "vin", "b": "vout"}
    assert graph.get_component("C1").terminals == {"a": "vout", "b": "0"}
