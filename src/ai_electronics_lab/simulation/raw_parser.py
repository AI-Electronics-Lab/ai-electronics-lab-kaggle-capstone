"""Bounded parser for ngspice binary raw execution evidence."""

from __future__ import annotations

import json
import math
import struct
import sys
from dataclasses import dataclass
from typing import Any, Literal

from ai_electronics_lab.contracts.circuit_plan import MAX_FREQUENCY_HZ, MIN_FREQUENCY_HZ

from .core.spice_renderer import _format_scalar
from .deck import MAX_AC_RUNS
from .runner import (
    SIMULATION_RUNNER_VERSION,
    SimulationExecutionEvidence,
    SimulationRunEvidence,
)

SIMULATION_RAW_PARSER_VERSION = "1.0"

_MAX_RAW_OUTPUT_BYTES = 2 * 1024 * 1024
_MAX_HEADER_BYTES = 64 * 1024
_MAX_HEADER_LINE_BYTES = 512
_MAX_VARIABLES = 64
_REQUIRED_POINTS = 1
_MAX_VARIABLE_NAME_BYTES = 128
_MAX_VARIABLE_TYPE_BYTES = 64

_AC_PROBES = ("transfer_function", "vin_voltage", "vout_voltage")
_DC_PROBES = ("divider_ratio", "vin_voltage", "vout_voltage")
_TITLE_TO_TOPOLOGY = {
    "* rc_low_pass": "rc_low_pass",
    "* rc_high_pass": "rc_high_pass",
    "* resistive_divider": "resistive_divider",
}


class SimulationRawParseError(ValueError):
    """Stable structured failure at the raw-evidence parser boundary."""

    def __init__(self, code: str, path: tuple[str | int, ...], message: str) -> None:
        self.code = code
        self.path = path
        self.message = message
        location = ".".join(str(item) for item in path) or "<root>"
        super().__init__(f"{code} at {location}: {message}")

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "path": list(self.path), "message": self.message}


@dataclass(frozen=True, slots=True)
class SimulationComplexValue:
    """One finite complex voltage value."""

    real: float
    imag: float

    def __post_init__(self) -> None:
        if type(self.real) is not float or type(self.imag) is not float:
            _fail("raw.evidence.malformed", (), "complex values must be built-in floats")
        if not math.isfinite(self.real) or not math.isfinite(self.imag):
            _fail("raw.value.non_finite", (), "complex values must be finite")

    def to_dict(self) -> dict[str, float]:
        return {"real": self.real, "imag": self.imag}

    def to_json(self) -> str:
        return _canonical_json(self.to_dict())


@dataclass(frozen=True, slots=True)
class SimulationRunMeasurements:
    """Trusted measurements extracted from one raw simulation run."""

    run_id: str
    topology: Literal["rc_low_pass", "rc_high_pass", "resistive_divider"]
    analysis_kind: Literal["ac", "dc"]
    frequency_hz: float | int | None
    vin_voltage: SimulationComplexValue
    vout_voltage: SimulationComplexValue

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "topology": self.topology,
            "analysis_kind": self.analysis_kind,
            "frequency_hz": self.frequency_hz,
            "vin_voltage": self.vin_voltage.to_dict(),
            "vout_voltage": self.vout_voltage.to_dict(),
        }

    def to_json(self) -> str:
        return _canonical_json(self.to_dict())


@dataclass(frozen=True, slots=True)
class SimulationParsedResults:
    """Ordered parsed measurements for a complete simulation execution."""

    version: str
    runs: tuple[SimulationRunMeasurements, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "runs", tuple(self.runs))

    def to_dict(self) -> dict[str, Any]:
        return {"version": self.version, "runs": [run.to_dict() for run in self.runs]}

    def to_json(self) -> str:
        return _canonical_json(self.to_dict())


def parse_simulation_execution_evidence(
    evidence: SimulationExecutionEvidence,
) -> SimulationParsedResults:
    """Parse bounded ngspice binary raw evidence into immutable voltage measurements."""

    try:
        _check_runtime()
        runs = _validate_evidence(evidence)
        parsed = tuple(_parse_run(run, index) for index, run in enumerate(runs))
        return SimulationParsedResults(SIMULATION_RAW_PARSER_VERSION, parsed)
    except SimulationRawParseError:
        raise
    except (AttributeError, IndexError, KeyError, TypeError, ValueError, AssertionError) as exc:
        raise SimulationRawParseError(
            "raw.evidence.malformed", (), "evidence could not be parsed"
        ) from exc


