"""Bounded ngspice execution for trusted simulation decks."""

from __future__ import annotations

import base64
import json
import math
import os
import selectors
import signal
import stat
import subprocess
import tempfile
import time
from dataclasses import dataclass
from errno import ESRCH
from pathlib import Path
from typing import Any, Literal

from ai_electronics_lab.contracts.circuit_plan import (
    MAX_CAPACITANCE_FARADS,
    MAX_FREQUENCY_HZ,
    MAX_INPUT_VOLTAGE_VOLTS,
    MAX_RESISTANCE_OHMS,
    MIN_CAPACITANCE_FARADS,
    MIN_FREQUENCY_HZ,
    MIN_RESISTANCE_OHMS,
)

from .core.spice_renderer import _format_scalar
from .deck import MAX_AC_RUNS, SIMULATION_DECK_VERSION, SimulationDeck, SimulationDeckRun

SIMULATION_RUNNER_VERSION = "1.0"

_MAX_INPUT_BYTES = 64 * 1024
_MAX_STDOUT_BYTES = 256 * 1024
_MAX_STDERR_BYTES = 256 * 1024
_MAX_RAW_OUTPUT_BYTES = 2 * 1024 * 1024
_PER_RUN_TIMEOUT_SECONDS = 10.0
_TOTAL_TIMEOUT_SECONDS = 60.0
_PROCESS_GROUP_TERM_SECONDS = 0.5
_PROCESS_GROUP_KILL_SECONDS = 0.5
_NGSPICE_CANDIDATES = ("/usr/bin/ngspice", "/usr/local/bin/ngspice")
_INPUT_FILENAME = "input.cir"
_RAW_FILENAME = "output.raw"
_POPEN = subprocess.Popen

_PROBES = {
    "ac": ("transfer_function", "vin_voltage", "vout_voltage"),
    "dc": ("divider_ratio", "vin_voltage", "vout_voltage"),
}
_TRUSTED_TITLES = {"rc_low_pass", "rc_high_pass", "resistive_divider"}
_TOPOLOGY_LINES = {
    "rc_low_pass": (
        ("C1", "vout", "0", "capacitance"),
        ("R1", "vin", "vout", "resistance"),
        ("V1", "vin", "0", "ac_source"),
    ),
    "rc_high_pass": (
        ("C1", "vin", "vout", "capacitance"),
        ("R1", "vout", "0", "resistance"),
        ("V1", "vin", "0", "ac_source"),
    ),
    "resistive_divider": (
        ("R1", "vin", "vout", "resistance"),
        ("R2", "vout", "0", "resistance"),
        ("V1", "vin", "0", "dc_source"),
    ),
}


class SimulationRunnerError(RuntimeError):
    """Stable structured failure at the deck-to-ngspice boundary."""

    def __init__(self, code: str, path: tuple[str | int, ...], message: str) -> None:
        self.code = code
        self.path = path
        self.message = message
        location = ".".join(str(item) for item in path) or "<root>"
        super().__init__(f"{code} at {location}: {message}")

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "path": list(self.path), "message": self.message}


@dataclass(frozen=True, slots=True)
class SimulationRunEvidence:
    """Bounded raw execution evidence for one simulation run."""

    run_id: str
    analysis_kind: Literal["ac", "dc"]
    frequency_hz: float | int | None
    probe_names: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str
    raw_output: bytes

    def __post_init__(self) -> None:
        object.__setattr__(self, "probe_names", tuple(self.probe_names))
        object.__setattr__(self, "raw_output", bytes(self.raw_output))

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "analysis_kind": self.analysis_kind,
            "frequency_hz": self.frequency_hz,
            "probe_names": list(self.probe_names),
            "returncode": self.returncode,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "raw_output_base64": base64.b64encode(self.raw_output).decode("ascii"),
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
class SimulationExecutionEvidence:
    """Immutable ordered evidence for a complete deck execution."""

    version: str
    runs: tuple[SimulationRunEvidence, ...]

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


