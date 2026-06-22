from __future__ import annotations

from collections.abc import Mapping
from math import isfinite
from typing import Any

from .circuit_graph import CircuitComponent, CircuitGraph, CircuitGraphError, CircuitNode

__all__ = [
    "build_ac_voltage_source",
    "build_bjt",
    "build_capacitor",
    "build_dc_current_source",
    "build_dc_voltage_source",
    "build_inductor",
    "build_resistor",
    "build_sine_voltage_source",
    "ensure_ground_node",
    "ensure_node",
]


def ensure_node(graph: CircuitGraph, node_name: str, metadata: Mapping[str, Any] | None = None) -> CircuitNode:
    """Return an existing node or create a new one with validated metadata."""

    _validate_token("node name", node_name)
    normalized_metadata = _validate_metadata("node metadata", metadata)

    try:
        node = graph.get_node(node_name)
    except CircuitGraphError as exc:
        if "unknown node" not in str(exc):
            raise
        return graph.add_node(node_name, metadata=normalized_metadata)

    if metadata is not None and dict(node.metadata) != normalized_metadata:
        raise CircuitGraphError(f"node already exists with different metadata: {node_name!r}")
    return node


def ensure_ground_node(graph: CircuitGraph, node_name: str = "0", metadata: Mapping[str, Any] | None = None) -> CircuitNode:
    """Ensure the canonical ground/reference node exists."""

    return ensure_node(graph, node_name=node_name, metadata=metadata)


def build_resistor(
    graph: CircuitGraph,
    refdes: str,
    a: str,
    b: str,
    resistance_ohms: float,
    metadata: Mapping[str, Any] | None = None,
) -> CircuitComponent:
    """Add a deterministic resistor primitive to the graph."""

    return _build_component(
        graph=graph,
        refdes=refdes,
        kind="resistor",
        terminal_names=("a", "b"),
        node_names=(a, b),
        parameters={"resistance_ohms": resistance_ohms},
        metadata=metadata,
        positive_parameter_names=("resistance_ohms",),
    )


def build_capacitor(
    graph: CircuitGraph,
    refdes: str,
    a: str,
    b: str,
    capacitance_farads: float,
    metadata: Mapping[str, Any] | None = None,
) -> CircuitComponent:
    """Add a deterministic capacitor primitive to the graph."""

    return _build_component(
        graph=graph,
        refdes=refdes,
        kind="capacitor",
        terminal_names=("a", "b"),
        node_names=(a, b),
        parameters={"capacitance_farads": capacitance_farads},
        metadata=metadata,
        positive_parameter_names=("capacitance_farads",),
    )


def build_inductor(
    graph: CircuitGraph,
    refdes: str,
    a: str,
    b: str,
    inductance_henries: float,
    metadata: Mapping[str, Any] | None = None,
) -> CircuitComponent:
    """Add a deterministic inductor primitive to the graph."""

    return _build_component(
        graph=graph,
        refdes=refdes,
        kind="inductor",
        terminal_names=("a", "b"),
        node_names=(a, b),
        parameters={"inductance_henries": inductance_henries},
        metadata=metadata,
        positive_parameter_names=("inductance_henries",),
    )


def build_dc_voltage_source(
    graph: CircuitGraph,
    refdes: str,
    positive: str,
    negative: str,
    dc_volts: float,
    metadata: Mapping[str, Any] | None = None,
) -> CircuitComponent:
    """Add a deterministic DC voltage source primitive to the graph."""

    return _build_component(
        graph=graph,
        refdes=refdes,
        kind="voltage_source",
        terminal_names=("positive", "negative"),
        node_names=(positive, negative),
        parameters={"dc_volts": dc_volts},
        metadata=metadata,
        positive_parameter_names=(),
    )


def build_ac_voltage_source(
    graph: CircuitGraph,
    refdes: str,
    positive: str,
    negative: str,
    ac_magnitude: float,
    phase_deg: float = 0.0,
    metadata: Mapping[str, Any] | None = None,
) -> CircuitComponent:
    """Add a deterministic small-signal AC voltage source to the graph."""

    return _build_component(
        graph=graph,
        refdes=refdes,
        kind="voltage_source",
        terminal_names=("positive", "negative"),
        node_names=(positive, negative),
        parameters={"ac_magnitude": ac_magnitude, "ac_phase_deg": phase_deg},
        metadata=metadata,
        positive_parameter_names=("ac_magnitude",),
    )


def build_sine_voltage_source(
    graph: CircuitGraph,
    refdes: str,
    positive: str,
    negative: str,
    offset_volts: float,
    amplitude_volts: float,
    frequency_hz: float,
    phase_deg: float = 0.0,
    metadata: Mapping[str, Any] | None = None,
) -> CircuitComponent:
    """Add a deterministic sine-wave voltage source primitive to the graph."""

    return _build_component(
        graph=graph,
        refdes=refdes,
        kind="voltage_source",
        terminal_names=("positive", "negative"),
        node_names=(positive, negative),
        parameters={
            "sine_offset_volts": offset_volts,
            "sine_amplitude_volts": amplitude_volts,
            "sine_frequency_hz": frequency_hz,
            "sine_phase_deg": phase_deg,
        },
        metadata=metadata,
        positive_parameter_names=("sine_amplitude_volts", "sine_frequency_hz"),
    )


