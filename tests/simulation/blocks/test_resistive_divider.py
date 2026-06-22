from __future__ import annotations

import json
from math import isfinite
from types import MappingProxyType

import pytest

from ai_electronics_lab.simulation.blocks.filters import build_rc_high_pass, build_rc_low_pass
from ai_electronics_lab.simulation.blocks.networks import (
    RESISTIVE_DIVIDER_BLOCK,
    build_resistive_divider,
)
from ai_electronics_lab.simulation.core import (
    CircuitAnalysis,
    CircuitComponent,
    CircuitGraphError,
    RegistryContract,
)
from ai_electronics_lab.simulation.core.spice_renderer import render_spice_netlist


def divider_graph():
    return build_resistive_divider(
        resistance_top_ohms=10_000,
        resistance_bottom_ohms=10_000,
        vin="vin",
        vout="vout",
    )


def test_resistive_divider_block_exposes_and_registers_its_descriptor():
    descriptor = RESISTIVE_DIVIDER_BLOCK.to_registry_descriptor()

    assert descriptor.kind == "topology_block"
    assert descriptor.identifier == "resistive_divider"
    assert descriptor.summary == "Isolated unloaded resistive-divider topology block MVP"
    assert descriptor.version == "m8.8"
    assert descriptor.metadata == {
        "category": "passive_networks",
        "caveat_tags": ["ideal_passive", "unloaded_output"],
        "failure_modes": ["invalid_resistance_values", "invalid_node_tokens"],
        "generated_subgraph": ["vin", "R1", "vout", "R2", "gnd"],
        "metrics": ["divider_ratio", "thevenin_resistance_ohms"],
        "maturity": "mvp",
        "parameters": ["resistance_top_ohms", "resistance_bottom_ohms"],
        "ports": ["vin", "vout", "gnd"],
        "supported_analyses": ["dc"],
    }

    registry = RegistryContract()
    assert RESISTIVE_DIVIDER_BLOCK.register(registry) == descriptor
    assert registry.contains("topology_block", "resistive_divider")


def test_valid_divider_graph_has_exact_metadata_ports_probes_and_dc_analysis():
    graph = divider_graph()

    assert graph.validate_resistive_divider_topology() is None
    assert graph.capability_metadata["capability_id"] == "resistive_divider"
    assert graph.capability_metadata["category"] == "passive_networks"
    assert graph.capability_metadata["maturity"] == "mvp"
    assert graph.archetype_metadata["archetype_id"] == "resistive_divider_vertical_slice"
    assert graph.archetype_metadata["topology"] == "series_resistor_shunt_resistor"
    assert [(port.name, port.role, port.net) for port in graph.list_ports()] == [
        ("GND", "ground", "0"),
        ("VIN", "input", "vin"),
        ("VOUT", "output", "vout"),
    ]
    assert [probe.name for probe in graph.list_probes()] == [
        "vin_voltage",
        "vout_voltage",
        "divider_ratio",
    ]
    assert [analysis.to_dict() for analysis in graph.list_analyses()] == [
        {
            "name": "dc",
            "kind": "dc",
            "parameters": {},
            "metadata": {"domain": "bias"},
        }
    ]


def test_divider_connectivity_is_upper_r1_and_lower_r2():
    graph = divider_graph()

    assert graph.get_component("R1").kind == "resistor"
    assert graph.get_component("R1").terminals == {"a": "vin", "b": "vout"}
    assert graph.get_component("R1").metadata["role"] == "upper"
    assert graph.get_component("R2").kind == "resistor"
    assert graph.get_component("R2").terminals == {"a": "vout", "b": "0"}
    assert graph.get_component("R2").metadata["role"] == "lower"


