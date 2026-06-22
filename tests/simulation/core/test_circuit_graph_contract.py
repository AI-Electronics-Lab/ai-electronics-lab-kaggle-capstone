from __future__ import annotations

import json

import pytest

from src.ai_electronics_lab.simulation.blocks.filters import build_rc_low_pass
from src.ai_electronics_lab.simulation.core import CircuitGraph, CircuitGraphError


def test_rc_low_pass_graph_exposes_ports_probes_analyses_and_json_contract():
    graph = build_rc_low_pass(
        resistance_ohms=1_000,
        capacitance_farads=1e-6,
        vin="vin",
        vout="vout",
    )

    assert graph.capability_metadata["capability_id"] == "rc_low_pass"
    assert graph.archetype_metadata["archetype_id"] == "rc_low_pass_vertical_slice"
    assert [port.name for port in graph.list_ports()] == ["GND", "VIN", "VOUT"]
    assert [probe.name for probe in graph.list_probes()] == ["vin_voltage", "vout_voltage", "transfer_function"]
    assert [analysis.kind for analysis in graph.list_analyses()] == ["ac", "dc", "transient"]
    assert graph.validate_rc_low_pass_topology() is None

    payload = graph.to_dict()
    assert payload["metadata"]["capability_id"] == "rc_low_pass"
    assert payload["metadata"]["archetype_id"] == "rc_low_pass_vertical_slice"
    assert payload["capability_metadata"]["capability_id"] == "rc_low_pass"
    assert payload["archetype_metadata"]["archetype_id"] == "rc_low_pass_vertical_slice"
    assert [item["name"] for item in payload["ports"]] == ["GND", "VIN", "VOUT"]
    assert [item["name"] for item in payload["probes"]] == ["vin_voltage", "vout_voltage", "transfer_function"]
    assert [item["kind"] for item in payload["analyses"]] == ["ac", "dc", "transient"]

    assert json.loads(graph.to_json()) == payload


def test_rc_low_pass_validator_rejects_old_false_short_topology():
    graph = CircuitGraph(
        name="rc_low_pass",
        metadata={"block": "rc_low_pass"},
        capability_metadata={"capability_id": "rc_low_pass"},
        archetype_metadata={"archetype_id": "rc_low_pass_vertical_slice"},
    )
    graph.add_node("0")
    graph.add_node("vin")
    graph.add_node("vout")
    graph.add_port("VIN", "vin", role="input")
    graph.add_port("VOUT", "vout", role="output")
    graph.add_port("GND", "0", role="ground")
    graph.add_probe("vin_voltage", kind="voltage", target="vin")
    graph.add_probe("vout_voltage", kind="voltage", target="vout")
    graph.add_probe("transfer_function", kind="transfer_function", target="vout")
    graph.add_analysis("ac", kind="ac", parameters={"start_hz": 1, "stop_hz": 10_000, "points_per_decade": 10})
    graph.add_analysis("dc", kind="dc", parameters={})
    graph.add_analysis("transient", kind="transient", parameters={"stop_s": 0.01})
    graph.add_component("R1", "resistor", {"a": "vin", "b": "0"}, parameters={"resistance_ohms": 1000})
    graph.add_component("C1", "capacitor", {"a": "vout", "b": "0"}, parameters={"capacitance_farads": 1e-6})

    with pytest.raises(CircuitGraphError, match="short"):
        graph.validate_rc_low_pass_topology()


def test_rc_low_pass_validate_artifact_consistency_rejects_mismatched_manifest():
    graph = build_rc_low_pass(
        resistance_ohms=1_000,
        capacitance_farads=1e-6,
        vin="vin",
        vout="vout",
    )

    with pytest.raises(CircuitGraphError, match="artifact manifest"):
        graph.validate_artifact_consistency(
            {
                "netlist": "unexpected.net",
                "report": "report.md",
                "visual_report_data": "visual_report_data.json",
            }
        )