parse_simulation_execution_evidence.__annotations__ = {
    "evidence": SimulationExecutionEvidence,
    "return": SimulationParsedResults,
}


def _validate_evidence(
    evidence: SimulationExecutionEvidence,
) -> tuple[SimulationRunEvidence, ...]:
    if type(evidence) is not SimulationExecutionEvidence:
        _fail("raw.evidence.malformed", (), "evidence must be SimulationExecutionEvidence")
    if type(evidence.version) is not str:
        _fail("raw.evidence.malformed", ("version",), "evidence version must be a string")
    if evidence.version != SIMULATION_RUNNER_VERSION:
        _fail("raw.version.unsupported", ("version",), "evidence version is not supported")
    if type(evidence.runs) is not tuple:
        _fail("raw.evidence.malformed", ("runs",), "runs must be an immutable tuple")
    if not evidence.runs:
        _fail("raw.evidence.malformed", ("runs",), "at least one run is required")
    if len(evidence.runs) > MAX_AC_RUNS:
        _fail("raw.evidence.malformed", ("runs",), f"at most {MAX_AC_RUNS} runs are allowed")
    for index, run in enumerate(evidence.runs):
        if type(run) is not SimulationRunEvidence:
            _fail("raw.evidence.malformed", ("runs", index), "run must be SimulationRunEvidence")
    for index, run in enumerate(evidence.runs):
        _validate_run_evidence(run, index)

    first_kind = evidence.runs[0].analysis_kind
    if any(run.analysis_kind != first_kind for run in evidence.runs):
        _fail("raw.evidence.malformed", ("runs",), "runs must use one analysis kind")
    if first_kind == "dc" and len(evidence.runs) != 1:
        _fail("raw.evidence.malformed", ("runs",), "DC evidence requires exactly one run")

    return evidence.runs


def _validate_run_evidence(run: SimulationRunEvidence, index: int) -> None:
    path = ("runs", index)
    if type(run.run_id) is not str:
        _fail("raw.evidence.malformed", path + ("run_id",), "run_id must be a string")
    if type(run.analysis_kind) is not str or run.analysis_kind not in {"ac", "dc"}:
        _fail("raw.evidence.malformed", path + ("analysis_kind",), "analysis kind is invalid")
    expected_id = "dc-op" if run.analysis_kind == "dc" else f"ac-{index + 1:02d}"
    if run.run_id != expected_id:
        _fail("raw.evidence.malformed", path + ("run_id",), "run_id is not trusted")
    expected_probes = _DC_PROBES if run.analysis_kind == "dc" else _AC_PROBES
    if type(run.probe_names) is not tuple:
        _fail("raw.evidence.malformed", path + ("probe_names",), "probe names are not trusted")
    if len(run.probe_names) != len(expected_probes):
        _fail("raw.evidence.malformed", path + ("probe_names",), "probe names are not trusted")
    if any(type(probe) is not str for probe in run.probe_names) or run.probe_names != expected_probes:
        _fail("raw.evidence.malformed", path + ("probe_names",), "probe names are not trusted")
    if type(run.returncode) is not int or run.returncode != 0:
        _fail("raw.evidence.malformed", path + ("returncode",), "return code must be zero")
    if type(run.stdout) is not str:
        _fail("raw.evidence.malformed", path + ("stdout",), "stdout must be a string")
    if type(run.stderr) is not str:
        _fail("raw.evidence.malformed", path + ("stderr",), "stderr must be a string")
    if run.analysis_kind == "dc":
        if run.frequency_hz is not None:
            _fail("raw.evidence.malformed", path + ("frequency_hz",), "DC frequency must be None")
    else:
        _validate_frequency(run.frequency_hz, path + ("frequency_hz",))
    if type(run.raw_output) is not bytes:
        _fail("raw.evidence.malformed", path + ("raw_output",), "raw output must be bytes")
    if not run.raw_output:
        _fail("raw.output.empty", path + ("raw_output",), "raw output is empty")
    if len(run.raw_output) > _MAX_RAW_OUTPUT_BYTES:
        _fail("raw.output.oversized", path + ("raw_output",), "raw output exceeds the byte limit")