def test_equal_resistors_record_deterministic_divider_metrics():
    graph = build_resistive_divider(
        resistance_top_ohms=10_000,
        resistance_bottom_ohms=10_000,
        vin="vin",
        vout="vout",
        metadata={"divider_ratio": 0.9, "note": "caller metadata"},
    )

    assert graph.metadata["resistance_top_ohms"] == 10_000
    assert graph.metadata["resistance_bottom_ohms"] == 10_000
    assert graph.metadata["divider_ratio"] == pytest.approx(0.5)
    assert graph.metadata["thevenin_resistance_ohms"] == pytest.approx(5_000)
    assert graph.metadata["note"] == "caller metadata"
    assert "input_voltage_volts" not in graph.metadata
    assert "output_voltage_volts" not in graph.metadata


def test_extreme_equal_resistors_produce_finite_stable_metrics():
    graph = build_resistive_divider(
        resistance_top_ohms=1e308,
        resistance_bottom_ohms=1e308,
        vin="vin",
        vout="vout",
    )

    divider_ratio = graph.metadata["divider_ratio"]
    thevenin_resistance = graph.metadata["thevenin_resistance_ohms"]
    assert isfinite(divider_ratio)
    assert isfinite(thevenin_resistance)
    assert divider_ratio == pytest.approx(0.5)
    assert thevenin_resistance == pytest.approx(5e307)


def test_divider_graph_json_is_deterministic():
    first = divider_graph().to_json()
    second = divider_graph().to_json()

    assert first == second
    payload = json.loads(first)
    assert payload["name"] == "resistive_divider"
    assert [component["refdes"] for component in payload["components"]] == ["R1", "R2"]
    assert payload["metadata"]["divider_ratio"] == 0.5


def test_divider_spice_rendering_is_deterministic_and_passive_only():
    netlist = render_spice_netlist(divider_graph().to_netlist_ir())
    lines = netlist.splitlines()

    assert netlist == render_spice_netlist(divider_graph().to_netlist_ir())
    assert "R1 vin vout 10000" in lines
    assert "R2 vout 0 10000" in lines
    assert not any(line.startswith("V") for line in lines)
    assert [component.refdes for component in divider_graph().list_components()] == ["R1", "R2"]


