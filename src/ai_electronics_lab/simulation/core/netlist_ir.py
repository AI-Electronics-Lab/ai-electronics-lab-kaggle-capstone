from __future__ import annotations

import copy
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from .circuit_graph import (
    CircuitComponent,
    CircuitGraph,
    CircuitNode,
    _freeze_mapping,
    _sorted_mapping,
)


@dataclass(frozen=True, slots=True)
class NetlistStatement:
    refdes: str
    kind: str
    terminals: tuple[tuple[str, str], ...]
    parameters: tuple[tuple[str, Any], ...] = field(default_factory=tuple)
    metadata: tuple[tuple[str, Any], ...] = field(default_factory=tuple)

    @classmethod
    def from_component(cls, component: CircuitComponent) -> "NetlistStatement":
        return cls(
            refdes=component.refdes,
            kind=component.kind,
            terminals=tuple((terminal, component.terminals[terminal]) for terminal in sorted(component.terminals)),
            parameters=tuple((key, copy.deepcopy(component.parameters[key])) for key in sorted(component.parameters)),
            metadata=tuple((key, copy.deepcopy(component.metadata[key])) for key in sorted(component.metadata)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "refdes": self.refdes,
            "kind": self.kind,
            "terminals": [tuple(item) for item in self.terminals],
            "parameters": [tuple(item) for item in self.parameters],
            "metadata": [tuple(item) for item in self.metadata],
        }


@dataclass(frozen=True, slots=True)
class NetlistIR:
    name: str
    metadata: Mapping[str, Any] = field(default_factory=dict)
    nodes: tuple[CircuitNode, ...] = field(default_factory=tuple)
    components: tuple[NetlistStatement, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata))

    @classmethod
    def from_circuit_graph(cls, graph: CircuitGraph) -> "NetlistIR":
        graph.validate_integrity()
        return cls(
            name=graph.name,
            metadata=graph.metadata,
            nodes=graph.list_nodes(),
            components=tuple(NetlistStatement.from_component(component) for component in graph.list_components()),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "metadata": _sorted_mapping(self.metadata),
            "nodes": [node.to_dict() for node in self.nodes],
            "components": [component.to_dict() for component in self.components],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