def _validate_frequency(value: Any, path: tuple[str | int, ...]) -> None:
    if type(value) not in (int, float):
        _fail("raw.evidence.malformed", path, "frequency must be an int or float")
    if type(value) is int:
        if value <= 0:
            _fail("raw.evidence.malformed", path, "frequency must be finite and positive")
    elif not math.isfinite(value) or value <= 0:
        _fail("raw.evidence.malformed", path, "frequency must be finite and positive")
    if value < MIN_FREQUENCY_HZ or value > MAX_FREQUENCY_HZ:
        _fail("raw.evidence.malformed", path, "frequency is outside the trusted range")


@dataclass(frozen=True, slots=True)
class _Variable:
    index: int
    name: str
    kind: str


@dataclass(frozen=True, slots=True)
class _RawFile:
    title: str
    plotname: str
    flags: str
    variables: tuple[_Variable, ...]
    payload: bytes


def _parse_run(run: SimulationRunEvidence, index: int) -> SimulationRunMeasurements:
    path = ("runs", index, "raw_output")
    raw = _parse_raw_file(run.raw_output, path)
    topology = _validate_title_plot_flags(raw, run.analysis_kind, path)
    if run.analysis_kind == "ac":
        vin, vout = _parse_ac_values(raw, run.frequency_hz, path)
    else:
        vin, vout = _parse_dc_values(raw, path)
    return SimulationRunMeasurements(run.run_id, topology, run.analysis_kind, run.frequency_hz, vin, vout)


def _parse_raw_file(raw: bytes, path: tuple[str | int, ...]) -> _RawFile:
    delimiter = b"Binary:\n"
    delimiter_index = _find_complete_header_line(raw, delimiter)
    header_prefix = raw if delimiter_index < 0 else raw[:delimiter_index]
    if _contains_complete_header_line(header_prefix, b"Values:"):
        _fail("raw.format.unsupported", path + ("header",), "ASCII Values mode is not supported")
    if delimiter_index < 0:
        _fail("raw.format.unsupported", path + ("header",), "Binary delimiter is missing")
    header_end = delimiter_index + len(delimiter)
    if header_end > _MAX_HEADER_BYTES:
        _fail("raw.header.oversized", path + ("header",), "raw header exceeds the byte limit")
    header_bytes = raw[:header_end]
    if b"\x00" in header_bytes or b"\r" in header_bytes:
        _fail("raw.header.invalid", path + ("header",), "raw header contains invalid bytes")
    for line in header_bytes.split(b"\n"):
        if len(line) > _MAX_HEADER_LINE_BYTES:
            _fail("raw.header.oversized", path + ("header",), "raw header line exceeds the limit")
    try:
        header_text = header_bytes.decode("ascii")
    except UnicodeDecodeError as exc:
        raise SimulationRawParseError(
            "raw.header.invalid", path + ("header",), "raw header must be ASCII"
        ) from exc

    lines = header_text.split("\n")
    if lines[-1] != "":
        _fail("raw.header.invalid", path + ("header",), "raw header is malformed")
    lines = lines[:-1]
    if len(lines) < 8:
        _fail("raw.header.invalid", path + ("header",), "raw header is incomplete")
    title = _required_field(lines, 0, "Title", path + ("header",))
    _required_field(lines, 1, "Date", path + ("header",))
    plotname = _required_field(lines, 2, "Plotname", path + ("header",))
    flags = _required_field(lines, 3, "Flags", path + ("header",))
    variable_count = _parse_count(_required_field(lines, 4, "No. Variables", path + ("header",)), path + ("variables",))
    point_count = _parse_count(_required_field(lines, 5, "No. Points", path + ("header",)), path + ("points",))
    if point_count != _REQUIRED_POINTS:
        _fail("raw.count.invalid", path + ("points",), "raw file must contain exactly one point")
    if variable_count <= 0 or variable_count > _MAX_VARIABLES:
        _fail("raw.count.invalid", path + ("variables",), "variable count is outside the limit")
    if lines[6] != "Variables:":
        _fail("raw.header.invalid", path + ("header",), "Variables section is missing")
    expected_binary_line = 7 + variable_count
    if len(lines) != expected_binary_line + 1 or lines[expected_binary_line] != "Binary:":
        _fail("raw.header.invalid", path + ("header",), "raw header structure is invalid")
    variables = tuple(
        _parse_variable_line(lines[7 + offset], offset, path + ("variables",))
        for offset in range(variable_count)
    )
    _validate_variable_table(variables, path + ("variables",))
    return _RawFile(title, plotname, flags, variables, raw[header_end:])