@pytest.mark.parametrize(
    ("top", "bottom", "match"),
    [
        (0, 10_000, "greater than zero"),
        (-1, 10_000, "greater than zero"),
        (True, 10_000, "numeric"),
        ("10000", 10_000, "numeric"),
        (float("nan"), 10_000, "finite"),
        (float("inf"), 10_000, "finite"),
        (10_000, 0, "greater than zero"),
        (10_000, -1, "greater than zero"),
        (10_000, True, "numeric"),
        (10_000, "10000", "numeric"),
        (10_000, float("nan"), "finite"),
        (10_000, float("inf"), "finite"),
    ],
)
def test_divider_rejects_invalid_resistance_values(top, bottom, match):
    with pytest.raises(CircuitGraphError, match=match):
        build_resistive_divider(
            resistance_top_ohms=top,
            resistance_bottom_ohms=bottom,
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
def test_divider_rejects_invalid_or_reused_node_tokens(vin, vout, gnd, match):
    with pytest.raises(CircuitGraphError, match=match):
        build_resistive_divider(
            resistance_top_ohms=10_000,
            resistance_bottom_ohms=10_000,
            vin=vin,
            vout=vout,
            gnd=gnd,
        )


@pytest.mark.parametrize(
    ("metadata_name", "key", "value", "match"),
    [
        ("capability", "capability_id", "wrong", "capability metadata"),
        ("archetype", "archetype_id", "wrong", "archetype metadata"),
        ("archetype", "topology", "wrong", "topology metadata"),
    ],
)
def test_divider_validator_rejects_incorrect_identifiers(metadata_name, key, value, match):
    graph = divider_graph()
    attribute = f"_{metadata_name}_metadata"
    current = getattr(graph, attribute)
    setattr(graph, attribute, MappingProxyType({**current, key: value}))

    with pytest.raises(CircuitGraphError, match=match):
        graph.validate_resistive_divider_topology()


@pytest.mark.parametrize("mutation", ["missing", "extra"])
def test_divider_validator_rejects_missing_or_extra_components(mutation):
    graph = divider_graph()
    if mutation == "missing":
        graph._components.pop("R2")
    else:
        graph.add_component(
            "R3",
            "resistor",
            {"a": "vin", "b": "0"},
            parameters={"resistance_ohms": 1_000},
        )

    with pytest.raises(CircuitGraphError, match="only R1 and R2"):
        graph.validate_resistive_divider_topology()


@pytest.mark.parametrize("refdes", ["R1", "R2"])
def test_divider_validator_rejects_wrong_component_kinds(refdes):
    graph = divider_graph()
    component = graph.get_component(refdes)
    graph._components[refdes] = CircuitComponent(
        refdes,
        "capacitor",
        component.terminals,
        parameters={"capacitance_farads": 1e-6},
    )

    with pytest.raises(CircuitGraphError, match=f"{refdes} must be a resistor"):
        graph.validate_resistive_divider_topology()


def test_divider_validator_rejects_component_self_short():
    graph = divider_graph()
    graph._components["R2"] = CircuitComponent(
        "R2",
        "resistor",
        {"a": "vout", "b": "vout"},
        parameters={"resistance_ohms": 10_000},
    )

    with pytest.raises(CircuitGraphError, match="direct short"):
        graph.validate_resistive_divider_topology()


def test_divider_validator_rejects_inverted_resistor_placement():
    graph = divider_graph()
    graph._components["R1"] = CircuitComponent(
        "R1",
        "resistor",
        {"a": "vout", "b": "0"},
        parameters={"resistance_ohms": 10_000},
    )
    graph._components["R2"] = CircuitComponent(
        "R2",
        "resistor",
        {"a": "vin", "b": "vout"},
        parameters={"resistance_ohms": 10_000},
    )

    with pytest.raises(CircuitGraphError, match="R1 must connect input to output"):
        graph.validate_resistive_divider_topology()


@pytest.mark.parametrize("mutation", ["missing", "extra", "wrong_kind"])
def test_divider_validator_rejects_missing_extra_or_mismatched_analyses(mutation):
    graph = divider_graph()
    if mutation == "missing":
        graph._analyses.pop("dc")
    elif mutation == "extra":
        graph.add_analysis("ac", kind="ac", parameters={})
    else:
        graph._analyses["dc"] = CircuitAnalysis("dc", "ac")

    with pytest.raises(CircuitGraphError, match="analysis"):
        graph.validate_resistive_divider_topology()


@pytest.mark.parametrize("mutation", ["missing", "extra"])
def test_divider_validator_rejects_missing_or_extra_probes(mutation):
    graph = divider_graph()
    if mutation == "missing":
        graph._probes.pop("divider_ratio")
    else:
        graph.add_probe("unexpected", kind="voltage", target="vout")

    with pytest.raises(CircuitGraphError, match="probes"):
        graph.validate_resistive_divider_topology()


def test_divider_artifact_manifest_mismatch_is_rejected():
    graph = divider_graph()

    with pytest.raises(CircuitGraphError, match="artifact manifest"):
        graph.validate_artifact_consistency(
            {
                "netlist": "unexpected.net",
                "report": "report.md",
                "visual_report_data": "visual_report_data.json",
            }
        )


def test_existing_rc_topologies_remain_unchanged():
    low_pass = build_rc_low_pass(
        resistance_ohms=1_000,
        capacitance_farads=1e-6,
        vin="vin",
        vout="vout",
    )
    high_pass = build_rc_high_pass(
        resistance_ohms=1_000,
        capacitance_farads=1e-6,
        vin="vin",
        vout="vout",
    )

    assert low_pass.validate_rc_low_pass_topology() is None
    assert low_pass.get_component("R1").terminals == {"a": "vin", "b": "vout"}
    assert high_pass.validate_rc_high_pass_topology() is None
    assert high_pass.get_component("C1").terminals == {"a": "vin", "b": "vout"}