def run_simulation_deck(deck: SimulationDeck) -> SimulationExecutionEvidence:
    """Execute a defensively validated simulation deck with bounded ngspice."""

    try:
        validated_runs = _validate_deck(deck)
    except SimulationRunnerError:
        raise
    except (AttributeError, IndexError, KeyError, TypeError, ValueError, AssertionError) as exc:
        raise SimulationRunnerError(
            "runner.deck.malformed", (), "deck could not be validated"
        ) from exc
    executable = _resolve_executable()
    total_deadline = time.monotonic() + _TOTAL_TIMEOUT_SECONDS
    evidence = []
    for index, run in enumerate(validated_runs):
        if time.monotonic() >= total_deadline:
            _fail("runner.timeout.total", ("runs", index), "total execution timeout exceeded")
        evidence.append(_execute_run(executable, run, index, total_deadline))
    return SimulationExecutionEvidence(SIMULATION_RUNNER_VERSION, tuple(evidence))


def _validate_deck(deck: SimulationDeck) -> tuple[SimulationDeckRun, ...]:
    if type(deck) is not SimulationDeck:
        _fail("runner.deck.malformed", (), "deck must be a SimulationDeck")
    if type(deck.version) is not str:
        _fail("runner.deck.malformed", ("version",), "deck version must be a string")
    if deck.version != SIMULATION_DECK_VERSION:
        _fail("runner.version.unsupported", ("version",), "deck version is not supported")
    if type(deck.runs) is not tuple:
        _fail("runner.deck.malformed", ("runs",), "runs must be an immutable tuple")
    if not deck.runs:
        _fail("runner.deck.malformed", ("runs",), "at least one run is required")
    if len(deck.runs) > MAX_AC_RUNS:
        _fail("runner.deck.malformed", ("runs",), f"at most {MAX_AC_RUNS} runs are allowed")
    for index, run in enumerate(deck.runs):
        if type(run) is not SimulationDeckRun:
            _fail("runner.deck.malformed", ("runs", index), "run must be a SimulationDeckRun")

    first_kind = deck.runs[0].analysis_kind
    if type(first_kind) is not str:
        _fail(
            "runner.deck.malformed",
            ("runs", 0, "analysis_kind"),
            "analysis kind must be a string",
        )
    if first_kind not in _PROBES:
        _fail("runner.deck.malformed", ("runs", 0, "analysis_kind"), "analysis kind is invalid")
    if any(run.analysis_kind != first_kind for run in deck.runs):
        _fail("runner.deck.malformed", ("runs",), "runs must use one analysis kind")
    if first_kind == "dc" and len(deck.runs) != 1:
        _fail("runner.deck.malformed", ("runs",), "DC execution requires exactly one run")

    for index, run in enumerate(deck.runs):
        _validate_run(run, index)
    return deck.runs


def _validate_run(run: SimulationDeckRun, index: int) -> None:
    path = ("runs", index)
    if type(run.run_id) is not str:
        _fail("runner.deck.malformed", path + ("run_id",), "run_id must be a string")
    if type(run.analysis_kind) is not str:
        _fail(
            "runner.deck.malformed",
            path + ("analysis_kind",),
            "analysis kind must be a string",
        )
    if run.analysis_kind not in _PROBES:
        _fail("runner.deck.malformed", path + ("analysis_kind",), "analysis kind is invalid")
    expected_id = "dc-op" if run.analysis_kind == "dc" else f"ac-{index + 1:02d}"
    if run.run_id != expected_id:
        _fail("runner.deck.malformed", path + ("run_id",), "run_id is not trusted")
    if (
        type(run.probe_names) is not tuple
        or any(type(probe) is not str for probe in run.probe_names)
        or run.probe_names != _PROBES[run.analysis_kind]
    ):
        _fail("runner.deck.malformed", path + ("probe_names",), "probe names are not trusted")
    if run.analysis_kind == "dc":
        if run.frequency_hz is not None:
            _fail("runner.deck.malformed", path + ("frequency_hz",), "DC frequency must be None")
    else:
        _validate_number(
            run.frequency_hz,
            path + ("frequency_hz",),
            positive=True,
            minimum=MIN_FREQUENCY_HZ,
            maximum=MAX_FREQUENCY_HZ,
        )
    text = _validate_text(run.netlist_text, path + ("netlist_text",))
    _validate_netlist_text(text, run, index)