def _find_complete_header_line(raw: bytes, marker_line: bytes) -> int:
    start = 0
    while True:
        index = raw.find(marker_line, start)
        if index < 0:
            return -1
        if index == 0 or raw[index - 1] == 0x0A:
            return index
        start = index + 1


def _contains_complete_header_line(header_prefix: bytes, marker: bytes) -> bool:
    for line in header_prefix.split(b"\n"):
        if line == marker:
            return True
    return False


def _required_field(
    lines: list[str], index: int, field: str, path: tuple[str | int, ...]
) -> str:
    prefix = f"{field}: "
    if index >= len(lines) or not lines[index].startswith(prefix):
        _fail("raw.header.invalid", path, "mandatory header fields are missing or reordered")
    value = lines[index][len(prefix) :]
    if value == "":
        _fail("raw.header.invalid", path, "mandatory header field is empty")
    if any(line.startswith(prefix) for line in lines[index + 1 :]):
        _fail("raw.header.invalid", path, "duplicate mandatory header field")
    return value


def _parse_count(value: str, path: tuple[str | int, ...]) -> int:
    stripped = value.strip()
    if not stripped.isdecimal():
        _fail("raw.count.invalid", path, "count field is malformed")
    return int(stripped)


def _parse_variable_line(line: str, expected_index: int, path: tuple[str | int, ...]) -> _Variable:
    pieces = line.split("\t")
    if len(pieces) != 4 or pieces[0] != "":
        _fail("raw.variables.invalid", path, "variable row is malformed")
    index_text, name, kind = pieces[1:]
    if not index_text.isdecimal():
        _fail("raw.variables.invalid", path, "variable index is malformed")
    index = int(index_text)
    if index != expected_index:
        _fail("raw.variables.invalid", path, "variable indices must be contiguous")
    _validate_safe_token(name, _MAX_VARIABLE_NAME_BYTES, path)
    _validate_safe_token(kind, _MAX_VARIABLE_TYPE_BYTES, path)
    return _Variable(index, name, kind)


def _validate_safe_token(value: str, limit: int, path: tuple[str | int, ...]) -> None:
    try:
        encoded = value.encode("ascii")
    except UnicodeEncodeError as exc:
        raise SimulationRawParseError(
            "raw.variables.invalid", path, "variable token must be ASCII"
        ) from exc
    if not encoded or len(encoded) > limit:
        _fail("raw.variables.invalid", path, "variable token length is invalid")
    if any(byte <= 32 or byte >= 127 for byte in encoded):
        _fail("raw.variables.invalid", path, "variable token contains unsafe characters")


def _validate_variable_table(
    variables: tuple[_Variable, ...], path: tuple[str | int, ...]
) -> None:
    names = [variable.name for variable in variables]
    if len(set(names)) != len(names):
        _fail("raw.variables.invalid", path, "variable names must be unique")


def _validate_title_plot_flags(
    raw: _RawFile, analysis_kind: str, path: tuple[str | int, ...]
) -> Literal["rc_low_pass", "rc_high_pass", "resistive_divider"]:
    if raw.title not in _TITLE_TO_TOPOLOGY:
        _fail("raw.title.invalid", path + ("header",), "raw title is not trusted")
    topology = _TITLE_TO_TOPOLOGY[raw.title]
    if (analysis_kind == "dc") != (topology == "resistive_divider"):
        _fail("raw.title.invalid", path + ("header",), "raw title does not match analysis")
    if analysis_kind == "ac":
        if raw.plotname != "AC Analysis":
            _fail("raw.plot.invalid", path + ("header",), "raw plot is not trusted")
        if raw.flags != "complex":
            _fail("raw.flags.invalid", path + ("header",), "raw flags are not trusted")
    else:
        if raw.plotname != "Operating Point":
            _fail("raw.plot.invalid", path + ("header",), "raw plot is not trusted")
        if raw.flags != "real":
            _fail("raw.flags.invalid", path + ("header",), "raw flags are not trusted")
    return topology


