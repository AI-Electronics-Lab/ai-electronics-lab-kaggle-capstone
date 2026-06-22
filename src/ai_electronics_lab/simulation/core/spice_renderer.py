from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from .netlist_ir import NetlistIR, NetlistStatement


class SpiceRendererError(ValueError):
    """Raised when a Netlist IR object cannot be rendered as SPICE text."""


@dataclass(frozen=True, slots=True)
class SpiceNetlistRenderer:
    """Render the isolated M8.4 Netlist IR into deterministic SPICE text."""

    def render(self, netlist: NetlistIR) -> str:
        lines = [f"* {netlist.name}"]
        if netlist.metadata:
            for key in sorted(netlist.metadata):
                lines.append(f"* metadata: {key}={_format_metadata_value(netlist.metadata[key])}")
        for statement in netlist.components:
            lines.append(self.render_statement(statement))
        lines.append(".end")
        return "\n".join(lines)

    def render_statement(self, statement: NetlistStatement) -> str:
        kind = statement.kind.strip().lower()
        if kind == "resistor":
            nodes = _terminal_nodes(statement, ("a", "b"))
            value = _parameter_value(statement, ("resistance_ohms", "value_ohms", "resistance"))
            return f"{statement.refdes} {nodes[0]} {nodes[1]} {_format_scalar(value)}"
        if kind == "capacitor":
            nodes = _terminal_nodes(statement, ("a", "b"))
            value = _parameter_value(statement, ("capacitance_farads", "value_farads", "capacitance"))
            return f"{statement.refdes} {nodes[0]} {nodes[1]} {_format_scalar(value)}"
        if kind == "inductor":
            nodes = _terminal_nodes(statement, ("a", "b"))
            value = _parameter_value(statement, ("inductance_henries", "value_henries", "inductance"))
            return f"{statement.refdes} {nodes[0]} {nodes[1]} {_format_scalar(value)}"
        if kind == "voltage_source":
            nodes = _terminal_nodes(statement, ("positive", "negative"))
            if _has_any_parameter(statement, ("sine_offset_volts", "sine_amplitude_volts", "sine_frequency_hz", "sine_phase_deg")):
                offset = _parameter_value(statement, ("sine_offset_volts",))
                amplitude = _parameter_value(statement, ("sine_amplitude_volts",))
                frequency = _parameter_value(statement, ("sine_frequency_hz",))
                phase = _maybe_parameter_value(statement, "sine_phase_deg")
                waveform = f"SINE({_format_scalar(offset)} {_format_scalar(amplitude)} {_format_scalar(frequency)}"
                if phase is not None:
                    waveform += f" {_format_scalar(phase)}"
                waveform += ")"
                return f"{statement.refdes} {nodes[0]} {nodes[1]} {waveform}"
            pieces = [statement.refdes, nodes[0], nodes[1]]
            dc_value = _maybe_parameter_value(statement, "dc_volts")
            ac_value = _maybe_parameter_value(statement, "ac_magnitude")
            ac_phase = _maybe_parameter_value(statement, "ac_phase_deg")
            if ac_phase is not None and ac_value is None:
                raise SpiceRendererError(
                    f"component {statement.refdes!r} of kind {statement.kind!r} has ac_phase_deg without ac_magnitude"
                )
            if dc_value is not None:
                pieces.extend(["DC", _format_scalar(dc_value)])
            if ac_value is not None:
                pieces.extend(["AC", _format_scalar(ac_value)])
                if ac_phase is not None:
                    pieces.append(_format_scalar(ac_phase))
            return " ".join(pieces)
        if kind == "current_source":
            nodes = _terminal_nodes(statement, ("positive", "negative"))
            pieces = [statement.refdes, nodes[0], nodes[1]]
            dc_value = _maybe_parameter_value(statement, "dc_amps")
            if dc_value is not None:
                pieces.extend(["DC", _format_scalar(dc_value)])
                return " ".join(pieces)
            raise SpiceRendererError(
                f"component {statement.refdes!r} of kind {statement.kind!r} is missing required parameter(s): dc_amps"
            )
        if kind == "bjt":
            nodes = _terminal_nodes(statement, ("collector", "base", "emitter"))
            model = _maybe_component_value(statement, "model")
            if model is None:
                raise SpiceRendererError(
                    f"component {statement.refdes!r} of kind {statement.kind!r} is missing required parameter(s): model"
                )
            return f"{statement.refdes} {nodes[0]} {nodes[1]} {nodes[2]} {_format_scalar(model)}"
        raise SpiceRendererError(
            f"unsupported component kind for SPICE rendering: {statement.kind!r} (refdes {statement.refdes!r})"
        )


def render_spice_netlist(netlist: NetlistIR) -> str:
    """Render a Netlist IR object into deterministic SPICE text."""

    return SpiceNetlistRenderer().render(netlist)


def _terminal_nodes(statement: NetlistStatement, required_terminals: tuple[str, ...]) -> tuple[str, ...]:
    terminal_map = {name: node for name, node in statement.terminals}
    missing = [terminal for terminal in required_terminals if terminal not in terminal_map]
    if missing:
        raise SpiceRendererError(
            f"component {statement.refdes!r} of kind {statement.kind!r} is missing terminal(s): {', '.join(missing)}"
        )
    return tuple(terminal_map[terminal] for terminal in required_terminals)


def _parameter_value(statement: NetlistStatement, names: Iterable[str]) -> Any:
    value = _maybe_parameter_value_any(statement, names)
    if value is None:
        raise SpiceRendererError(
            f"component {statement.refdes!r} of kind {statement.kind!r} is missing required parameter(s): "
            + ", ".join(names)
        )
    return value


def _maybe_parameter_value(statement: NetlistStatement, name: str) -> Any | None:
    return _maybe_parameter_value_any(statement, (name,))



def _maybe_component_value(statement: NetlistStatement, name: str) -> Any | None:
    value = _maybe_parameter_value(statement, name)
    if value is not None:
        return value
    return _maybe_metadata_value(statement, name)


def _maybe_parameter_value_any(statement: NetlistStatement, names: Iterable[str]) -> Any | None:
    parameters = {name: value for name, value in statement.parameters}
    for name in names:
        if name in parameters:
            return parameters[name]
    return None



def _maybe_metadata_value(statement: NetlistStatement, name: str) -> Any | None:
    metadata = {key: value for key, value in statement.metadata}
    return metadata.get(name)



def _has_any_parameter(statement: NetlistStatement, names: Iterable[str]) -> bool:
    parameters = {name: value for name, value in statement.parameters}
    return any(name in parameters for name in names)



def _format_metadata_value(value: Any) -> str:
    try:
        return _format_scalar(value)
    except SpiceRendererError:
        try:
            return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        except (TypeError, ValueError) as exc:
            raise SpiceRendererError(f"unsupported metadata value for SPICE rendering: {value!r}") from exc


def _format_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return format(value, ".15g")
    if isinstance(value, str):
        return value
    raise SpiceRendererError(f"unsupported scalar value for SPICE rendering: {value!r}")
