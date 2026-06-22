from __future__ import annotations

import pytest

from src.ai_electronics_lab.simulation.core import CircuitGraph
from src.ai_electronics_lab.simulation.core.spice_renderer import SpiceRendererError, render_spice_netlist


def build_renderable_rc_graph() -> CircuitGraph:
    graph = CircuitGraph(name="rc_low_pass", metadata={"stage": "m8.5"})
    graph.add_node("0")
    graph.add_node("vin")
    graph.add_node("vout")
    graph.add_component("V1", "voltage_source", {"positive": "vin", "negative": "0"}, parameters={"dc_volts": 0})
    graph.add_component("R1", "resistor", {"a": "vin", "b": "vout"}, parameters={"resistance_ohms": 3183.1})
    graph.add_component("C1", "capacitor", {"a": "vout", "b": "0"}, parameters={"capacitance_farads": 1e-7})
    return graph


def test_render_spice_netlist_is_deterministic_and_uses_m8_4_ir_only():
    netlist = build_renderable_rc_graph().to_netlist_ir()

    assert render_spice_netlist(netlist) == "\n".join(
        [
            "* rc_low_pass",
            "* metadata: stage=m8.5",
            "C1 vout 0 1e-07",
            "R1 vin vout 3183.1",
            "V1 vin 0 DC 0",
            ".end",
        ]
    )


@pytest.mark.parametrize("kind", ["diode"])
def test_render_spice_netlist_rejects_unsupported_component_kinds(kind: str) -> None:
    graph = CircuitGraph(name="demo")
    graph.add_node("0")
    graph.add_node("n1")
    graph.add_component("X1", kind, {"a": "n1", "b": "0"})

    with pytest.raises(SpiceRendererError, match="unsupported component kind"):
        render_spice_netlist(graph.to_netlist_ir())


def test_render_spice_netlist_renders_bjt_components() -> None:
    graph = CircuitGraph(name="demo")
    graph.add_node("0")
    graph.add_node("vc")
    graph.add_node("vb")
    graph.add_node("ve")
    graph.add_component(
        "Q1",
        "bjt",
        {"collector": "vc", "base": "vb", "emitter": "ve"},
        metadata={"model": "generic_npn"},
    )

    assert render_spice_netlist(graph.to_netlist_ir()) == "\n".join(
        [
            "* demo",
            "Q1 vc vb ve generic_npn",
            ".end",
        ]
    )


def test_render_spice_netlist_rejects_missing_required_parameters() -> None:
    graph = CircuitGraph(name="demo")
    graph.add_node("0")
    graph.add_node("n1")
    graph.add_component("R1", "resistor", {"a": "n1", "b": "0"})

    with pytest.raises(SpiceRendererError, match="required parameter"):
        render_spice_netlist(graph.to_netlist_ir())


def test_render_spice_netlist_rejects_unsupported_metadata_values() -> None:
    graph = CircuitGraph(name="demo", metadata={"tags": {"unsafe"}})
    graph.add_node("0")
    graph.add_node("n1")
    graph.add_component("R1", "resistor", {"a": "n1", "b": "0"}, parameters={"resistance_ohms": 1})

    with pytest.raises(SpiceRendererError, match="unsupported metadata value"):
        render_spice_netlist(graph.to_netlist_ir())


def test_render_spice_netlist_rejects_ac_phase_without_ac_magnitude() -> None:
    graph = CircuitGraph(name="demo")
    graph.add_node("0")
    graph.add_node("n1")
    graph.add_component(
        "V1",
        "voltage_source",
        {"positive": "n1", "negative": "0"},
        parameters={"dc_volts": 0, "ac_phase_deg": 45},
    )

    with pytest.raises(SpiceRendererError, match="ac_phase_deg without ac_magnitude"):
        render_spice_netlist(graph.to_netlist_ir())