def _parse_ac_values(
    raw: _RawFile, trusted_frequency: float | int | None, path: tuple[str | int, ...]
) -> tuple[SimulationComplexValue, SimulationComplexValue]:
    if trusted_frequency is None:
        _fail("raw.evidence.malformed", path, "AC frequency is missing")
    doubles = _unpack_payload(raw.payload, len(raw.variables) * 2, path)
    values = {variable.name: (doubles[variable.index * 2], doubles[variable.index * 2 + 1]) for variable in raw.variables}
    frequency_var = _required_vector(raw.variables, "frequency", "frequency", path)
    _required_vector(raw.variables, "v(vin)", "voltage", path)
    _required_vector(raw.variables, "v(vout)", "voltage", path)
    frequency_real, frequency_imag = values[frequency_var.name]
    expected_frequency = float(_format_scalar(trusted_frequency))
    if frequency_real != expected_frequency:
        _fail("raw.frequency.mismatch", path + ("frequency",), "raw frequency does not match evidence")
    if frequency_imag != 0.0 and abs(frequency_imag) >= sys.float_info.min:
        _fail("raw.frequency.mismatch", path + ("frequency",), "raw frequency imaginary slot is invalid")
    vin_real, vin_imag = values["v(vin)"]
    vout_real, vout_imag = values["v(vout)"]
    return SimulationComplexValue(vin_real, vin_imag), SimulationComplexValue(vout_real, vout_imag)


def _parse_dc_values(
    raw: _RawFile, path: tuple[str | int, ...]
) -> tuple[SimulationComplexValue, SimulationComplexValue]:
    doubles = _unpack_payload(raw.payload, len(raw.variables), path)
    variables_by_name = {variable.name: variable for variable in raw.variables}
    _required_vector(raw.variables, "v(vin)", "voltage", path)
    _required_vector(raw.variables, "v(vout)", "voltage", path)
    vin = doubles[variables_by_name["v(vin)"].index]
    vout = doubles[variables_by_name["v(vout)"].index]
    return SimulationComplexValue(vin, 0.0), SimulationComplexValue(vout, 0.0)


def _required_vector(
    variables: tuple[_Variable, ...],
    name: str,
    kind: str,
    path: tuple[str | int, ...],
) -> _Variable:
    matches = [variable for variable in variables if variable.name == name]
    if not matches:
        _fail("raw.vector.missing", path + ("variables",), "required vector is missing")
    if len(matches) > 1:
        _fail("raw.vector.duplicate", path + ("variables",), "required vector is duplicated")
    variable = matches[0]
    if variable.kind != kind:
        _fail("raw.variables.invalid", path + ("variables",), "required vector type is invalid")
    return variable


def _unpack_payload(
    payload: bytes, expected_double_count: int, path: tuple[str | int, ...]
) -> tuple[float, ...]:
    expected_bytes = expected_double_count * 8
    if len(payload) < expected_bytes:
        _fail("raw.payload.truncated", path + ("payload",), "binary payload is truncated")
    if len(payload) > expected_bytes:
        _fail("raw.payload.trailing", path + ("payload",), "binary payload has trailing bytes")
    try:
        values = struct.unpack(f"@{expected_double_count}d", payload)
    except struct.error as exc:
        raise SimulationRawParseError(
            "raw.payload.truncated", path + ("payload",), "binary payload is malformed"
        ) from exc
    if any(not math.isfinite(value) for value in values):
        _fail("raw.value.non_finite", path + ("payload",), "binary payload contains non-finite values")
    return values


def _check_runtime() -> None:
    if struct.calcsize("@d") != 8:
        _fail("raw.format.unsupported", (), "native double size is unsupported")
    try:
        roundtrip = struct.unpack("@d", struct.pack("@d", 1.0))[0]
    except struct.error as exc:
        raise SimulationRawParseError(
            "raw.format.unsupported", (), "native double packing is unsupported"
        ) from exc
    if roundtrip != 1.0:
        _fail("raw.format.unsupported", (), "native double packing is unsupported")


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _fail(code: str, path: tuple[str | int, ...], message: str) -> None:
    raise SimulationRawParseError(code, path, message)


__all__ = [
    "SIMULATION_RAW_PARSER_VERSION",
    "SimulationComplexValue",
    "SimulationParsedResults",
    "SimulationRawParseError",
    "SimulationRunMeasurements",
    "parse_simulation_execution_evidence",
]
