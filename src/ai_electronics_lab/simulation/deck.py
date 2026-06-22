"""Bounded deterministic expansion of simulation assemblies into ngspice decks."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any, Literal

from ai_electronics_lab.contracts.circuit_plan import (
    MAX_CAPACITANCE_FARADS,
    MAX_FREQUENCY_HZ,
    MAX_INPUT_VOLTAGE_VOLTS,
    MAX_REQUESTED_FREQUENCIES,
    MAX_RESISTANCE_OHMS,
    MIN_CAPACITANCE_FARADS,
    MIN_FREQUENCY_HZ,
    MIN_RESISTANCE_OHMS,
)

from .assembly import SIMULATION_ASSEMBLY_VERSION, SimulationAssembly
from .core import NetlistIR, NetlistStatement
from .core.spice_renderer import SpiceRendererError, _format_scalar, render_spice_netlist

SIMULATION_DECK_VERSION = "1.0"
MAX_AC_RUNS = MAX_REQUESTED_FREQUENCIES

_NODES = {"0", "vin", "vout"}
_PROBES = {
    "ac": ("transfer_function", "vin_voltage", "vout_voltage"),
    "dc": ("divider_ratio", "vin_voltage", "vout_voltage"),
}
_SHAPES = {
    "rc_low_pass": {
        "C1": ("capacitor", {"a": "vout", "b": "0"}, "capacitance_farads"),
        "R1": ("resistor", {"a": "vin", "b": "vout"}, "resistance_ohms"),
    },
    "rc_high_pass": {
        "C1": ("capacitor", {"a": "vin", "b": "vout"}, "capacitance_farads"),
        "R1": ("resistor", {"a": "vout", "b": "0"}, "resistance_ohms"),
    },
    "resistive_divider": {
        "R1": ("resistor", {"a": "vin", "b": "vout"}, "resistance_ohms"),
        "R2": ("resistor", {"a": "vout", "b": "0"}, "resistance_ohms"),
    },
}


class SimulationDeckError(ValueError):
    """Stable structured failure at the assembly-to-deck boundary."""

    def __init__(self, code: str, path: tuple[str | int, ...], message: str) -> None:
        self.code = code
        self.path = path
        self.message = message
        location = ".".join(str(item) for item in path) or "<root>"
        super().__init__(f"{code} at {location}: {message}")

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "path": list(self.path), "message": self.message}


@dataclass(frozen=True, slots=True)
class SimulationDeckRun:
    """One complete independent ngspice input deck."""

    run_id: str
    analysis_kind: Literal["ac", "dc"]
    frequency_hz: float | int | None
    probe_names: tuple[str, ...]
    netlist_text: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "probe_names", tuple(self.probe_names))

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "analysis_kind": self.analysis_kind,
            "frequency_hz": self.frequency_hz,
            "probe_names": list(self.probe_names),
            "netlist_text": self.netlist_text,
        }

    def to_json(self) -> str:
        return json.dumps(
            self.to_dict(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )


@dataclass(frozen=True, slots=True)
class SimulationDeck:
    """Immutable ordered collection of complete simulation runs."""

    version: str
    runs: tuple[SimulationDeckRun, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "runs", tuple(self.runs))

    def to_dict(self) -> dict[str, Any]:
        return {"version": self.version, "runs": [run.to_dict() for run in self.runs]}

    def to_json(self) -> str:
        return json.dumps(
            self.to_dict(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )


def build_simulation_deck_from_assembly(assembly: SimulationAssembly) -> SimulationDeck:
    """Validate an assembly and expand its trusted analysis into bounded run decks."""

    try:
        return _build(assembly)
    except SimulationDeckError:
        raise
    except (AttributeError, IndexError, KeyError, TypeError, ValueError, AssertionError) as exc:
        raise SimulationDeckError(
            "assembly.malformed", (), "assembly could not be validated or rendered"
        ) from exc


def _build(assembly: SimulationAssembly) -> SimulationDeck:
    if not isinstance(assembly, SimulationAssembly):
        _fail("assembly.type", (), "assembly must be a SimulationAssembly")
    if assembly.version != SIMULATION_ASSEMBLY_VERSION:
        _fail("assembly.version.unsupported", ("version",), "assembly version is not supported")
    if not isinstance(assembly.netlist_ir, NetlistIR):
        _fail("assembly.netlist_ir.type", ("netlist_ir",), "netlist_ir must be a NetlistIR")

    analysis = assembly.analysis
    if analysis.kind not in _PROBES:
        _fail("analysis.kind.unsupported", ("analysis", "kind"), "analysis kind is not supported")
    if not isinstance(analysis.requested_frequencies_hz, tuple):
        _fail(
            "analysis.frequencies.type",
            ("analysis", "requested_frequencies_hz"),
            "frequencies must be an immutable tuple",
        )
    if (
        not isinstance(analysis.probe_names, tuple)
        or analysis.probe_names != _PROBES[analysis.kind]
    ):
        _fail(
            "analysis.probes.untrusted",
            ("analysis", "probe_names"),
            "probe names are not the trusted sorted tuple",
        )

    _validate_ir(assembly.netlist_ir, analysis.kind, assembly.source_reference)
    component_deck = _render_component_deck(assembly.netlist_ir)
    if analysis.kind == "dc":
        if analysis.requested_frequencies_hz:
            _fail(
                "analysis.frequencies.not_allowed_for_dc",
                ("analysis", "requested_frequencies_hz"),
                "DC analysis must not contain frequencies",
            )
        runs = (_run("dc-op", "dc", None, analysis.probe_names, component_deck, ".op"),)
    else:
        frequencies = analysis.requested_frequencies_hz
        if not frequencies:
            _fail(
                "analysis.frequencies.empty",
                ("analysis", "requested_frequencies_hz"),
                "AC analysis requires at least one frequency",
            )
        if len(frequencies) > MAX_AC_RUNS:
            _fail(
                "analysis.frequencies.too_many",
                ("analysis", "requested_frequencies_hz"),
                f"at most {MAX_AC_RUNS} AC runs are allowed",
            )
        for index, frequency in enumerate(frequencies):
            _validate_number(
                frequency,
                ("analysis", "requested_frequencies_hz", index),
                positive=True,
                minimum=MIN_FREQUENCY_HZ,
                maximum=MAX_FREQUENCY_HZ,
            )
        runs = tuple(
            _run(
                f"ac-{index + 1:02d}",
                "ac",
                frequency,
                analysis.probe_names,
                component_deck,
                f".ac lin 1 {_format_scalar(frequency)} {_format_scalar(frequency)}",
            )
            for index, frequency in enumerate(frequencies)
        )
    return SimulationDeck(SIMULATION_DECK_VERSION, runs)


def _validate_ir(netlist: NetlistIR, kind: str, source_reference: Any) -> None:
    if source_reference != "V1":
        _fail("source.reference.invalid", ("source_reference",), "source reference must be V1")
    if netlist.name not in _SHAPES:
        _fail("netlist.name.untrusted", ("netlist_ir", "name"), "netlist name is not trusted")
    if (kind == "dc") != (netlist.name == "resistive_divider"):
        _fail(
            "analysis.topology_mismatch", ("analysis", "kind"), "analysis does not match topology"
        )
    if not isinstance(netlist.nodes, tuple) or len(netlist.nodes) != 3:
        _fail(
            "netlist.nodes.invalid",
            ("netlist_ir", "nodes"),
            "nodes must be an immutable three-node tuple",
        )
    if {node.name for node in netlist.nodes} != _NODES:
        _fail(
            "netlist.nodes.invalid",
            ("netlist_ir", "nodes"),
            "nodes must be exactly 0, vin, and vout",
        )
    if not isinstance(netlist.components, tuple):
        _fail(
            "netlist.components.type",
            ("netlist_ir", "components"),
            "components must be an immutable tuple",
        )
    expected_refs = tuple(sorted((*_SHAPES[netlist.name], "V1")))
    if tuple(item.refdes for item in netlist.components) != expected_refs:
        _fail(
            "netlist.components.untrusted",
            ("netlist_ir", "components"),
            "components do not match the trusted topology and order",
        )
    statements = {item.refdes: item for item in netlist.components}
    for refdes, (component_kind, terminals, parameter) in _SHAPES[netlist.name].items():
        _validate_passive(statements[refdes], component_kind, terminals, parameter)
    _validate_source(statements["V1"], kind)


def _validate_passive(
    statement: NetlistStatement, kind: str, terminals: dict[str, str], parameter: str
) -> None:
    path = ("netlist_ir", "components", statement.refdes)
    if statement.kind != kind or dict(statement.terminals) != terminals:
        _fail("component.shape.invalid", path, "component kind or terminals are invalid")
    parameters = dict(statement.parameters)
    if set(parameters) != {parameter}:
        _fail(
            "component.parameters.invalid",
            path + ("parameters",),
            "component parameters are invalid",
        )
    if parameter == "capacitance_farads":
        minimum = MIN_CAPACITANCE_FARADS
        maximum = MAX_CAPACITANCE_FARADS
    else:
        minimum = MIN_RESISTANCE_OHMS
        maximum = MAX_RESISTANCE_OHMS
    _validate_number(
        parameters[parameter],
        path + ("parameters", parameter),
        positive=True,
        minimum=minimum,
        maximum=maximum,
    )


def _validate_source(statement: NetlistStatement, kind: str) -> None:
    path = ("netlist_ir", "components", "V1")
    if statement.kind != "voltage_source" or dict(statement.terminals) != {
        "negative": "0",
        "positive": "vin",
    }:
        _fail("source.shape.invalid", path, "V1 must be a voltage source from vin to 0")
    parameters = dict(statement.parameters)
    if kind == "ac":
        if set(parameters) != {"ac_magnitude", "ac_phase_deg"}:
            _fail(
                "source.parameters.invalid",
                path + ("parameters",),
                "AC V1 must contain only magnitude and phase",
            )
        _validate_number(
            parameters["ac_magnitude"],
            path + ("parameters", "ac_magnitude"),
            positive=True,
        )
        _validate_number(
            parameters["ac_phase_deg"],
            path + ("parameters", "ac_phase_deg"),
        )
        if parameters["ac_magnitude"] != 1.0 or parameters["ac_phase_deg"] != 0.0:
            _fail(
                "source.parameters.invalid",
                path + ("parameters",),
                "AC V1 must use unit magnitude and zero phase",
            )
    elif set(parameters) != {"dc_volts"}:
        _fail(
            "source.parameters.invalid", path + ("parameters",), "DC V1 must contain only dc_volts"
        )
    else:
        _validate_number(
            parameters["dc_volts"],
            path + ("parameters", "dc_volts"),
            nonzero=True,
            minimum=math.nextafter(0.0, 1.0),
            maximum=MAX_INPUT_VOLTAGE_VOLTS,
            magnitude=True,
        )


def _validate_number(
    value: Any,
    path: tuple[str | int, ...],
    *,
    positive: bool = False,
    nonzero: bool = False,
    minimum: float | None = None,
    maximum: float | None = None,
    magnitude: bool = False,
) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail("number.type", path, "value must be an int or float, excluding bool")
    if not math.isfinite(value):
        _fail("number.non_finite", path, "value must be finite")
    if positive and value <= 0:
        _fail("number.not_positive", path, "value must be greater than zero")
    if nonzero and value == 0:
        _fail("number.zero", path, "value must be nonzero")

    comparable = abs(value) if magnitude else value
    if minimum is not None and comparable < minimum:
        _fail("number.out_of_range", path, "value is below the trusted numeric range")
    if maximum is not None and comparable > maximum:
        _fail("number.out_of_range", path, "value is above the trusted numeric range")


def _render_component_deck(netlist: NetlistIR) -> str:
    try:
        rendered = render_spice_netlist(netlist)
    except SpiceRendererError as exc:
        raise SimulationDeckError(
            "netlist.render.failed", ("netlist_ir",), "component rendering failed"
        ) from exc
    lines = rendered.splitlines()
    if len(lines) != 1 + len(netlist.metadata) + len(netlist.components) + 1:
        _fail(
            "netlist.render.multiline", ("netlist_ir",), "rendered fields must remain on one line"
        )
    if not lines or lines[-1] != ".end" or lines.count(".end") != 1:
        _fail(
            "netlist.end.invalid",
            ("netlist_ir",),
            "component deck must end with exactly one .end line",
        )
    if [line for line in lines if line.lstrip().startswith(".")] != [".end"]:
        _fail(
            "netlist.directive.untrusted",
            ("netlist_ir",),
            "component deck contains an executable directive",
        )
    return rendered


def _run(
    run_id: str,
    kind: Literal["ac", "dc"],
    frequency: float | int | None,
    probes: tuple[str, ...],
    component_deck: str,
    directive: str,
) -> SimulationDeckRun:
    lines = component_deck.splitlines()
    return SimulationDeckRun(
        run_id, kind, frequency, probes, "\n".join((*lines[:-1], directive, ".end"))
    )


def _fail(code: str, path: tuple[str | int, ...], message: str) -> None:
    raise SimulationDeckError(code, path, message)


__all__ = [
    "MAX_AC_RUNS",
    "SIMULATION_DECK_VERSION",
    "SimulationDeck",
    "SimulationDeckError",
    "SimulationDeckRun",
    "build_simulation_deck_from_assembly",
]
