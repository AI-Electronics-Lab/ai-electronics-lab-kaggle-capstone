from __future__ import annotations

import pytest

from ai_electronics_lab.simulation.core import CircuitGraph, CircuitGraphError
from ai_electronics_lab.simulation.core.primitive_builders import (
    build_ac_voltage_source,
    build_bjt,
    build_capacitor,
    build_dc_current_source,
    build_dc_voltage_source,
    build_inductor,
    build_resistor,
    build_sine_voltage_source,
    ensure_ground_node,
)
from ai_electronics_lab.simulation.core.spice_renderer import render_spice_netlist


def test_primitive_builders_add_nodes_and_render_supported_primitives_deterministically():
    graph = CircuitGraph(name="primitive_demo", metadata={"stage": "m8.6"})

    ensure_ground_node(graph)
    build_dc_voltage_source(graph, "V1", "vin", "0", 5)
    build_sine_voltage_source(graph, "V2", "drive", "0", 1.0, 2.0, 1000.0, phase_deg=45.0)
    build_resistor(graph, "R1", "vin", "vout", 1000)
    build_capacitor(graph, "C1", "vout", "0", 1e-6)
    build_inductor(graph, "L1", "vout", "drive", 2.5e-3)

    assert [node.name for node in graph.list_nodes()] == ["0", "drive", "vin", "vout"]
    assert [component.refdes for component in graph.list_components()] == ["C1", "L1", "R1", "V1", "V2"]
    assert render_spice_netlist(graph.to_netlist_ir()) == "\n".join(
        [
            "* primitive_demo",
            "* metadata: stage=m8.6",
            "C1 vout 0 1e-06",
            "L1 vout drive 0.0025",
            "R1 vin vout 1000",
            "V1 vin 0 DC 5",
            "V2 drive 0 SINE(1 2 1000 45)",
            ".end",
        ]
    )


def test_dc_current_source_builder_renders_renderer_safe_output():
    graph = CircuitGraph(name="current_demo")

    build_dc_current_source(graph, "I1", "n1", "0", 0.001)

    assert render_spice_netlist(graph.to_netlist_ir()) == "\n".join(
        [
            "* current_demo",
            "I1 n1 0 DC 0.001",
            ".end",
        ]
    )


def test_ac_voltage_source_builder_renders_deterministically():
    graph = CircuitGraph(name="ac_source_demo")

    component = build_ac_voltage_source(graph, "V1", "vin", "0", 1.0, phase_deg=0.0)

    assert component.parameters == {"ac_magnitude": 1.0, "ac_phase_deg": 0.0}
    assert render_spice_netlist(graph.to_netlist_ir()) == "\n".join(
        ["* ac_source_demo", "V1 vin 0 AC 1 0", ".end"]
    )


@pytest.mark.parametrize("magnitude", [0, -1, True, float("nan"), float("inf")])
def test_ac_voltage_source_builder_rejects_invalid_magnitude(magnitude):
    graph = CircuitGraph(name="demo")

    with pytest.raises(CircuitGraphError):
        build_ac_voltage_source(graph, "V1", "vin", "0", magnitude)


@pytest.mark.parametrize("phase", [True, float("nan"), float("inf")])
def test_ac_voltage_source_builder_rejects_invalid_phase(phase):
    graph = CircuitGraph(name="demo")

    with pytest.raises(CircuitGraphError):
        build_ac_voltage_source(graph, "V1", "vin", "0", 1.0, phase_deg=phase)


def test_bjt_builder_renders_renderer_safe_output():
    graph = CircuitGraph(name="bjt_demo")

    ensure_ground_node(graph)
    graph.add_node("vc")
    graph.add_node("vb")
    graph.add_node("ve")
    build_bjt(graph, "Q1", "vc", "vb", "ve", "generic_npn", metadata={"role": "active_device"})

    assert render_spice_netlist(graph.to_netlist_ir()) == "\n".join(
        [
            "* bjt_demo",
            "Q1 vc vb ve generic_npn",
            ".end",
        ]
    )


@pytest.mark.parametrize("bad_refdes", ["R 1", " R1", "R1 "])
def test_primitive_builders_reject_whitespace_in_refdes(bad_refdes: str) -> None:
    graph = CircuitGraph(name="demo")

    with pytest.raises(CircuitGraphError, match="refdes"):
        build_resistor(graph, bad_refdes, "n1", "0", 1_000)


@pytest.mark.parametrize("bad_metadata", [{"tags": {"unsafe"}}, {"tags": ["ok", {"nested": {"bad"}}]}])
def test_primitive_builders_reject_renderer_unsafe_metadata(bad_metadata) -> None:
    graph = CircuitGraph(name="demo")

    with pytest.raises(CircuitGraphError, match="renderer-unsafe"):
        build_capacitor(graph, "C1", "n1", "0", 1e-6, metadata=bad_metadata)


@pytest.mark.parametrize(
    "builder_args",
    [
        (build_resistor, {"value": 0}),
        (build_capacitor, {"value": -1e-6}),
        (build_inductor, {"value": 0}),
    ],
)
def test_primitive_builders_reject_nonpositive_passive_values(builder_args) -> None:
    builder, kwargs = builder_args
    graph = CircuitGraph(name="demo")

    with pytest.raises(CircuitGraphError, match="greater than zero"):
        builder(graph, "X1", "n1", "0", kwargs["value"])
