from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping
import copy
import json

from .circuit_graph import CircuitComponent, CircuitGraph, CircuitGraphError, CircuitPort, _freeze_mapping, _sorted_mapping

__all__ = [
    "SchematicComponentLayout",
    "SchematicLayout",
    "SchematicLayoutCheck",
    "SchematicNodeLayout",
    "SchematicPortLayout",
    "SchematicTerminalLayout",
    "SchematicTextLabel",
    "SchematicWireSegment",
    "build_series_resistor_shunt_capacitor_schematic_layout",
    "build_rc_low_pass_schematic_layout",
]


@dataclass(frozen=True, slots=True)
class SchematicLayoutCheck:
    name: str
    passed: bool
    message: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _validate_token("layout check name", self.name)
        if not isinstance(self.message, str) or not self.message.strip():
            raise CircuitGraphError("layout check message must be a non-empty string")
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "passed": self.passed,
            "message": self.message,
            "metadata": _sorted_mapping(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class SchematicNodeLayout:
    node_id: str
    net: str
    x: float
    y: float
    role: str = "junction"
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _validate_token("layout node id", self.node_id)
        _validate_token("layout node net", self.net)
        _validate_token("layout node role", self.role)
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "net": self.net,
            "x": self.x,
            "y": self.y,
            "role": self.role,
            "metadata": _sorted_mapping(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class SchematicPortLayout:
    name: str
    net: str
    x: float
    y: float
    side: str
    role: str = "signal"
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _validate_token("layout port name", self.name)
        _validate_token("layout port net", self.net)
        _validate_token("layout port side", self.side)
        _validate_token("layout port role", self.role)
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "net": self.net,
            "x": self.x,
            "y": self.y,
            "side": self.side,
            "role": self.role,
            "metadata": _sorted_mapping(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class SchematicTerminalLayout:
    name: str
    net: str
    x: float
    y: float
    side: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _validate_token("layout terminal name", self.name)
        _validate_token("layout terminal net", self.net)
        _validate_token("layout terminal side", self.side)
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "net": self.net,
            "x": self.x,
            "y": self.y,
            "side": self.side,
            "metadata": _sorted_mapping(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class SchematicComponentLayout:
    refdes: str
    kind: str
    symbol: str
    x: float
    y: float
    width: float
    height: float
    terminals: tuple[SchematicTerminalLayout, ...]
    label_anchor: str = "top"
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _validate_token("layout component refdes", self.refdes)
        _validate_token("layout component kind", self.kind)
        _validate_token("layout component symbol", self.symbol)
        _validate_token("layout component label_anchor", self.label_anchor)
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        return {
            "refdes": self.refdes,
            "kind": self.kind,
            "symbol": self.symbol,
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
            "terminals": [terminal.to_dict() for terminal in self.terminals],
            "label_anchor": self.label_anchor,
            "metadata": _sorted_mapping(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class SchematicWireSegment:
    wire_id: str
    net: str
    x1: float
    y1: float
    x2: float
    y2: float
    role: str = "signal"
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _validate_token("layout wire id", self.wire_id)
        _validate_token("layout wire net", self.net)
        _validate_token("layout wire role", self.role)
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        return {
            "wire_id": self.wire_id,
            "net": self.net,
            "x1": self.x1,
            "y1": self.y1,
            "x2": self.x2,
            "y2": self.y2,
            "role": self.role,
            "metadata": _sorted_mapping(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class SchematicTextLabel:
    text: str
    x: float
    y: float
    anchor: str = "start"
    role: str = "annotation"
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.text, str) or not self.text.strip():
            raise CircuitGraphError("layout text label must be a non-empty string")
        _validate_token("layout text label anchor", self.anchor)
        _validate_token("layout text label role", self.role)
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "x": self.x,
            "y": self.y,
            "anchor": self.anchor,
            "role": self.role,
            "metadata": _sorted_mapping(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class SchematicLayout:
    layout_id: str
    source_circuit_graph_id: str
    nodes: tuple[SchematicNodeLayout, ...]
    component_instances: tuple[SchematicComponentLayout, ...]
    wires: tuple[SchematicWireSegment, ...]
    labels: tuple[SchematicTextLabel, ...]
    ports: tuple[SchematicPortLayout, ...]
    checks: tuple[SchematicLayoutCheck, ...]
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _validate_token("layout id", self.layout_id)
        _validate_token("source circuit graph id", self.source_circuit_graph_id)
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        return {
            "layout_id": self.layout_id,
            "source_circuit_graph_id": self.source_circuit_graph_id,
            "nodes": [node.to_dict() for node in self.nodes],
            "component_instances": [component.to_dict() for component in self.component_instances],
            "wires": [wire.to_dict() for wire in self.wires],
            "labels": [label.to_dict() for label in self.labels],
            "ports": [port.to_dict() for port in self.ports],
            "checks": [check.to_dict() for check in self.checks],
            "metadata": _sorted_mapping(self.metadata),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


_RC_INPUT_NET = "vin"
_RC_OUTPUT_NET = "vout"
_RC_GROUND_NET = "0"
_SERIES_SHUNT_TOPOLOGY = "series_resistor_shunt_capacitor"


def build_series_resistor_shunt_capacitor_schematic_layout(graph: CircuitGraph) -> SchematicLayout:
    """Build a deterministic schematic layout IR for a series resistor + shunt capacitor graph."""

    graph.validate_integrity()

    topology = graph.archetype_metadata.get("topology")
    if topology != _SERIES_SHUNT_TOPOLOGY:
        raise CircuitGraphError(
            "shared schematic layout builder requires series_resistor_shunt_capacitor archetype metadata"
        )

    port_by_role = {port.role: port for port in graph.list_ports()}
    required_roles = {"input", "output", "ground"}
    if set(port_by_role) != required_roles:
        raise CircuitGraphError("shared schematic layout requires input, output, and ground ports")

    input_port = port_by_role["input"]
    output_port = port_by_role["output"]
    ground_port = port_by_role["ground"]

    series_component = _select_single_component(graph, kind="resistor", preferred_role="series", preferred_refdes="R1")
    shunt_component = _select_single_component(graph, kind="capacitor", preferred_role="shunt", preferred_refdes="C1")

    resistor_value = float(series_component.parameters["resistance_ohms"])
    capacitor_value = float(shunt_component.parameters["capacitance_farads"])
    cutoff_hz = float(graph.metadata.get("cutoff_frequency_hz", 0.0) or 0.0)
    input_frequency_hz = float(graph.metadata.get("input_frequency_hz", cutoff_hz or 0.0) or (cutoff_hz or 0.0))

    input_node = SchematicNodeLayout(
        node_id=f"{input_port.net}_node",
        net=input_port.net,
        x=90.0,
        y=210.0,
        role="input",
        metadata={"port": input_port.name},
    )
    output_node = SchematicNodeLayout(
        node_id=f"{output_port.net}_node",
        net=output_port.net,
        x=560.0,
        y=210.0,
        role="output",
        metadata={"port": output_port.name},
    )
    ground_node = SchematicNodeLayout(
        node_id=f"{ground_port.net}_node",
        net=ground_port.net,
        x=560.0,
        y=350.0,
        role="ground",
        metadata={"port": ground_port.name},
    )

    component_instances = (
        SchematicComponentLayout(
            refdes=series_component.refdes,
            kind=series_component.kind,
            symbol="resistor",
            x=180.0,
            y=180.0,
            width=210.0,
            height=60.0,
            terminals=(
                SchematicTerminalLayout(name="a", net=input_port.net, x=180.0, y=210.0, side="left", metadata={"role": "series-in"}),
                SchematicTerminalLayout(name="b", net=output_port.net, x=390.0, y=210.0, side="right", metadata={"role": "series-out"}),
            ),
            label_anchor="top",
            metadata={"role": series_component.metadata.get("role", "series")},
        ),
        SchematicComponentLayout(
            refdes=shunt_component.refdes,
            kind=shunt_component.kind,
            symbol="capacitor",
            x=530.0,
            y=260.0,
            width=60.0,
            height=90.0,
            terminals=(
                SchematicTerminalLayout(name="a", net=output_port.net, x=560.0, y=280.0, side="top", metadata={"role": "shunt-in"}),
                SchematicTerminalLayout(name="b", net=ground_port.net, x=560.0, y=350.0, side="bottom", metadata={"role": "reference"}),
            ),
            label_anchor="right",
            metadata={"role": shunt_component.metadata.get("role", "shunt")},
        ),
    )

    ports = (
        SchematicPortLayout(name=input_port.name, net=input_port.net, x=90.0, y=210.0, side="left", role=input_port.role, metadata=input_port.metadata),
        SchematicPortLayout(name=output_port.name, net=output_port.net, x=980.0, y=210.0, side="right", role=output_port.role, metadata=output_port.metadata),
        SchematicPortLayout(name=ground_port.name, net=ground_port.net, x=560.0, y=350.0, side="bottom", role=ground_port.role, metadata=ground_port.metadata),
    )

    wires = (
        SchematicWireSegment(wire_id=f"{input_port.net}_to_{series_component.refdes.lower()}", net=input_port.net, x1=90.0, y1=210.0, x2=180.0, y2=210.0, role="signal", metadata={"from": input_port.name, "to": f"{series_component.refdes}.a"}),
        SchematicWireSegment(wire_id=f"{series_component.refdes.lower()}_to_{output_port.net}", net=output_port.net, x1=390.0, y1=210.0, x2=560.0, y2=210.0, role="signal", metadata={"from": f"{series_component.refdes}.b", "to": f"{shunt_component.refdes}.a"}),
        SchematicWireSegment(wire_id=f"{output_port.net}_to_{shunt_component.refdes.lower()}", net=output_port.net, x1=560.0, y1=210.0, x2=560.0, y2=280.0, role="signal", metadata={"from": output_port.name, "to": f"{shunt_component.refdes}.a"}),
        SchematicWireSegment(wire_id=f"{output_port.net}_to_port", net=output_port.net, x1=560.0, y1=210.0, x2=980.0, y2=210.0, role="signal", metadata={"from": f"{shunt_component.refdes}.a", "to": output_port.name}),
        SchematicWireSegment(wire_id=f"{shunt_component.refdes.lower()}_to_{ground_port.name.lower()}", net=ground_port.net, x1=560.0, y1=280.0, x2=560.0, y2=350.0, role="reference", metadata={"from": f"{shunt_component.refdes}.b", "to": ground_port.name}),
    )

    labels = (
        SchematicTextLabel(text=input_port.name, x=24.0, y=132.0, anchor="start", role="port-label", metadata={"port": input_port.name}),
        SchematicTextLabel(text=f"{input_port.name} port", x=24.0, y=150.0, anchor="start", role="annotation", metadata={"port": input_port.name}),
        SchematicTextLabel(text=series_component.refdes, x=220.0, y=132.0, anchor="start", role="designator", metadata={"component": series_component.refdes}),
        SchematicTextLabel(text=_format_resistance(resistor_value), x=220.0, y=150.0, anchor="start", role="value", metadata={"component": series_component.refdes, "unit": "ohm"}),
        SchematicTextLabel(text=shunt_component.refdes, x=620.0, y=170.0, anchor="start", role="designator", metadata={"component": shunt_component.refdes}),
        SchematicTextLabel(text=_format_capacitance(capacitor_value), x=620.0, y=188.0, anchor="start", role="value", metadata={"component": shunt_component.refdes, "unit": "farad"}),
        SchematicTextLabel(text=output_port.name, x=832.0, y=132.0, anchor="start", role="port-label", metadata={"port": output_port.name}),
        SchematicTextLabel(text=f"{output_port.name} port", x=832.0, y=150.0, anchor="start", role="annotation", metadata={"port": output_port.name}),
        SchematicTextLabel(text=ground_port.name, x=438.0, y=318.0, anchor="end", role="port-label", metadata={"port": ground_port.name}),
        SchematicTextLabel(text="Reference", x=438.0, y=336.0, anchor="end", role="annotation", metadata={"port": ground_port.name}),
        SchematicTextLabel(
            text=f"Signal flow: {input_port.name} → {series_component.refdes} → {output_port.name} · {shunt_component.refdes} shunts the output node to {ground_port.name}",
            x=34.0,
            y=428.0,
            anchor="start",
            role="note",
            metadata={"source": "topology_layout_strategy"},
        ),
        SchematicTextLabel(
            text=f"{series_component.refdes} {_format_resistance(resistor_value)} · {shunt_component.refdes} {_format_capacitance(capacitor_value)} · fc {_format_frequency(cutoff_hz)} · input {_format_frequency(input_frequency_hz)} · {_SERIES_SHUNT_TOPOLOGY}",
            x=34.0,
            y=452.0,
            anchor="start",
            role="note",
            metadata={"source": "topology_layout_strategy"},
        ),
    )

    checks = (
        _check_net_equivalence(
            "output_layout_net_matches_series_and_shunt_connection",
            output_port.net == series_component.terminals["b"] == shunt_component.terminals["a"],
            "output layout net matches the series component output and shunt component input",
            {
                "layout_net": output_port.net,
                "series_b": series_component.terminals["b"],
                "shunt_a": shunt_component.terminals["a"],
            },
        ),
        _check_net_equivalence(
            "ground_layout_net_matches_shunt_and_ground_port",
            ground_port.net == shunt_component.terminals["b"] and ground_port.net == ground_port.net,
            "ground layout net matches the shunt component return and ground port",
            {
                "layout_net": ground_port.net,
                "shunt_b": shunt_component.terminals["b"],
                "ground_port_net": ground_port.net,
            },
        ),
        _check_net_equivalence(
            "input_and_ground_layout_nets_remain_distinct",
            input_port.net != ground_port.net,
            "input and ground layout nets remain distinct unless the graph says otherwise",
            {
                "input_net": input_port.net,
                "ground_net": ground_port.net,
            },
        ),
        _check_net_equivalence(
            "topology_strategy_is_series_then_shunt_to_ground",
            True,
            "Layout strategy uses the canonical series_then_shunt_to_ground motif",
            {"strategy": "series_then_shunt_to_ground", "topology": topology},
        ),
    )

    return SchematicLayout(
        layout_id=f"{graph.name}_schematic_layout",
        source_circuit_graph_id=graph.name,
        nodes=(input_node, output_node, ground_node),
        component_instances=component_instances,
        wires=wires,
        labels=labels,
        ports=ports,
        checks=checks,
        metadata={
            "archetype_id": graph.archetype_metadata.get("archetype_id", ""),
            "capability_id": graph.capability_metadata.get("capability_id", ""),
            "layout_strategy": "series_then_shunt_to_ground",
        },
    )


def build_rc_low_pass_schematic_layout(graph: CircuitGraph) -> SchematicLayout:
    """Build a deterministic schematic layout IR for the validated RC low-pass graph."""

    graph.validate_rc_low_pass_topology()
    return build_series_resistor_shunt_capacitor_schematic_layout(graph)


def _check_net_equivalence(name: str, passed: bool, message: str, metadata: Mapping[str, Any]) -> SchematicLayoutCheck:
    return SchematicLayoutCheck(name=name, passed=passed, message=message, metadata=metadata)


def _select_single_component(
    graph: CircuitGraph,
    *,
    kind: str,
    preferred_role: str,
    preferred_refdes: str,
) -> CircuitComponent:
    candidates = [component for component in graph.list_components() if component.kind == kind]
    if not candidates:
        raise CircuitGraphError(f"shared schematic layout requires a {kind} component")

    for component in candidates:
        if component.refdes == preferred_refdes:
            return component

    role_matches = [component for component in candidates if component.metadata.get("role") == preferred_role]
    if len(role_matches) == 1:
        return role_matches[0]
    if len(role_matches) > 1:
        raise CircuitGraphError(f"shared schematic layout found multiple {preferred_role} {kind} components")

    if len(candidates) == 1:
        return candidates[0]

    raise CircuitGraphError(f"shared schematic layout could not uniquely identify the {preferred_role} {kind}")


def _format_resistance(value: float) -> str:
    if value >= 1_000_000:
        return f"{value / 1_000_000:g} MΩ"
    if value >= 1_000:
        return f"{value / 1_000:g} kΩ"
    return f"{value:g} Ω"


def _format_capacitance(value: float) -> str:
    if value >= 1e-6:
        return f"{value / 1e-6:g} µF"
    if value >= 1e-9:
        return f"{value / 1e-9:g} nF"
    if value >= 1e-12:
        return f"{value / 1e-12:g} pF"
    return f"{value:g} F"


def _format_frequency(value: float) -> str:
    if value >= 1_000_000:
        return f"{value / 1_000_000:g} MHz"
    if value >= 1_000:
        return f"{value / 1_000:g} kHz"
    if value >= 1:
        return f"{value:g} Hz"
    if value >= 1e-3:
        return f"{value / 1e-3:g} mHz"
    return f"{value:g} Hz"


def _validate_token(label: str, value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CircuitGraphError(f"{label} must be a non-empty string")
    if value != value.strip():
        raise CircuitGraphError(f"{label} must not contain leading or trailing whitespace: {value!r}")
    if any(character.isspace() for character in value):
        raise CircuitGraphError(f"{label} must not contain whitespace: {value!r}")
    return value
