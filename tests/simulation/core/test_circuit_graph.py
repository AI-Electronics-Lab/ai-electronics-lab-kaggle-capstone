from __future__ import annotations

import copy

import pytest

from ai_electronics_lab.simulation.core import CircuitGraph, CircuitGraphError


def build_simple_rc_graph() -> CircuitGraph:
    graph = CircuitGraph(name="rc_low_pass", metadata={"stage": "m8.4"})
    graph.add_node("0")
    graph.add_node("vin")
    graph.add_node("vout")
    graph.add_component(
        refdes="V1",
        kind="voltage_source",
        terminals={"positive": "vin", "negative": "0"},
        parameters={"dc_volts": 5},
        metadata={"role": "input"},
    )
    graph.add_component(
        refdes="R1",
        kind="resistor",
        terminals={"a": "vin", "b": "vout"},
        parameters={"resistance_ohms": 1000},
    )
    graph.add_component(
        refdes="C1",
        kind="capacitor",
        terminals={"a": "vout", "b": "0"},
        parameters={"capacitance_farads": 1e-6},
    )
    return graph


def test_empty_graph_retains_name_metadata_and_exports_deterministically():
    graph = CircuitGraph(name="demo", metadata={"stage": "m8.4", "tags": ["foundation"]})

    assert graph.name == "demo"
    assert graph.metadata["stage"] == "m8.4"
    assert graph.metadata["tags"] == ["foundation"]
    assert graph.list_nodes() == ()
    assert graph.list_components() == ()
    assert graph.to_dict() == {
        "name": "demo",
        "metadata": {"stage": "m8.4", "tags": ["foundation"]},
        "capability_metadata": {},
        "archetype_metadata": {},
        "nodes": [],
        "nets": [],
        "components": [],
        "ports": [],
        "probes": [],
        "analyses": [],
    }



def test_simple_rc_graph_lists_nodes_and_components_in_deterministic_order():
    graph = build_simple_rc_graph()

    assert [node.name for node in graph.list_nodes()] == ["0", "vin", "vout"]
    assert [component.refdes for component in graph.list_components()] == ["C1", "R1", "V1"]
    assert graph.get_component("R1").terminals == {"a": "vin", "b": "vout"}
    assert graph.get_component("V1").metadata["role"] == "input"


def test_duplicate_refdes_is_rejected():
    graph = CircuitGraph(name="demo")
    graph.add_node("0")
    graph.add_node("vin")
    graph.add_component("R1", "resistor", {"a": "vin", "b": "0"})

    with pytest.raises(CircuitGraphError, match="duplicate refdes"):
        graph.add_component("R1", "resistor", {"a": "vin", "b": "0"})


def test_invalid_component_rejected_for_empty_refdes_kind_missing_terminals_and_missing_nodes():
    graph = CircuitGraph(name="demo")
    graph.add_node("0")

    with pytest.raises(CircuitGraphError, match="refdes"):
        graph.add_component("", "resistor", {"a": "0", "b": "0"})

    with pytest.raises(CircuitGraphError, match="kind"):
        graph.add_component("R1", "", {"a": "0", "b": "0"})

    with pytest.raises(CircuitGraphError, match="terminal"):
        graph.add_component("R2", "resistor", {})

    with pytest.raises(CircuitGraphError, match="node"):
        graph.add_component("R3", "resistor", {"a": "0", "b": "vin"})


def test_component_input_mappings_do_not_leak_mutation_back_into_graph():
    graph = CircuitGraph(name="demo", metadata={"tags": ["original"]})
    graph.add_node("0")
    graph.add_node("vin")
    graph.add_node("vout")

    terminals = {"a": "vin", "b": "vout"}
    parameters = {"curve": [1, 2]}
    metadata = {"notes": ["seed"]}
    graph.add_component("R1", "resistor", terminals, parameters=parameters, metadata=metadata)

    terminals["a"] = "0"
    parameters["curve"].append(3)
    metadata["notes"].append("changed")

    component = graph.get_component("R1")
    assert component.terminals == {"a": "vin", "b": "vout"}
    assert component.parameters == {"curve": [1, 2]}
    assert component.metadata == {"notes": ["seed"]}
    assert graph.metadata == {"tags": ["original"]}

    exported = graph.to_dict()
    exported["components"][0]["parameters"]["curve"].append(999)
    assert graph.get_component("R1").parameters == {"curve": [1, 2]}


def test_graph_copy_round_trip_is_isolated_from_external_mutation():
    graph = build_simple_rc_graph()
    graph_snapshot = graph.to_dict()
    round_trip = copy.deepcopy(graph_snapshot)
    round_trip["components"][2]["terminals"][0] = ("positive", "mutated")

    assert graph.to_dict() == graph_snapshot
