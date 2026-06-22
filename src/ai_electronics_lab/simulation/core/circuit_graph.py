from __future__ import annotations

import copy
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any


class CircuitGraphError(ValueError):
    """Raised when a circuit graph or component fails validation."""


def _freeze_mapping(value: Mapping[str, Any] | None) -> Mapping[str, Any]:
    frozen = copy.deepcopy(dict(value or {}))
    return MappingProxyType(frozen)


def _sorted_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    return {key: copy.deepcopy(value[key]) for key in sorted(value)}


def _sorted_tuple_items(value: Mapping[str, Any]) -> tuple[tuple[str, Any], ...]:
    return tuple((key, copy.deepcopy(value[key])) for key in sorted(value))


def _validate_token(label: str, value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CircuitGraphError(f"{label} must be a non-empty string")
    if value != value.strip():
        raise CircuitGraphError(f"{label} must not contain leading or trailing whitespace: {value!r}")
    if any(character.isspace() for character in value):
        raise CircuitGraphError(f"{label} must not contain whitespace: {value!r}")
    return value


@dataclass(frozen=True, slots=True)
class CircuitNode:
    name: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _validate_token("node name", self.name)
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "metadata": _sorted_mapping(self.metadata)}


CircuitNet = CircuitNode


@dataclass(frozen=True, slots=True)
class CircuitComponent:
    refdes: str
    kind: str
    terminals: Mapping[str, str]
    parameters: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _validate_token("component refdes", self.refdes)
        _validate_token("component kind", self.kind)
        if not isinstance(self.terminals, Mapping) or not dict(self.terminals):
            raise CircuitGraphError("component must define at least one terminal")

        terminals = copy.deepcopy(dict(self.terminals))
        for terminal_name, node_name in terminals.items():
            _validate_token("terminal name", terminal_name)
            _validate_token("terminal node reference", node_name)

        object.__setattr__(self, "terminals", MappingProxyType(terminals))
        object.__setattr__(self, "parameters", _freeze_mapping(self.parameters))
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        return {
            "refdes": self.refdes,
            "kind": self.kind,
            "terminals": {key: copy.deepcopy(self.terminals[key]) for key in sorted(self.terminals)},
            "parameters": _sorted_mapping(self.parameters),
            "metadata": _sorted_mapping(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class CircuitPort:
    name: str
    net: str
    role: str = "signal"
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _validate_token("port name", self.name)
        _validate_token("port net", self.net)
        _validate_token("port role", self.role)
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "net": self.net,
            "role": self.role,
            "metadata": _sorted_mapping(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class CircuitProbe:
    name: str
    kind: str
    target: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _validate_token("probe name", self.name)
        _validate_token("probe kind", self.kind)
        _validate_token("probe target", self.target)
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "target": self.target,
            "metadata": _sorted_mapping(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class CircuitAnalysis:
    name: str
    kind: str
    parameters: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _validate_token("analysis name", self.name)
        _validate_token("analysis kind", self.kind)
        object.__setattr__(self, "parameters", _freeze_mapping(self.parameters))
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "parameters": _sorted_mapping(self.parameters),
            "metadata": _sorted_mapping(self.metadata),
        }


class CircuitGraph:
    def __init__(
        self,
        name: str,
        metadata: Mapping[str, Any] | None = None,
        capability_metadata: Mapping[str, Any] | None = None,
        archetype_metadata: Mapping[str, Any] | None = None,
    ) -> None:
        _validate_token("graph name", name)
        self.name = name
        self._metadata = _freeze_mapping(metadata)
        self._capability_metadata = _freeze_mapping(capability_metadata)
        self._archetype_metadata = _freeze_mapping(archetype_metadata)
        self._nodes: dict[str, CircuitNode] = {}
        self._components: dict[str, CircuitComponent] = {}
        self._ports: dict[str, CircuitPort] = {}
        self._probes: dict[str, CircuitProbe] = {}
        self._analyses: dict[str, CircuitAnalysis] = {}

    @property
    def metadata(self) -> Mapping[str, Any]:
        return self._metadata

    @property
    def capability_metadata(self) -> Mapping[str, Any]:
        return self._capability_metadata

    @property
    def archetype_metadata(self) -> Mapping[str, Any]:
        return self._archetype_metadata

    def add_node(self, name: str, metadata: Mapping[str, Any] | None = None) -> CircuitNode:
        node = CircuitNode(name=name, metadata=metadata or {})
        if node.name in self._nodes:
            raise CircuitGraphError(f"duplicate node name: {node.name}")
        self._nodes[node.name] = node
        return node

    def get_node(self, name: str) -> CircuitNode:
        try:
            return self._nodes[name]
        except KeyError as exc:  # pragma: no cover - defensive
            raise CircuitGraphError(f"unknown node: {name}") from exc

    def list_nodes(self) -> tuple[CircuitNode, ...]:
        return tuple(self._nodes[name] for name in sorted(self._nodes))

    def list_nets(self) -> tuple[CircuitNet, ...]:
        return self.list_nodes()

    def add_component(
        self,
        refdes: str,
        kind: str,
        terminals: Mapping[str, str],
        parameters: Mapping[str, Any] | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> CircuitComponent:
        component = CircuitComponent(
            refdes=refdes,
            kind=kind,
            terminals=terminals,
            parameters=parameters or {},
            metadata=metadata or {},
        )
        if component.refdes in self._components:
            raise CircuitGraphError(f"duplicate refdes: {component.refdes}")
        missing_nodes = [node_name for node_name in component.terminals.values() if node_name not in self._nodes]
        if missing_nodes:
            raise CircuitGraphError(
                "component references unknown node(s): " + ", ".join(sorted(set(missing_nodes)))
            )
        self._components[component.refdes] = component
        return component

    def get_component(self, refdes: str) -> CircuitComponent:
        try:
            return self._components[refdes]
        except KeyError as exc:  # pragma: no cover - defensive
            raise CircuitGraphError(f"unknown component: {refdes}") from exc

    def list_components(self) -> tuple[CircuitComponent, ...]:
        return tuple(self._components[refdes] for refdes in sorted(self._components))

    def add_port(
        self,
        name: str,
        net: str,
        *,
        role: str = "signal",
        metadata: Mapping[str, Any] | None = None,
    ) -> CircuitPort:
        port = CircuitPort(name=name, net=net, role=role, metadata=metadata or {})
        if port.name in self._ports:
            raise CircuitGraphError(f"duplicate port name: {port.name}")
        if port.net not in self._nodes:
            raise CircuitGraphError(f"port {port.name!r} references unknown net: {port.net!r}")
        self._ports[port.name] = port
        return port

    def get_port(self, name: str) -> CircuitPort:
        try:
            return self._ports[name]
        except KeyError as exc:  # pragma: no cover - defensive
            raise CircuitGraphError(f"unknown port: {name}") from exc

    def list_ports(self) -> tuple[CircuitPort, ...]:
        return tuple(self._ports[name] for name in sorted(self._ports))

    def add_probe(
        self,
        name: str,
        *,
        kind: str,
        target: str,
        metadata: Mapping[str, Any] | None = None,
    ) -> CircuitProbe:
        probe = CircuitProbe(name=name, kind=kind, target=target, metadata=metadata or {})
        if probe.name in self._probes:
            raise CircuitGraphError(f"duplicate probe name: {probe.name}")
        if probe.target not in self._nodes and probe.target not in self._components:
            raise CircuitGraphError(f"probe {probe.name!r} references unknown target: {probe.target!r}")
        self._probes[probe.name] = probe
        return probe

    def get_probe(self, name: str) -> CircuitProbe:
        try:
            return self._probes[name]
        except KeyError as exc:  # pragma: no cover - defensive
            raise CircuitGraphError(f"unknown probe: {name}") from exc

    def list_probes(self) -> tuple[CircuitProbe, ...]:
        return tuple(self._probes[name] for name in self._probes)

    def add_analysis(
        self,
        name: str,
        *,
        kind: str,
        parameters: Mapping[str, Any] | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> CircuitAnalysis:
        analysis = CircuitAnalysis(name=name, kind=kind, parameters=parameters or {}, metadata=metadata or {})
        if analysis.name in self._analyses:
            raise CircuitGraphError(f"duplicate analysis name: {analysis.name}")
        self._analyses[analysis.name] = analysis
        return analysis

    def get_analysis(self, name: str) -> CircuitAnalysis:
        try:
            return self._analyses[name]
        except KeyError as exc:  # pragma: no cover - defensive
            raise CircuitGraphError(f"unknown analysis: {name}") from exc

    def list_analyses(self) -> tuple[CircuitAnalysis, ...]:
        return tuple(self._analyses[name] for name in sorted(self._analyses))

    def validate(self) -> None:
        self.validate_integrity()

    def validate_integrity(self) -> None:
        for component in self._components.values():
            missing_nodes = [node_name for node_name in component.terminals.values() if node_name not in self._nodes]
            if missing_nodes:
                raise CircuitGraphError(
                    f"component {component.refdes} references unknown node(s): "
                    + ", ".join(sorted(set(missing_nodes)))
                )

        for port in self._ports.values():
            if port.net not in self._nodes:
                raise CircuitGraphError(f"port {port.name!r} references unknown net: {port.net!r}")

        for probe in self._probes.values():
            if probe.target not in self._nodes and probe.target not in self._components:
                raise CircuitGraphError(f"probe {probe.name!r} references unknown target: {probe.target!r}")

    def validate_artifact_consistency(self, artifact_manifest: Mapping[str, Any] | None = None) -> None:
        manifest = artifact_manifest if artifact_manifest is not None else self.capability_metadata.get("artifact_manifest")
        if manifest is None:
            return
        if not isinstance(manifest, Mapping):
            raise CircuitGraphError("artifact manifest must be a mapping or None")

        normalized_manifest: dict[str, Any] = {}
        for key, value in manifest.items():
            _validate_token("artifact manifest key", key)
            if not isinstance(value, str) or not value.strip():
                raise CircuitGraphError(f"artifact manifest entry {key!r} must be a non-empty string")
            normalized_manifest[key] = value

        declared_manifest = self.capability_metadata.get("artifact_manifest")
        if artifact_manifest is not None and declared_manifest and dict(declared_manifest) != normalized_manifest:
            raise CircuitGraphError("artifact manifest does not match graph capability metadata")

    def validate_rc_low_pass_topology(self) -> None:
        self.validate_integrity()

        capability_id = self.capability_metadata.get("capability_id")
        if capability_id != "rc_low_pass":
            raise CircuitGraphError("RC low-pass capability metadata is missing or incorrect")

        archetype_id = self.archetype_metadata.get("archetype_id")
        if archetype_id != "rc_low_pass_vertical_slice":
            raise CircuitGraphError("RC low-pass archetype metadata is missing or incorrect")

        port_by_role = {port.role: port for port in self._ports.values()}
        required_roles = {"input", "output", "ground"}
        if set(port_by_role) != required_roles:
            raise CircuitGraphError("RC low-pass graph must declare input, output, and ground ports")

        input_port = port_by_role["input"]
        output_port = port_by_role["output"]
        ground_port = port_by_role["ground"]

        if input_port.name != "VIN" or output_port.name != "VOUT" or ground_port.name != "GND":
            raise CircuitGraphError("RC low-pass ports must be named VIN, VOUT, and GND")

        input_net = input_port.net
        output_net = output_port.net
        ground_net = ground_port.net

        if len({input_net, output_net, ground_net}) != 3:
            raise CircuitGraphError("input, output, and ground nets must be distinct")

        if set(self._components) != {"C1", "R1"}:
            raise CircuitGraphError("RC low-pass graph must contain only R1 and C1 components")

        resistor = self.get_component("R1")
        capacitor = self.get_component("C1")
        if resistor.kind != "resistor":
            raise CircuitGraphError("R1 must be a resistor")
        if capacitor.kind != "capacitor":
            raise CircuitGraphError("C1 must be a capacitor")

        resistor_nodes = set(resistor.terminals.values())
        capacitor_nodes = set(capacitor.terminals.values())

        for component in (resistor, capacitor):
            terminal_nodes = tuple(component.terminals.values())
            if len(set(terminal_nodes)) != len(terminal_nodes):
                raise CircuitGraphError(f"component {component.refdes} creates a direct short")
            if input_net in terminal_nodes and ground_net in terminal_nodes and component.refdes != "C1":
                raise CircuitGraphError("RC low-pass graph contains an input-ground short")
            if output_net in terminal_nodes and ground_net in terminal_nodes and component.refdes != "C1":
                raise CircuitGraphError("RC low-pass graph contains an output-ground short")

        if resistor_nodes != {input_net, output_net}:
            raise CircuitGraphError("RC low-pass resistor must connect input to output")
        if capacitor_nodes != {output_net, ground_net}:
            raise CircuitGraphError("RC low-pass capacitor must connect output to ground")

        analysis_kinds = {analysis.kind for analysis in self._analyses.values()}
        if analysis_kinds != {"ac", "dc", "transient"}:
            raise CircuitGraphError("RC low-pass graph must declare ac, dc, and transient analyses")

        probe_names = {probe.name for probe in self._probes.values()}
        if probe_names != {"transfer_function", "vin_voltage", "vout_voltage"}:
            raise CircuitGraphError("RC low-pass graph must declare vin_voltage, vout_voltage, and transfer_function probes")

        self.validate_artifact_consistency()

    def validate_rc_high_pass_topology(self) -> None:
        self.validate_integrity()

        capability_id = self.capability_metadata.get("capability_id")
        if capability_id != "rc_high_pass":
            raise CircuitGraphError("RC high-pass capability metadata is missing or incorrect")

        archetype_id = self.archetype_metadata.get("archetype_id")
        if archetype_id != "rc_high_pass_vertical_slice":
            raise CircuitGraphError("RC high-pass archetype metadata is missing or incorrect")

        topology = self.archetype_metadata.get("topology")
        if topology != "series_capacitor_shunt_resistor":
            raise CircuitGraphError("RC high-pass topology metadata is missing or incorrect")

        if len(self._ports) != 3:
            raise CircuitGraphError("RC high-pass graph must declare exactly three ports")
        port_by_role = {port.role: port for port in self._ports.values()}
        required_roles = {"input", "output", "ground"}
        if set(port_by_role) != required_roles:
            raise CircuitGraphError("RC high-pass graph must declare input, output, and ground ports")

        input_port = port_by_role["input"]
        output_port = port_by_role["output"]
        ground_port = port_by_role["ground"]
        if input_port.name != "VIN" or output_port.name != "VOUT" or ground_port.name != "GND":
            raise CircuitGraphError("RC high-pass ports must be named VIN, VOUT, and GND")

        input_net = input_port.net
        output_net = output_port.net
        ground_net = ground_port.net
        if len({input_net, output_net, ground_net}) != 3:
            raise CircuitGraphError("input, output, and ground nets must be distinct")

        if set(self._components) != {"C1", "R1"}:
            raise CircuitGraphError("RC high-pass graph must contain only C1 and R1 components")

        capacitor = self.get_component("C1")
        resistor = self.get_component("R1")
        if capacitor.kind != "capacitor":
            raise CircuitGraphError("C1 must be a capacitor")
        if resistor.kind != "resistor":
            raise CircuitGraphError("R1 must be a resistor")

        for component in (capacitor, resistor):
            terminal_nodes = tuple(component.terminals.values())
            if len(set(terminal_nodes)) != len(terminal_nodes):
                raise CircuitGraphError(f"component {component.refdes} creates a direct short")

        capacitor_nodes = set(capacitor.terminals.values())
        resistor_nodes = set(resistor.terminals.values())
        if capacitor_nodes != {input_net, output_net}:
            raise CircuitGraphError("RC high-pass capacitor must connect input to output")
        if resistor_nodes != {output_net, ground_net}:
            raise CircuitGraphError("RC high-pass resistor must connect output to ground")

        if set(self._analyses) != {"ac", "dc", "transient"} or any(
            analysis.name != analysis.kind for analysis in self._analyses.values()
        ):
            raise CircuitGraphError("RC high-pass graph must declare ac, dc, and transient analyses")

        probe_names = {probe.name for probe in self._probes.values()}
        if probe_names != {"transfer_function", "vin_voltage", "vout_voltage"}:
            raise CircuitGraphError(
                "RC high-pass graph must declare vin_voltage, vout_voltage, and transfer_function probes"
            )

        self.validate_artifact_consistency()

    def validate_resistive_divider_topology(self) -> None:
        self.validate_integrity()

        capability_id = self.capability_metadata.get("capability_id")
        if capability_id != "resistive_divider":
            raise CircuitGraphError("resistive-divider capability metadata is missing or incorrect")

        archetype_id = self.archetype_metadata.get("archetype_id")
        if archetype_id != "resistive_divider_vertical_slice":
            raise CircuitGraphError("resistive-divider archetype metadata is missing or incorrect")

        topology = self.archetype_metadata.get("topology")
        if topology != "series_resistor_shunt_resistor":
            raise CircuitGraphError("resistive-divider topology metadata is missing or incorrect")

        if len(self._ports) != 3:
            raise CircuitGraphError("resistive-divider graph must declare exactly three ports")
        port_by_role = {port.role: port for port in self._ports.values()}
        required_roles = {"input", "output", "ground"}
        if set(port_by_role) != required_roles:
            raise CircuitGraphError(
                "resistive-divider graph must declare input, output, and ground ports"
            )

        input_port = port_by_role["input"]
        output_port = port_by_role["output"]
        ground_port = port_by_role["ground"]
        if input_port.name != "VIN" or output_port.name != "VOUT" or ground_port.name != "GND":
            raise CircuitGraphError("resistive-divider ports must be named VIN, VOUT, and GND")

        input_net = input_port.net
        output_net = output_port.net
        ground_net = ground_port.net
        if len({input_net, output_net, ground_net}) != 3:
            raise CircuitGraphError("input, output, and ground nets must be distinct")

        if set(self._components) != {"R1", "R2"}:
            raise CircuitGraphError("resistive-divider graph must contain only R1 and R2 components")

        top_resistor = self.get_component("R1")
        bottom_resistor = self.get_component("R2")
        if top_resistor.kind != "resistor":
            raise CircuitGraphError("R1 must be a resistor")
        if bottom_resistor.kind != "resistor":
            raise CircuitGraphError("R2 must be a resistor")

        for component in (top_resistor, bottom_resistor):
            terminal_nodes = tuple(component.terminals.values())
            if len(set(terminal_nodes)) != len(terminal_nodes):
                raise CircuitGraphError(f"component {component.refdes} creates a direct short")

        if set(top_resistor.terminals.values()) != {input_net, output_net}:
            raise CircuitGraphError("R1 must connect input to output")
        if set(bottom_resistor.terminals.values()) != {output_net, ground_net}:
            raise CircuitGraphError("R2 must connect output to ground")

        if set(self._analyses) != {"dc"}:
            raise CircuitGraphError("resistive-divider graph must declare exactly one dc analysis")
        dc_analysis = self.get_analysis("dc")
        if dc_analysis.name != "dc" or dc_analysis.kind != "dc":
            raise CircuitGraphError("resistive-divider analysis name and kind must both be dc")

        probe_names = {probe.name for probe in self._probes.values()}
        if probe_names != {"divider_ratio", "vin_voltage", "vout_voltage"}:
            raise CircuitGraphError(
                "resistive-divider graph must declare vin_voltage, vout_voltage, and divider_ratio probes"
            )

        self.validate_artifact_consistency()

    def to_dict(self) -> dict[str, Any]:
        self.validate_integrity()
        return {
            "name": self.name,
            "metadata": _sorted_mapping(self._metadata),
            "capability_metadata": _sorted_mapping(self._capability_metadata),
            "archetype_metadata": _sorted_mapping(self._archetype_metadata),
            "nodes": [node.to_dict() for node in self.list_nodes()],
            "nets": [node.to_dict() for node in self.list_nets()],
            "components": [component.to_dict() for component in self.list_components()],
            "ports": [port.to_dict() for port in self.list_ports()],
            "probes": [probe.to_dict() for probe in self.list_probes()],
            "analyses": [analysis.to_dict() for analysis in self.list_analyses()],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    def to_netlist_ir(self):
        from .netlist_ir import NetlistIR

        return NetlistIR.from_circuit_graph(self)