def _validate_text(value: Any, path: tuple[str | int, ...]) -> str:
    if type(value) is not str:
        _fail("runner.deck.malformed", path, "netlist_text must be a string")
    if "\x00" in value:
        _fail("runner.deck.malformed", path, "netlist_text must not contain NUL")
    if "\r" in value:
        _fail("runner.deck.malformed", path, "netlist_text must not contain carriage returns")
    if value.endswith("\n"):
        _fail("runner.deck.malformed", path, "netlist_text must not end with a newline")
    try:
        encoded = value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise SimulationRunnerError(
            "runner.deck.malformed", path, "netlist_text must be UTF-8 encodable"
        ) from exc
    if len(encoded) > _MAX_INPUT_BYTES:
        _fail("runner.deck.malformed", path, "netlist_text exceeds the trusted input size limit")
    if any(line == "" for line in value.split("\n")):
        _fail("runner.deck.malformed", path, "netlist_text must not contain blank lines")
    return value


def _validate_netlist_text(text: str, run: SimulationDeckRun, index: int) -> None:
    path = ("runs", index, "netlist_text")
    lines = text.split("\n")
    if len(lines) < 6:
        _fail("runner.deck.malformed", path, "netlist_text is incomplete")
    title_line = lines[0]
    if not title_line.startswith("* "):
        _fail("runner.deck.malformed", path, "title line is not a trusted comment")
    title = title_line[2:]
    if title not in _TRUSTED_TITLES:
        _fail("runner.deck.malformed", path, "title is not trusted")
    if (run.analysis_kind == "dc") != (title == "resistive_divider"):
        _fail("runner.deck.malformed", path, "topology and analysis do not match")

    directive = lines[-2]
    if run.analysis_kind == "dc":
        expected_directive = ".op"
    else:
        frequency = _format_scalar(run.frequency_hz)
        expected_directive = f".ac lin 1 {frequency} {frequency}"
    if directive != expected_directive or lines[-1] != ".end":
        _fail("runner.deck.malformed", path, "analysis directive or final .end is not trusted")
    if lines.count(".end") != 1:
        _fail("runner.deck.malformed", path, "netlist_text must contain exactly one .end")
    executable_directives = [line for line in lines if line.startswith(".")]
    if executable_directives != [expected_directive, ".end"]:
        _fail("runner.deck.malformed", path, "netlist_text contains an untrusted directive")

    component_lines = lines[-5:-2] if title != "resistive_divider" else lines[-5:-2]
    if len(component_lines) != 3:
        _fail("runner.deck.malformed", path, "component block is not trusted")
    for line in lines[1:-5]:
        if not line.startswith("* metadata: "):
            _fail("runner.deck.malformed", path, "metadata lines must remain comments")
    _validate_component_lines(component_lines, title, path)


