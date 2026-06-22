from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from math import isfinite
from typing import Any

from ...core import (
    CircuitGraph,
    CircuitGraphError,
    RegistryContract,
    RegistryDescriptor,
    build_resistor,
    ensure_ground_node,
    ensure_node,
)

__all__ = [
    "RESISTIVE_DIVIDER_BLOCK",
    "ResistiveDividerTopologyBlock",
    "build_resistive_divider",
]


BLOCK_IDENTIFIER = "resistive_divider"
BLOCK_VERSION = "m8.8"
BLOCK_CATEGORY = "passive_networks"
BLOCK_MATURITY = "mvp"
BLOCK_ARCHETYPE_ID = "resistive_divider_vertical_slice"


@dataclass(frozen=True, slots=True)
class ResistiveDividerTopologyBlock:
    identifier: str = BLOCK_IDENTIFIER
    version: str = BLOCK_VERSION
    category: str = BLOCK_CATEGORY
    maturity: str = BLOCK_MATURITY
    ports: tuple[str, ...] = ("vin", "vout", "gnd")
    parameters: tuple[str, ...] = ("resistance_top_ohms", "resistance_bottom_ohms")
    supported_analyses: tuple[str, ...] = ("dc",)
    metrics: tuple[str, ...] = ("divider_ratio", "thevenin_resistance_ohms")
    failure_modes: tuple[str, ...] = ("invalid_resistance_values", "invalid_node_tokens")
    caveat_tags: tuple[str, ...] = ("ideal_passive", "unloaded_output")
    generated_subgraph: tuple[str, ...] = ("vin", "R1", "vout", "R2", "gnd")

    @property
    def summary(self) -> str:
        return "Isolated unloaded resistive-divider topology block MVP"

    def to_registry_descriptor(self) -> RegistryDescriptor:
        return RegistryDescriptor(
            kind="topology_block",
            identifier=self.identifier,
            summary=self.summary,
            version=self.version,
            metadata={
                "category": self.category,
                "caveat_tags": list(self.caveat_tags),
                "failure_modes": list(self.failure_modes),
                "generated_subgraph": list(self.generated_subgraph),
                "metrics": list(self.metrics),
                "maturity": self.maturity,
                "parameters": list(self.parameters),
                "ports": list(self.ports),
                "supported_analyses": list(self.supported_analyses),
            },
        )

    def register(self, registry: RegistryContract) -> RegistryDescriptor:
        return registry.register(self.to_registry_descriptor())

    def build(
        self,
        *,
        resistance_top_ohms: float,
        resistance_bottom_ohms: float,
        vin: str,
        vout: str,
        gnd: str = "0",
        graph_name: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> CircuitGraph:
        return build_resistive_divider(
            resistance_top_ohms=resistance_top_ohms,
            resistance_bottom_ohms=resistance_bottom_ohms,
            vin=vin,
            vout=vout,
            gnd=gnd,
            graph_name=graph_name,
            metadata=metadata,
        )


RESISTIVE_DIVIDER_BLOCK = ResistiveDividerTopologyBlock()


def build_resistive_divider(
    *,
    resistance_top_ohms: float,
    resistance_bottom_ohms: float,
    vin: str,
    vout: str,
    gnd: str = "0",
    graph_name: str | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> CircuitGraph:
    """Build an unloaded resistive divider as a deterministic passive CircuitGraph."""

    _validate_token("node name", vin)
    _validate_token("node name", vout)
    _validate_token("ground node name", gnd)
    if vin == vout:
        raise CircuitGraphError("vin and vout must refer to different nodes")
    if vin == gnd or vout == gnd:
        raise CircuitGraphError("signal nodes must not reuse the ground node")

    resistance_top_ohms = _validate_positive_finite(
        "resistance_top_ohms", resistance_top_ohms
    )
    resistance_bottom_ohms = _validate_positive_finite(
        "resistance_bottom_ohms", resistance_bottom_ohms
    )
    if resistance_top_ohms <= resistance_bottom_ohms:
        divider_ratio = 1.0 / (1.0 + resistance_top_ohms / resistance_bottom_ohms)
    else:
        resistance_ratio = resistance_bottom_ohms / resistance_top_ohms
        divider_ratio = resistance_ratio / (1.0 + resistance_ratio)

    smaller_resistance = min(resistance_top_ohms, resistance_bottom_ohms)
    larger_resistance = max(resistance_top_ohms, resistance_bottom_ohms)
    thevenin_resistance_ohms = smaller_resistance / (
        1.0 + smaller_resistance / larger_resistance
    )

    block_metadata = {
        "archetype_id": BLOCK_ARCHETYPE_ID,
        "block": BLOCK_IDENTIFIER,
        "capability_id": BLOCK_IDENTIFIER,
        "capability_version": BLOCK_VERSION,
        "category": BLOCK_CATEGORY,
        "divider_ratio": divider_ratio,
        "maturity": BLOCK_MATURITY,
        "resistance_bottom_ohms": resistance_bottom_ohms,
        "resistance_top_ohms": resistance_top_ohms,
        "thevenin_resistance_ohms": thevenin_resistance_ohms,
        "version": BLOCK_VERSION,
    }
    if metadata is not None:
        _validate_metadata("block metadata", metadata)
        block_metadata = {**metadata, **block_metadata}

    if graph_name is not None:
        _validate_token("graph name", graph_name)

    capability_metadata = {
        "artifact_manifest": {
            "netlist": "circuit.net",
            "report": "report.md",
            "visual_report_data": "visual_report_data.json",
        },
        "archetype_id": BLOCK_ARCHETYPE_ID,
        "capability_id": BLOCK_IDENTIFIER,
        "capability_version": BLOCK_VERSION,
        "category": BLOCK_CATEGORY,
        "maturity": BLOCK_MATURITY,
        "ports": ["VIN", "VOUT", "GND"],
        "probes": ["vin_voltage", "vout_voltage", "divider_ratio"],
        "supported_analyses": ["dc"],
    }
    archetype_metadata = {
        "archetype_family": "vertical_slice",
        "archetype_id": BLOCK_ARCHETYPE_ID,
        "ports": ["VIN", "VOUT", "GND"],
        "topology": "series_resistor_shunt_resistor",
    }

    graph = CircuitGraph(
        name=graph_name or BLOCK_IDENTIFIER,
        metadata=block_metadata,
        capability_metadata=capability_metadata,
        archetype_metadata=archetype_metadata,
    )
    ensure_ground_node(graph, gnd)
    ensure_node(graph, vin)
    ensure_node(graph, vout)

    build_resistor(
        graph,
        "R1",
        vin,
        vout,
        resistance_top_ohms,
        metadata={"block": BLOCK_IDENTIFIER, "role": "upper"},
    )
    build_resistor(
        graph,
        "R2",
        vout,
        gnd,
        resistance_bottom_ohms,
        metadata={"block": BLOCK_IDENTIFIER, "role": "lower"},
    )
    graph.add_port("VIN", vin, role="input", metadata={"signal": "input"})
    graph.add_port("VOUT", vout, role="output", metadata={"signal": "output"})
    graph.add_port("GND", gnd, role="ground", metadata={"signal": "reference"})
    graph.add_probe("vin_voltage", kind="voltage", target=vin, metadata={"port": "VIN"})
    graph.add_probe("vout_voltage", kind="voltage", target=vout, metadata={"port": "VOUT"})
    graph.add_probe(
        "divider_ratio",
        kind="ratio",
        target=vout,
        metadata={"from": "VIN", "to": "VOUT"},
    )
    graph.add_analysis("dc", kind="dc", parameters={}, metadata={"domain": "bias"})
    graph.validate_resistive_divider_topology()
    graph.validate_artifact_consistency()
    return graph


def _validate_token(label: str, value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CircuitGraphError(f"{label} must be a non-empty string")
    if value != value.strip():
        raise CircuitGraphError(f"{label} must not contain leading or trailing whitespace: {value!r}")
    if any(character.isspace() for character in value):
        raise CircuitGraphError(f"{label} must not contain whitespace: {value!r}")
    return value


def _validate_positive_finite(label: str, value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CircuitGraphError(f"parameter {label!r} must be a finite numeric value")
    numeric_value = float(value)
    if not isfinite(numeric_value):
        raise CircuitGraphError(f"parameter {label!r} must be finite")
    if numeric_value <= 0:
        raise CircuitGraphError(f"parameter {label!r} must be greater than zero")
    return numeric_value


def _validate_metadata(label: str, value: Mapping[str, Any]) -> None:
    if not isinstance(value, Mapping):
        raise CircuitGraphError(f"{label} must be a mapping or None")
    for key, item in value.items():
        _validate_token(f"{label} key", key)
        _validate_renderer_safe_value(f"{label}.{key}", item)


def _validate_renderer_safe_value(label: str, value: Any) -> None:
    if value is None or isinstance(value, (str, int, float, bool)):
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            _validate_token(f"{label} key", key)
            _validate_renderer_safe_value(f"{label}.{key}", item)
        return
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _validate_renderer_safe_value(f"{label}[{index}]", item)
        return
    raise CircuitGraphError(f"{label} contains a renderer-unsafe value: {value!r}")
