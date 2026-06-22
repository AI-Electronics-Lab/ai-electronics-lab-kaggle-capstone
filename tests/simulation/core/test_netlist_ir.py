from __future__ import annotations

from src.ai_electronics_lab.simulation.core import CircuitGraph


def build_simple_rc_graph() -> CircuitGraph:
    graph = CircuitGraph(name="rc_low_pass", metadata={"stage": "m8.4"})
    graph.add_node("0")
    graph.add_node("vin")
    graph.add_node("vout")
    graph.add_component("V1", "voltage_source", {"positive": "vin", "negative": "0"}, parameters={"dc_volts": 5})
    graph.add_component("R1", "resistor", {"a": "vin", "b": "vout"}, parameters={"resistance_ohms": 1000})
    graph.add_component("C1", "capacitor", {"a": "vout", "b": "0"}, parameters={"capacitance_farads": 1e-6})
    return graph


def test_netlist_ir_snapshot_is_stable_and_ordered():
    graph = build_simple_rc_graph()

    ir = graph.to_netlist_ir()
    assert ir.to_dict() == {
        "name": "rc_low_pass",
        "metadata": {"stage": "m8.4"},
        "nodes": [
            {"name": "0", "metadata": {}},
            {"name": "vin", "metadata": {}},
            {"name": "vout", "metadata": {}},
        ],
        "components": [
            {
                "refdes": "C1",
                "kind": "capacitor",
                "terminals": [("a", "vout"), ("b", "0")],
                "parameters": [("capacitance_farads", 1e-06)],
                "metadata": [],
            },
            {
                "refdes": "R1",
                "kind": "resistor",
                "terminals": [("a", "vin"), ("b", "vout")],
                "parameters": [("resistance_ohms", 1000)],
                "metadata": [],
            },
            {
                "refdes": "V1",
                "kind": "voltage_source",
                "terminals": [("negative", "0"), ("positive", "vin")],
                "parameters": [("dc_volts", 5)],
                "metadata": [],
            },
        ],
    }
