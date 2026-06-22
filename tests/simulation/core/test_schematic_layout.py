from __future__ import annotations

import json

from src.ai_electronics_lab.simulation.blocks.filters import build_rc_low_pass
from src.ai_electronics_lab.simulation.core import (
    CircuitGraph,
    build_rc_low_pass_schematic_layout,
    build_series_resistor_shunt_capacitor_schematic_layout,
)


def test_rc_layout_ir_is_serializable_and_preserves_topology_equivalence():
    graph = build_rc_low_pass(
        resistance_ohms=1_000,
        capacitance_farads=1e-6,
        vin="vin",
        vout="vout",
        metadata={"cutoff_frequency_hz": 1_000.0, "input_frequency_hz": 1_000.0},
    )

    layout = build_rc_low_pass_schematic_layout(graph)
    payload = layout.to_dict()

    assert layout.layout_id == "rc_low_pass_schematic_layout"
    assert layout.source_circuit_graph_id == "rc_low_pass"
    assert [node.net for node in layout.nodes] == ["vin", "vout", "0"]
    assert [component.refdes for component in layout.component_instances] == ["R1", "C1"]
    assert [port.name for port in layout.ports] == ["VIN", "VOUT", "GND"]
    assert [wire.wire_id for wire in layout.wires] == ["vin_to_r1", "r1_to_vout", "vout_to_c1", "vout_to_port", "c1_to_gnd"]
    assert all(check.passed for check in layout.checks)
    assert payload["metadata"]["layout_strategy"] == "series_then_shunt_to_ground"
    assert payload["checks"][0]["name"] == "output_layout_net_matches_series_and_shunt_connection"
    assert payload["checks"][0]["passed"] is True
    assert payload["checks"][1]["passed"] is True
    assert json.loads(layout.to_json()) == payload


def test_rc_layout_json_remains_deterministic_across_repeated_builds():
    graph = build_rc_low_pass(
        resistance_ohms=2_200,
        capacitance_farads=220e-9,
        vin="vin",
        vout="vout",
        metadata={"cutoff_frequency_hz": 329.733471, "input_frequency_hz": 1_000.0},
    )

    first = build_rc_low_pass_schematic_layout(graph).to_json()
    second = build_rc_low_pass_schematic_layout(graph).to_json()

    assert first == second


def test_shared_series_shunt_layout_builder_supports_non_rc_graphs():
    graph = CircuitGraph(
        name="demo_series_shunt",
        metadata={"cutoff_frequency_hz": 250.0, "input_frequency_hz": 1_000.0},
        capability_metadata={"capability_id": "demo_series_shunt", "category": "demo"},
        archetype_metadata={"archetype_id": "demo_series_shunt", "topology": "series_resistor_shunt_capacitor"},
    )
    for node_name in ("vin", "vout", "0"):
        graph.add_node(node_name)
    graph.add_component(
        "R1",
        "resistor",
        {"a": "vin", "b": "vout"},
        parameters={"resistance_ohms": 4700.0},
        metadata={"role": "series"},
    )
    graph.add_component(
        "C1",
        "capacitor",
        {"a": "vout", "b": "0"},
        parameters={"capacitance_farads": 220e-9},
        metadata={"role": "shunt"},
    )
    graph.add_port("VIN", "vin", role="input")
    graph.add_port("VOUT", "vout", role="output")
    graph.add_port("GND", "0", role="ground")

    layout = build_series_resistor_shunt_capacitor_schematic_layout(graph)

    assert layout.layout_id == "demo_series_shunt_schematic_layout"
    assert layout.source_circuit_graph_id == "demo_series_shunt"
    assert [component.refdes for component in layout.component_instances] == ["R1", "C1"]
    assert [wire.wire_id for wire in layout.wires] == ["vin_to_r1", "r1_to_vout", "vout_to_c1", "vout_to_port", "c1_to_gnd"]
    assert layout.metadata["layout_strategy"] == "series_then_shunt_to_ground"
    assert all(check.passed for check in layout.checks)