def build_dc_current_source(
    graph: CircuitGraph,
    refdes: str,
    positive: str,
    negative: str,
    dc_amps: float,
    metadata: Mapping[str, Any] | None = None,
) -> CircuitComponent:
    """Add a deterministic DC current source primitive to the graph."""

    return _build_component(
        graph=graph,
        refdes=refdes,
        kind="current_source",
        terminal_names=("positive", "negative"),
        node_names=(positive, negative),
        parameters={"dc_amps": dc_amps},
        metadata=metadata,
        positive_parameter_names=(),
    )


def build_bjt(
    graph: CircuitGraph,
    refdes: str,
    collector: str,
    base: str,
    emitter: str,
    model: str,
    metadata: Mapping[str, Any] | None = None,
) -> CircuitComponent:
    """Add a deterministic BJT primitive to the graph."""

    _validate_token("transistor model", model)
    normalized_metadata = _validate_metadata("component metadata", metadata)
    normalized_metadata = {**normalized_metadata, "model": model}
    return _build_component(
        graph=graph,
        refdes=refdes,
        kind="bjt",
        terminal_names=("collector", "base", "emitter"),
        node_names=(collector, base, emitter),
        parameters={},
        metadata=normalized_metadata,
        positive_parameter_names=(),
    )


def _build_component(
    *,
    graph: CircuitGraph,
    refdes: str,
    kind: str,
    terminal_names: tuple[str, ...],
    node_names: tuple[str, ...],
    parameters: Mapping[str, float | int | str],
    metadata: Mapping[str, Any] | None,
    positive_parameter_names: tuple[str, ...],
) -> CircuitComponent:
    _validate_token("component refdes", refdes)
    _validate_token("component kind", kind)
    normalized_metadata = _validate_metadata("component metadata", metadata)
    normalized_parameters = _validate_parameters(parameters, positive_parameter_names=positive_parameter_names)

    terminal_map = {}
    for terminal_name, node_name in zip(terminal_names, node_names, strict=True):
        _validate_token("terminal name", terminal_name)
        ensure_node(graph, node_name)
        terminal_map[terminal_name] = node_name

    return graph.add_component(
        refdes=refdes,
        kind=kind,
        terminals=terminal_map,
        parameters=normalized_parameters,
        metadata=normalized_metadata,
    )


def _validate_token(label: str, value: Any) -> None:
    if not isinstance(value, str) or not value.strip():
        raise CircuitGraphError(f"{label} must be a non-empty string")
    if value != value.strip():
        raise CircuitGraphError(f"{label} must not contain leading or trailing whitespace: {value!r}")
    if any(character.isspace() for character in value):
        raise CircuitGraphError(f"{label} must not contain whitespace: {value!r}")


def _validate_metadata(label: str, value: Mapping[str, Any] | None) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise CircuitGraphError(f"{label} must be a mapping or None")
    normalized: dict[str, Any] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not key.strip():
            raise CircuitGraphError(f"{label} keys must be non-empty strings")
        if key != key.strip() or any(character.isspace() for character in key):
            raise CircuitGraphError(f"{label} keys must not contain whitespace: {key!r}")
        _validate_renderer_safe_value(f"{label}.{key}", item)
        normalized[key] = item
    return normalized


def _validate_renderer_safe_value(label: str, value: Any) -> None:
    if value is None or isinstance(value, (str, int, float, bool)):
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str) or not key.strip():
                raise CircuitGraphError(f"{label} contains a non-string metadata key: {key!r}")
            if key != key.strip() or any(character.isspace() for character in key):
                raise CircuitGraphError(f"{label} contains whitespace in metadata key: {key!r}")
            _validate_renderer_safe_value(f"{label}.{key}", item)
        return
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _validate_renderer_safe_value(f"{label}[{index}]", item)
        return
    raise CircuitGraphError(f"{label} contains a renderer-unsafe value: {value!r}")


def _validate_parameters(
    parameters: Mapping[str, Any],
    *,
    positive_parameter_names: tuple[str, ...],
) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for key, value in parameters.items():
        if not isinstance(key, str) or not key.strip():
            raise CircuitGraphError("parameter names must be non-empty strings")
        if key != key.strip() or any(character.isspace() for character in key):
            raise CircuitGraphError(f"parameter names must not contain whitespace: {key!r}")
        _validate_numeric_parameter(key, value, positive=key in positive_parameter_names)
        normalized[key] = value
    return normalized


def _validate_numeric_parameter(name: str, value: Any, *, positive: bool) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CircuitGraphError(f"parameter {name!r} must be a finite numeric value")
    numeric_value = float(value)
    if not isfinite(numeric_value):
        raise CircuitGraphError(f"parameter {name!r} must be finite")
    if positive and numeric_value <= 0:
        raise CircuitGraphError(f"parameter {name!r} must be greater than zero")
