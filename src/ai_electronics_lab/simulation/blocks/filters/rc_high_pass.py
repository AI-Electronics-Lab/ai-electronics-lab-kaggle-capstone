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
    build_capacitor,
    build_resistor,
    ensure_ground_node,
    ensure_node,
)

__all__ = [
    "RC_HIGH_PASS_BLOCK",
    "RcHighPassTopologyBlock",
    "build_rc_high_pass",
]


BLOCK_IDENTIFIER = "rc_high_pass"
BLOCK_VERSION = "m8.8"
BLOCK_CATEGORY = "filters"
BLOCK_MATURITY = "mvp"
BLOCK_ARCHETYPE_ID = "rc_high_pass_vertical_slice"


@dataclass(frozen=True, slots=True)
class RcHighPassTopologyBlock:
    identifier: str = BLOCK_IDENTIFIER
    version: str = BLOCK_VERSION
    category: str = BLOCK_CATEGORY
    maturity: str = BLOCK_MATURITY
    ports: tuple[str, ...] = ("vin", "vout", "gnd")
    parameters: tuple[str, ...] = ("resistance_ohms", "capacitance_farads")
    supported_analyses: tuple[str, ...] = ("dc", "ac", "transient")
    metrics: tuple[str, ...] = ("cutoff_frequency_hz", "time_constant_s")
    failure_modes: tuple[str, ...] = ("invalid_rc_values", "invalid_node_tokens")
    caveat_tags: tuple[str, ...] = ("ideal_passive", "no_loading_accounted")
    generated_subgraph: tuple[str, ...] = ("vin", "C", "vout", "R", "gnd")

    @property
    def summary(self) -> str:
        return "Isolated RC high-pass topology block MVP"

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
        resistance_ohms: float,
        capacitance_farads: float,
        vin: str,
        vout: str,
        gnd: str = "0",
        graph_name: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> CircuitGraph:
        return build_rc_high_pass(
            resistance_ohms=resistance_ohms,
            capacitance_farads=capacitance_farads,
            vin=vin,
            vout=vout,
            gnd=gnd,
            graph_name=graph_name,
            metadata=metadata,
        )


RC_HIGH_PASS_BLOCK = RcHighPassTopologyBlock()


def build_rc_high_pass(
    *,
    resistance_ohms: float,
    capacitance_farads: float,
    vin: str,
    vout: str,
    gnd: str = "0",
    graph_name: str | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> CircuitGraph:
    """Build the isolated rc_high_pass topology block as a deterministic CircuitGraph."""

    _validate_token("node name", vin)
    _validate_token("node name", vout)
    _validate_token("ground node name", gnd)
    if vin == vout:
        raise CircuitGraphError("vin and vout must refer to different nodes")
    if vin == gnd or vout == gnd:
        raise CircuitGraphError("signal nodes must not reuse the ground node")

    resistance_ohms = _validate_positive_finite("resistance_ohms", resistance_ohms)
    capacitance_farads = _validate_positive_finite("capacitance_farads", capacitance_farads)

    block_metadata = {
        "archetype_id": BLOCK_ARCHETYPE_ID,
        "block": BLOCK_IDENTIFIER,
        "capability_id": BLOCK_IDENTIFIER,
        "capability_version": BLOCK_VERSION,
        "category": BLOCK_CATEGORY,
        "capacitance_farads": capacitance_farads,
        "maturity": BLOCK_MATURITY,
        "resistance_ohms": resistance_ohms,
        "version": BLOCK_VERSION,
    }
    if metadata is not None:
        _validate_metadata("block metadata", metadata)
        block_metadata.update(metadata)

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
        "probes": ["vin_voltage", "vout_voltage", "transfer_function"],
        "supported_analyses": ["ac", "dc", "transient"],
    }
    archetype_metadata = {
        "archetype_family": "vertical_slice",
        "archetype_id": BLOCK_ARCHETYPE_ID,
        "ports": ["VIN", "VOUT", "GND"],
        "topology": "series_capacitor_shunt_resistor",
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

    build_capacitor(
        graph,
        "C1",
        vin,
        vout,
        capacitance_farads,
        metadata={"block": BLOCK_IDENTIFIER, "role": "series"},
    )
    build_resistor(
        graph,
        "R1",
        vout,
        gnd,
        resistance_ohms,
        metadata={"block": BLOCK_IDENTIFIER, "role": "shunt"},
    )
    graph.add_port("VIN", vin, role="input", metadata={"signal": "input"})
    graph.add_port("VOUT", vout, role="output", metadata={"signal": "output"})
    graph.add_port("GND", gnd, role="ground", metadata={"signal": "reference"})
    graph.add_probe("vin_voltage", kind="voltage", target=vin, metadata={"port": "VIN"})
    graph.add_probe("vout_voltage", kind="voltage", target=vout, metadata={"port": "VOUT"})
    graph.add_probe(
        "transfer_function",
        kind="transfer_function",
        target=vout,
        metadata={"from": "VIN", "to": "VOUT"},
    )
    graph.add_analysis(
        "ac",
        kind="ac",
        parameters={"points_per_decade": 10, "start_hz": 1.0, "stop_hz": 1e6},
        metadata={"domain": "frequency"},
    )
    graph.add_analysis("dc", kind="dc", parameters={}, metadata={"domain": "bias"})
    graph.add_analysis(
        "transient",
        kind="transient",
        parameters={"stop_s": 0.01, "step_s": 1e-5},
        metadata={"domain": "time"},
    )
    graph.validate_rc_high_pass_topology()
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
