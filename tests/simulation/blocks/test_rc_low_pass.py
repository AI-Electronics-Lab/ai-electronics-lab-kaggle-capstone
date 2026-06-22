from __future__ import annotations

import pytest

from ai_electronics_lab.simulation.blocks.filters.rc_low_pass import (
    RC_LOW_PASS_BLOCK,
    build_rc_low_pass,
)
from ai_electronics_lab.simulation.core import CircuitGraphError, RegistryContract
from ai_electronics_lab.simulation.core.spice_renderer import render_spice_netlist


def test_rc_low_pass_block_exposes_a_registry_descriptor():
    descriptor = RC_LOW_PASS_BLOCK.to_registry_descriptor()

    assert descriptor.kind == "topology_block"
    assert descriptor.identifier == "rc_low_pass"
    assert descriptor.summary == "Isolated RC low-pass topology block MVP"
    assert descriptor.version == "m8.8"
    assert descriptor.metadata == {
        "category": "filters",
        "caveat_tags": ["ideal_passive", "no_loading_accounted"],
        "failure_modes": ["invalid_rc_values", "invalid_node_tokens"],
        "generated_subgraph": ["vin", "R", "vout", "C", "gnd"],
        "metrics": ["cutoff_frequency_hz", "time_constant_s"],
        "maturity": "mvp",
        "parameters": ["resistance_ohms", "capacitance_farads"],
        "ports": ["vin", "vout", "gnd"],
        "supported_analyses": ["dc", "ac", "transient"],
    }


def test_rc_low_pass_block_registers_with_the_registry_contract():
    registry = RegistryContract()

    registered = RC_LOW_PASS_BLOCK.register(registry)

    assert registered == RC_LOW_PASS_BLOCK.to_registry_descriptor()
    assert registry.contains("topology_block", "rc_low_pass") is True


def test_rc_low_pass_block_builds_a_deterministic_circuit_graph_and_spice_netlist():
    graph = build_rc_low_pass(
        resistance_ohms=1000,
        capacitance_farads=1e-6,
        vin="vin",
        vout="vout",
    )

    assert graph.validate_rc_low_pass_topology() is None
    assert graph.capability_metadata["capability_id"] == "rc_low_pass"
    assert graph.archetype_metadata["archetype_id"] == "rc_low_pass_vertical_slice"
    assert graph.to_dict() == {
        "name": "rc_low_pass",
        "metadata": {
            "archetype_id": "rc_low_pass_vertical_slice",
            "block": "rc_low_pass",
            "capability_id": "rc_low_pass",
            "capability_version": "m8.8",
            "category": "filters",
            "capacitance_farads": 1e-06,
            "maturity": "mvp",
            "resistance_ohms": 1000,
            "version": "m8.8",
        },
        "capability_metadata": {
            "artifact_manifest": {
                "netlist": "circuit.net",
                "report": "report.md",
                "visual_report_data": "visual_report_data.json",
            },
            "archetype_id": "rc_low_pass_vertical_slice",
            "capability_id": "rc_low_pass",
            "capability_version": "m8.8",
            "category": "filters",
            "maturity": "mvp",
            "ports": ["VIN", "VOUT", "GND"],
            "probes": ["vin_voltage", "vout_voltage", "transfer_function"],
            "supported_analyses": ["ac", "dc", "transient"],
        },
        "archetype_metadata": {
            "archetype_family": "vertical_slice",
            "archetype_id": "rc_low_pass_vertical_slice",
            "ports": ["VIN", "VOUT", "GND"],
            "topology": "series_resistor_shunt_capacitor",
        },
        "nodes": [
            {"name": "0", "metadata": {}},
            {"name": "vin", "metadata": {}},
            {"name": "vout", "metadata": {}},
        ],
        "nets": [
            {"name": "0", "metadata": {}},
            {"name": "vin", "metadata": {}},
            {"name": "vout", "metadata": {}},
        ],
        "components": [
            {
                "refdes": "C1",
                "kind": "capacitor",
                "terminals": {"a": "vout", "b": "0"},
                "parameters": {"capacitance_farads": 1e-06},
                "metadata": {"block": "rc_low_pass", "role": "shunt"},
            },
            {
                "refdes": "R1",
                "kind": "resistor",
                "terminals": {"a": "vin", "b": "vout"},
                "parameters": {"resistance_ohms": 1000},
                "metadata": {"block": "rc_low_pass", "role": "series"},
            },
        ],
        "ports": [
            {"name": "GND", "net": "0", "role": "ground", "metadata": {"signal": "reference"}},
            {"name": "VIN", "net": "vin", "role": "input", "metadata": {"signal": "input"}},
            {"name": "VOUT", "net": "vout", "role": "output", "metadata": {"signal": "output"}},
        ],
        "probes": [
            {"name": "vin_voltage", "kind": "voltage", "target": "vin", "metadata": {"port": "VIN"}},
            {"name": "vout_voltage", "kind": "voltage", "target": "vout", "metadata": {"port": "VOUT"}},
            {
                "name": "transfer_function",
                "kind": "transfer_function",
                "target": "vout",
                "metadata": {"from": "VIN", "to": "VOUT"},
            },
        ],
        "analyses": [
            {
                "name": "ac",
                "kind": "ac",
                "parameters": {"points_per_decade": 10, "start_hz": 1.0, "stop_hz": 1000000.0},
                "metadata": {"domain": "frequency"},
            },
            {"name": "dc", "kind": "dc", "parameters": {}, "metadata": {"domain": "bias"}},
            {
                "name": "transient",
                "kind": "transient",
                "parameters": {"step_s": 1e-05, "stop_s": 0.01},
                "metadata": {"domain": "time"},
            },
        ],
    }
    assert render_spice_netlist(graph.to_netlist_ir()) == "\n".join(
        [
            "* rc_low_pass",
            "* metadata: archetype_id=rc_low_pass_vertical_slice",
            "* metadata: block=rc_low_pass",
            "* metadata: capability_id=rc_low_pass",
            "* metadata: capability_version=m8.8",
            "* metadata: capacitance_farads=1e-06",
            "* metadata: category=filters",
            "* metadata: maturity=mvp",
            "* metadata: resistance_ohms=1000",
            "* metadata: version=m8.8",
            "C1 vout 0 1e-06",
            "R1 vin vout 1000",
            ".end",
        ]
    )


def test_rc_low_pass_block_rejects_invalid_tokens_and_nonpositive_values():
    with pytest.raises(CircuitGraphError, match="node name"):
        build_rc_low_pass(resistance_ohms=1000, capacitance_farads=1e-6, vin=" vin", vout="vout")

    with pytest.raises(CircuitGraphError, match="node name"):
        build_rc_low_pass(resistance_ohms=1000, capacitance_farads=1e-6, vin="vin", vout="v out")

    with pytest.raises(CircuitGraphError, match="greater than zero"):
        build_rc_low_pass(resistance_ohms=0, capacitance_farads=1e-6, vin="vin", vout="vout")

    with pytest.raises(CircuitGraphError, match="greater than zero"):
        build_rc_low_pass(resistance_ohms=1000, capacitance_farads=-1e-6, vin="vin", vout="vout")