def _validate_component_lines(
    lines: list[str], title: str, path: tuple[str | int, ...]
) -> None:
    expected = _TOPOLOGY_LINES[title]
    for line, shape in zip(lines, expected):
        pieces = line.split(" ")
        if shape[3] in {"resistance", "capacitance"}:
            if len(pieces) != 4 or tuple(pieces[:3]) != shape[:3]:
                _fail("runner.deck.malformed", path, "component line is not trusted")
            if shape[3] == "resistance":
                minimum, maximum = MIN_RESISTANCE_OHMS, MAX_RESISTANCE_OHMS
            else:
                minimum, maximum = MIN_CAPACITANCE_FARADS, MAX_CAPACITANCE_FARADS
            _validate_numeric_token(pieces[3], path, positive=True, minimum=minimum, maximum=maximum)
        elif shape[3] == "ac_source":
            if pieces != ["V1", "vin", "0", "AC", "1", "0"]:
                _fail("runner.deck.malformed", path, "AC source line is not trusted")
        else:
            if len(pieces) != 5 or pieces[:4] != ["V1", "vin", "0", "DC"]:
                _fail("runner.deck.malformed", path, "DC source line is not trusted")
            _validate_numeric_token(
                pieces[4],
                path,
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
    if type(value) not in (int, float):
        _fail("runner.deck.malformed", path, "value must be an int or float, excluding bool")
    if not math.isfinite(value):
        _fail("runner.deck.malformed", path, "value must be finite")
    _check_numeric_bounds(
        value,
        path,
        positive=positive,
        nonzero=nonzero,
        minimum=minimum,
        maximum=maximum,
        magnitude=magnitude,
    )


def _validate_numeric_token(
    token: str,
    path: tuple[str | int, ...],
    *,
    positive: bool = False,
    nonzero: bool = False,
    minimum: float | None = None,
    maximum: float | None = None,
    magnitude: bool = False,
) -> None:
    if type(token) is not str:
        _fail("runner.deck.malformed", path, "numeric token must be a string")
    lowered = token.lower()
    if lowered in {"true", "false", "nan", "inf", "+inf", "-inf", "infinity"}:
        _fail("runner.deck.malformed", path, "numeric token is not trusted")
    try:
        value = float(token)
    except ValueError as exc:
        raise SimulationRunnerError("runner.deck.malformed", path, "numeric token is malformed") from exc
    if not math.isfinite(value):
        _fail("runner.deck.malformed", path, "numeric token must be finite")
    _check_numeric_bounds(
        value,
        path,
        positive=positive,
        nonzero=nonzero,
        minimum=minimum,
        maximum=maximum,
        magnitude=magnitude,
    )
    if token != _format_scalar(value):
        _fail("runner.deck.malformed", path, "numeric token is not canonical")


def _check_numeric_bounds(
    value: float | int,
    path: tuple[str | int, ...],
    *,
    positive: bool,
    nonzero: bool,
    minimum: float | None,
    maximum: float | None,
    magnitude: bool,
) -> None:
    if positive and value <= 0:
        _fail("runner.deck.malformed", path, "value must be greater than zero")
    if nonzero and value == 0:
        _fail("runner.deck.malformed", path, "value must be nonzero")
    comparable = abs(value) if magnitude else value
    if minimum is not None and comparable < minimum:
        _fail("runner.deck.malformed", path, "value is below the trusted numeric range")
    if maximum is not None and comparable > maximum:
        _fail("runner.deck.malformed", path, "value is above the trusted numeric range")


def _resolve_executable() -> str:
    invalid_seen = False
    for candidate in _NGSPICE_CANDIDATES:
        path = Path(candidate)
        try:
            details = path.stat()
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise SimulationRunnerError(
                "runner.executable.invalid", (), "ngspice executable could not be inspected"
            ) from exc
        if not stat.S_ISREG(details.st_mode) or not os.access(path, os.X_OK):
            invalid_seen = True
            continue
        return str(path)
    if invalid_seen:
        _fail("runner.executable.invalid", (), "trusted ngspice candidate is not executable")
    _fail("runner.executable.missing", (), "trusted ngspice executable was not found")


def _execute_run(
    executable: str, run: SimulationDeckRun, index: int, total_deadline: float
) -> SimulationRunEvidence:
    path = ("runs", index)
    try:
        with tempfile.TemporaryDirectory(prefix="ai-electronics-lab-ngspice-") as tmpdir:
            return _execute_run_in_tmpdir(executable, run, path, tmpdir, total_deadline)
    except SimulationRunnerError:
        raise
    except OSError as exc:
        raise SimulationRunnerError("runner.io.failed", path, "temporary I/O failed") from exc


def _execute_run_in_tmpdir(
    executable: str,
    run: SimulationDeckRun,
    path: tuple[str | int, ...],
    tmpdir: str,
    total_deadline: float,
) -> SimulationRunEvidence:
    input_path = Path(tmpdir, _INPUT_FILENAME)
    raw_path = Path(tmpdir, _RAW_FILENAME)
    try:
        input_path.write_bytes(run.netlist_text.encode("utf-8"))
    except OSError as exc:
        raise SimulationRunnerError("runner.io.failed", path, "input deck write failed") from exc

    env = {"HOME": tmpdir, "TMPDIR": tmpdir, "LANG": "C", "LC_ALL": "C"}
    argv = [executable, "-n", "-b", "-r", _RAW_FILENAME, _INPUT_FILENAME]
    run_deadline = min(time.monotonic() + _PER_RUN_TIMEOUT_SECONDS, total_deadline)
    try:
        proc = _POPEN(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
            close_fds=True,
            start_new_session=True,
            cwd=tmpdir,
            env=env,
        )
    except OSError as exc:
        raise SimulationRunnerError(
            "runner.subprocess.start_failed", path, "ngspice process could not be started"
        ) from exc

    stdout_bytes, stderr_bytes = _communicate_bounded(proc, raw_path, path, run_deadline, total_deadline)
    _terminate_process_group(proc, path)
    returncode = proc.returncode
    if returncode != 0:
        raise SimulationRunnerError(
            "runner.exit.nonzero", path, "ngspice exited with a nonzero status"
        )
    try:
        if not raw_path.exists():
            _fail("runner.raw_output.missing", path, "ngspice did not produce raw output")
        if raw_path.stat().st_size > _MAX_RAW_OUTPUT_BYTES:
            _fail("runner.raw_output.overflow", path, "raw output exceeded the byte limit")
        raw_output = raw_path.read_bytes()
    except SimulationRunnerError:
        raise
    except OSError as exc:
        raise SimulationRunnerError("runner.io.failed", path, "raw output read failed") from exc
    return SimulationRunEvidence(
        run_id=run.run_id,
        analysis_kind=run.analysis_kind,
        frequency_hz=run.frequency_hz,
        probe_names=run.probe_names,
        returncode=returncode,
        stdout=stdout_bytes.decode("utf-8", errors="replace"),
        stderr=stderr_bytes.decode("utf-8", errors="replace"),
        raw_output=raw_output,
    )


def _communicate_bounded(
    proc: subprocess.Popen[bytes],
    raw_path: Path,
    path: tuple[str | int, ...],
    run_deadline: float,
    total_deadline: float,
) -> tuple[bytes, bytes]:
    selector = selectors.DefaultSelector()
    buffers: dict[int, bytearray] = {}
    stream_names: dict[int, str] = {}
    try:
        for stream, name in ((proc.stdout, "stdout"), (proc.stderr, "stderr")):
            if stream is None:
                continue
            os.set_blocking(stream.fileno(), False)
            selector.register(stream, selectors.EVENT_READ)
            buffers[stream.fileno()] = bytearray()
            stream_names[stream.fileno()] = name
        while selector.get_map() or proc.poll() is None:
            now = time.monotonic()
            if now >= total_deadline:
                _terminate_process_group(proc, path)
                _fail("runner.timeout.total", path, "total execution timeout exceeded")
            if now >= run_deadline:
                _terminate_process_group(proc, path)
                _fail("runner.timeout.per_run", path, "per-run timeout exceeded")
            _check_raw_size_while_running(raw_path, proc, path)
            timeout = max(0.0, min(0.05, run_deadline - now, total_deadline - now))
            try:
                events = selector.select(timeout)
            except OSError as exc:
                _terminate_process_group(proc, path)
                raise SimulationRunnerError(
                    "runner.io.failed", path, "process stream I/O failed"
                ) from exc
            if not events and proc.poll() is not None:
                try:
                    events = selector.select(0)
                except OSError as exc:
                    _terminate_process_group(proc, path)
                    raise SimulationRunnerError(
                        "runner.io.failed", path, "process stream I/O failed"
                    ) from exc
                if not events:
                    break
            for key, _ in events:
                try:
                    chunk = key.fileobj.read1(8192)
                except OSError as exc:
                    _terminate_process_group(proc, path)
                    raise SimulationRunnerError(
                        "runner.io.failed", path, "process stream I/O failed"
                    ) from exc
                if not chunk:
                    try:
                        selector.unregister(key.fileobj)
                    except (KeyError, OSError) as exc:
                        _terminate_process_group(proc, path)
                        raise SimulationRunnerError(
                            "runner.io.failed", path, "process stream I/O failed"
                        ) from exc
                    continue
                fileno = key.fileobj.fileno()
                name = stream_names[fileno]
                buffer = buffers[fileno]
                buffer.extend(chunk)
                limit = _MAX_STDOUT_BYTES if name == "stdout" else _MAX_STDERR_BYTES
                if len(buffer) > limit:
                    _terminate_process_group(proc, path)
                    code = "runner.stdout.overflow" if name == "stdout" else "runner.stderr.overflow"
                    _fail(code, path, f"{name} exceeded the byte limit")
        try:
            proc.wait(timeout=0)
        except subprocess.TimeoutExpired as exc:
            _terminate_process_group(proc, path)
            raise SimulationRunnerError(
                "runner.io.failed", path, "process completion could not be confirmed"
            ) from exc
        except OSError as exc:
            _terminate_process_group(proc, path)
            raise SimulationRunnerError(
                "runner.io.failed", path, "process completion could not be confirmed"
            ) from exc
        return bytes(_buffer_for(proc.stdout, buffers)), bytes(_buffer_for(proc.stderr, buffers))
    except SimulationRunnerError:
        raise
    except OSError as exc:
        _terminate_process_group(proc, path)
        raise SimulationRunnerError("runner.io.failed", path, "process stream I/O failed") from exc
    except BaseException:
        _terminate_process_group(proc, path)
        raise
    finally:
        try:
            selector.close()
        except OSError:
            pass
        for stream in (proc.stdout, proc.stderr):
            if stream is not None:
                try:
                    stream.close()
                except OSError:
                    pass


def _buffer_for(stream: Any, buffers: dict[int, bytearray]) -> bytearray:
    if stream is None:
        return bytearray()
    return buffers.get(stream.fileno(), bytearray())


def _check_raw_size_while_running(
    raw_path: Path, proc: subprocess.Popen[bytes], path: tuple[str | int, ...]
) -> None:
    try:
        size = raw_path.stat().st_size
    except FileNotFoundError:
        return
    except OSError as exc:
        _terminate_process_group(proc, path)
        raise SimulationRunnerError("runner.io.failed", path, "raw output stat failed") from exc
    if size > _MAX_RAW_OUTPUT_BYTES:
        _terminate_process_group(proc, path)
        _fail("runner.raw_output.overflow", path, "raw output exceeded the byte limit")


def _terminate_process_group(
    proc: subprocess.Popen[bytes], path: tuple[str | int, ...]
) -> None:
    pgid = proc.pid
    if pgid <= 0 or pgid == os.getpgrp():
        _fail("runner.io.failed", path, "process cleanup refused an unsafe process group")
    try:
        os.killpg(pgid, signal.SIGTERM)
    except ProcessLookupError:
        _reap_direct_child(proc, path, 0)
        return
    except OSError as exc:
        raise SimulationRunnerError("runner.io.failed", path, "process cleanup failed") from exc

    if _wait_for_process_group_exit(proc, pgid, path, _PROCESS_GROUP_TERM_SECONDS):
        return

    try:
        os.killpg(pgid, signal.SIGKILL)
    except ProcessLookupError:
        _reap_direct_child(proc, path, 0)
        return
    except OSError as exc:
        raise SimulationRunnerError("runner.io.failed", path, "process cleanup failed") from exc

    if not _wait_for_process_group_exit(proc, pgid, path, _PROCESS_GROUP_KILL_SECONDS):
        _fail("runner.io.failed", path, "process cleanup did not complete")


def _wait_for_process_group_exit(
    proc: subprocess.Popen[bytes],
    pgid: int,
    path: tuple[str | int, ...],
    timeout: float,
) -> bool:
    deadline = time.monotonic() + timeout
    while True:
        _reap_direct_child(proc, path, 0)
        if not _process_group_exists(pgid, path):
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(min(0.02, max(0.0, deadline - time.monotonic())))


def _reap_direct_child(
    proc: subprocess.Popen[bytes], path: tuple[str | int, ...], timeout: float
) -> None:
    if proc.poll() is not None:
        return
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        return
    except OSError as exc:
        raise SimulationRunnerError("runner.io.failed", path, "process cleanup failed") from exc


def _process_group_exists(pgid: int, path: tuple[str | int, ...]) -> bool:
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    except OSError as exc:
        if exc.errno == ESRCH:
            return False
        raise SimulationRunnerError("runner.io.failed", path, "process cleanup failed") from exc
    return True


def _fail(code: str, path: tuple[str | int, ...], message: str) -> None:
    raise SimulationRunnerError(code, path, message)


__all__ = [
    "SIMULATION_RUNNER_VERSION",
    "SimulationExecutionEvidence",
    "SimulationRunEvidence",
    "SimulationRunnerError",
    "run_simulation_deck",
]
