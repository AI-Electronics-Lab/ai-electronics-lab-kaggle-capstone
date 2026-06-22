from __future__ import annotations

from ai_electronics_lab.simulation.blocks.filters import build_rc_low_pass
from ai_electronics_lab.simulation.core import (
    CircuitGraph,
    SchematicComponentLayout,
    SchematicLayout,
    SchematicLayoutCheck,
    SchematicNodeLayout,
    SchematicPortLayout,
    SchematicTerminalLayout,
    SchematicTextLabel,
    SchematicWireSegment,
    build_rc_low_pass_schematic_layout,
    build_series_resistor_shunt_capacitor_schematic_layout,
    render_schematic_svg,
)


def test_rc_schematic_renderer_uses_layout_ir_and_is_deterministic():
    graph = build_rc_low_pass(
        resistance_ohms=1_000,
        capacitance_farads=1e-6,
        vin="vin",
        vout="vout",
        metadata={"cutoff_frequency_hz": 1_000.0, "input_frequency_hz": 1_000.0},
    )
    layout = build_rc_low_pass_schematic_layout(graph)

    svg = render_schematic_svg(layout)

    assert svg.startswith("<svg")
    assert "RC low-pass schematic" in svg
    assert "series_then_shunt_to_ground" in svg
    assert "Signal flow: VIN → R1 → VOUT" in svg
    assert "data-wire-id='vin_to_r1'" in svg
    assert "data-wire-id='c1_to_gnd'" in svg
    assert "VIN" in svg and "VOUT" in svg and "GND" in svg
    assert "data-layout-id=\"rc_low_pass_schematic_layout\"" in svg
    assert "data-source-graph-id=\"rc_low_pass\"" in svg
    assert "<metadata id='schematic-layout-metadata'>" in svg
    assert "\"source_circuit_graph_id\":\"rc_low_pass\"" in svg
    assert "class=\"ground-symbol\"" in svg
    assert render_schematic_svg(layout) == svg


def test_schematic_renderer_supports_voltage_source_ground_and_probe_symbols():
    layout = SchematicLayout(
        layout_id="demo_layout",
        source_circuit_graph_id="demo_graph",
        nodes=(
            SchematicNodeLayout(node_id="vin_node", net="vin", x=90.0, y=150.0, role="input"),
            SchematicNodeLayout(node_id="gnd_node", net="0", x=210.0, y=250.0, role="ground"),
        ),
        component_instances=(
            SchematicComponentLayout(
                refdes="V1",
                kind="source",
                symbol="voltage_source",
                x=80.0,
                y=100.0,
                width=120.0,
                height=160.0,
                terminals=(
                    SchematicTerminalLayout(name="p", net="vin", x=140.0, y=110.0, side="top"),
                    SchematicTerminalLayout(name="n", net="0", x=140.0, y=250.0, side="bottom"),
                ),
                label_anchor="top",
            ),
        ),
        wires=(
            SchematicWireSegment(wire_id="vin_lead", net="vin", x1=90.0, y1=150.0, x2=140.0, y2=110.0, role="signal"),
            SchematicWireSegment(wire_id="gnd_lead", net="0", x1=140.0, y1=250.0, x2=210.0, y2=250.0, role="reference"),
        ),
        labels=(
            SchematicTextLabel(text="V1", x=96.0, y=92.0, anchor="start", role="designator", metadata={"component": "V1"}),
            SchematicTextLabel(text="1 V", x=96.0, y=110.0, anchor="start", role="value", metadata={"component": "V1"}),
        ),
        ports=(
            SchematicPortLayout(name="VIN", net="vin", x=90.0, y=150.0, side="left", role="input"),
            SchematicPortLayout(name="GND", net="0", x=210.0, y=250.0, side="bottom", role="ground"),
            SchematicPortLayout(name="PROBE", net="vin", x=270.0, y=150.0, side="probe", role="probe"),
        ),
        checks=(SchematicLayoutCheck(name="demo", passed=True, message="demo layout is valid"),),
        metadata={"layout_strategy": "demo"},
    )

    svg = render_schematic_svg(layout)

    assert "voltage-source-symbol" in svg
    assert "ground-symbol" in svg
    assert "probe-symbol" in svg
    assert "data-layout-id=\"demo_layout\"" in svg
    assert "\"layout_id\":\"demo_layout\"" in svg


def test_schematic_renderer_suppresses_leader_lines_for_footer_notes():
    layout = SchematicLayout(
        layout_id="note_layout",
        source_circuit_graph_id="demo_graph",
        nodes=(),
        component_instances=(),
        wires=(),
        labels=(
            SchematicTextLabel(text="Footer note", x=34.0, y=428.0, anchor="start", role="note"),
        ),
        ports=(),
        checks=(),
        metadata={"layout_strategy": "demo"},
    )

    svg = render_schematic_svg(layout)

    assert "Footer note" in svg
    assert "annotation-leader" not in svg


def test_shared_series_shunt_layout_renders_outside_the_rc_block():
    graph = CircuitGraph(
        name="demo_series_shunt_render",
        metadata={"cutoff_frequency_hz": 250.0, "input_frequency_hz": 1_000.0},
        capability_metadata={"capability_id": "demo_series_shunt", "category": "demo"},
        archetype_metadata={"archetype_id": "demo_series_shunt", "topology": "series_resistor_shunt_capacitor"},
    )
    for node_name in ("vin", "vout", "0"):
        graph.add_node(node_name)
    graph.add_component("R1", "resistor", {"a": "vin", "b": "vout"}, parameters={"resistance_ohms": 1000.0}, metadata={"role": "series"})
    graph.add_component("C1", "capacitor", {"a": "vout", "b": "0"}, parameters={"capacitance_farads": 1e-6}, metadata={"role": "shunt"})
    graph.add_port("VIN", "vin", role="input")
    graph.add_port("VOUT", "vout", role="output")
    graph.add_port("GND", "0", role="ground")

    svg = render_schematic_svg(build_series_resistor_shunt_capacitor_schematic_layout(graph))

    assert svg.startswith("<svg")
    assert "demo_series_shunt_render" in svg
    assert "Signal flow: VIN → R1 → VOUT · C1 shunts the output node to GND" in svg
    assert "data-wire-id='vout_to_c1'" in svg
    assert "series_then_shunt_to_ground" in svg
