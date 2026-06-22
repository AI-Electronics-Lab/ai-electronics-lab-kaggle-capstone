"""Deterministic trusted-source simulation assembly."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal

from ai_electronics_lab.contracts import CircuitPlan, require_valid_circuit_plan

from .core import (
    CircuitGraph,
    NetlistIR,
    NetlistStatement,
    build_ac_voltage_source,
    build_dc_voltage_source,
)
from .plan_adapter import build_circuit_graph_from_plan

SIMULATION_ASSEMBLY_VERSION = "1.0"
_SOURCE_REFERENCE = "V1"
_INPUT_NODE = "vin"
_OUTPUT_NODE = "vout"
_GROUND_NODE = "0"


@dataclass(frozen=True, slots=True)
class SimulationAnalysis:
    """Typed, non-executable analysis intent for a trusted component deck."""

    kind: Literal["ac", "dc"]
    requested_frequencies_hz: tuple[float | int, ...]
    probe_names: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.kind not in {"ac", "dc"}:
            raise ValueError("simulation analysis kind must be 'ac' or 'dc'")
        frequencies = tuple(self.requested_frequencies_hz)
        probes = tuple(self.probe_names)
        if self.kind == "dc" and frequencies:
            raise ValueError("dc simulation analysis must not contain requested frequencies")
        object.__setattr__(self, "requested_frequencies_hz", frequencies)
        object.__setattr__(self, "probe_names", probes)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "requested_frequencies_hz": list(self.requested_frequencies_hz),
            "probe_names": list(self.probe_names),
        }


@dataclass(frozen=True, slots=True)
class SimulationAssembly:
    """Immutable component deck and its typed analysis request."""

    version: str
    netlist_ir: NetlistIR
    analysis: SimulationAnalysis
    source_reference: str

    def __post_init__(self) -> None:
        if self.version != SIMULATION_ASSEMBLY_VERSION:
            raise ValueError(f"simulation assembly version must be {SIMULATION_ASSEMBLY_VERSION!r}")
        if not isinstance(self.netlist_ir, NetlistIR):
            raise TypeError("simulation assembly netlist_ir must be a NetlistIR")
        if not isinstance(self.analysis, SimulationAnalysis):
            raise TypeError("simulation assembly analysis must be a SimulationAnalysis")
        if self.source_reference != _SOURCE_REFERENCE:
            raise ValueError(f"simulation source reference must be {_SOURCE_REFERENCE!r}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "netlist_ir": self.netlist_ir.to_dict(),
            "analysis": self.analysis.to_dict(),
            "source_reference": self.source_reference,
        }

    def to_json(self) -> str:
        return json.dumps(
            self.to_dict(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )


def build_simulation_assembly_from_plan(plan: CircuitPlan) -> SimulationAssembly:
    """Validate a plan, then assemble one trusted source with its passive topology."""

    validated_plan = require_valid_circuit_plan(plan)
    passive_graph = build_circuit_graph_from_plan(validated_plan)
    passive_ir = passive_graph.to_netlist_ir()

    passive_node_names = {node.name for node in passive_ir.nodes}
    if not {_INPUT_NODE, _OUTPUT_NODE, _GROUND_NODE}.issubset(passive_node_names):
        raise ValueError("trusted passive topology is missing required source nodes")

    source_graph = CircuitGraph(name="trusted_simulation_source")
    if validated_plan.topology in {"rc_low_pass", "rc_high_pass"}:
        source_component = build_ac_voltage_source(
            source_graph,
            _SOURCE_REFERENCE,
            _INPUT_NODE,
            _GROUND_NODE,
            ac_magnitude=1.0,
            phase_deg=0.0,
        )
        source_policy = "unit_ac"
        requested_frequencies = tuple(validated_plan.requested_frequencies_hz)
    else:
        source_component = build_dc_voltage_source(
            source_graph,
            _SOURCE_REFERENCE,
            _INPUT_NODE,
            _GROUND_NODE,
            validated_plan.parameters["input_voltage_volts"],
        )
        source_policy = "plan_dc"
        requested_frequencies = ()

    if not set(source_component.terminals.values()).issubset(passive_node_names):
        raise ValueError("trusted source references a node outside the passive topology")

    source_statement = NetlistStatement.from_component(source_component)
    components = tuple(
        sorted((*passive_ir.components, source_statement), key=lambda statement: statement.refdes)
    )
    metadata = {
        **dict(passive_ir.metadata),
        "simulation_assembly_version": SIMULATION_ASSEMBLY_VERSION,
        "simulation_source_policy": source_policy,
    }
    netlist_ir = NetlistIR(
        name=passive_ir.name,
        metadata=metadata,
        nodes=passive_ir.nodes,
        components=components,
    )
    analysis = SimulationAnalysis(
        kind=validated_plan.analysis,
        requested_frequencies_hz=requested_frequencies,
        probe_names=tuple(sorted(probe.name for probe in passive_graph.list_probes())),
    )
    return SimulationAssembly(
        version=SIMULATION_ASSEMBLY_VERSION,
        netlist_ir=netlist_ir,
        analysis=analysis,
        source_reference=_SOURCE_REFERENCE,
    )


__all__ = [
    "SIMULATION_ASSEMBLY_VERSION",
    "SimulationAnalysis",
    "SimulationAssembly",
    "build_simulation_assembly_from_plan",
]
