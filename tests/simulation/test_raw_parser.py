from __future__ import annotations

import builtins
import inspect
import json
import math
import os
import struct
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest

import ai_electronics_lab.simulation as simulation
import ai_electronics_lab.simulation.raw_parser as raw_parser_module
from ai_electronics_lab.contracts import CircuitPlan
from ai_electronics_lab.simulation import (
    SIMULATION_RAW_PARSER_VERSION,
    SIMULATION_RUNNER_VERSION,
    SimulationComplexValue,
    SimulationExecutionEvidence,
    SimulationParsedResults,
    SimulationRawParseError,
    SimulationRunEvidence,
    SimulationRunMeasurements,
    build_simulation_assembly_from_plan,
    build_simulation_deck_from_assembly,
    parse_simulation_execution_evidence,
    run_simulation_deck,
)

DATE = "Tue Jun 23 09:02:54  2026"


def raw_file(
    *,
    title: str = "* rc_low_pass",
    plotname: str = "AC Analysis",
    flags: str = "complex",
    variables: tuple[tuple[str, str], ...] = (
        ("frequency", "frequency"),
        ("v(vout)", "voltage"),
        ("v(vin)", "voltage"),
        ("i(v1)", "current"),
    ),
    points: str = "1       ",
    date: str = DATE,
    values: tuple[float, ...] | None = None,
) -> bytes:
    if values is None:
        if flags == "complex":
            values = (10.0, 0.0, 0.9, -0.1, 1.0, 0.0, -0.001, -0.002)
        else:
            values = (5.0, 3.333333333333333, -0.0001666666666666667)
    lines = [
        f"Title: {title}",
        f"Date: {date}",
        f"Plotname: {plotname}",
        f"Flags: {flags}",
        f"No. Variables: {len(variables)}",
        f"No. Points: {points}",
        "Variables:",
    ]
    lines.extend(f"\t{index}\t{name}\t{kind}" for index, (name, kind) in enumerate(variables))
    lines.append("Binary:")
    header = "\n".join(lines).encode("ascii") + b"\n"
    return header + struct.pack(f"@{len(values)}d", *values)


def finite_values_marker_double() -> bytes:
    candidates = [b"Values:" + bytes([suffix]) for suffix in range(256)]
    candidates.extend(bytes([prefix]) + b"Values:" for prefix in range(256))
    for candidate in candidates:
        if math.isfinite(struct.unpack("@d", candidate)[0]):
            return candidate
    raise AssertionError("no finite native double candidate containing Values: was found")


def finite_binary_marker_double() -> bytes:
    candidates = [b"Binary:" + bytes([suffix]) for suffix in range(256)]
    candidates.extend(bytes([prefix]) + b"Binary:" for prefix in range(256))
    candidates.append(b"Binary:\n")
    for candidate in candidates:
        if math.isfinite(struct.unpack("@d", candidate)[0]):
            return candidate
    raise AssertionError("no finite native double candidate containing Binary: was found")


def raw_file_with_ignored_current_bytes(ignored_real: bytes) -> bytes:
    assert len(ignored_real) == 8
    assert math.isfinite(struct.unpack("@d", ignored_real)[0])
    header = raw_file().split(b"Binary:\n", 1)[0] + b"Binary:\n"
    trusted_payload = struct.pack("@6d", 10.0, 0.0, 0.9, -0.1, 1.0, 0.0)
    ignored_imag = struct.pack("@d", -0.002)
    return header + trusted_payload + ignored_real + ignored_imag


def evidence_for(
    raw: bytes,
    *,
    run_id: str = "ac-01",
    analysis_kind: str = "ac",
    frequency_hz: float | int | None = 10.0,
    probe_names: tuple[str, ...] | None = None,
) -> SimulationExecutionEvidence:
    if probe_names is None:
        probe_names = (
            ("divider_ratio", "vin_voltage", "vout_voltage")
            if analysis_kind == "dc"
            else ("transfer_function", "vin_voltage", "vout_voltage")
        )
    return SimulationExecutionEvidence(
        SIMULATION_RUNNER_VERSION,
        (
            SimulationRunEvidence(
                run_id,
                analysis_kind,
                frequency_hz,
                probe_names,
                0,
                "stdout must not appear",
                "stderr must not appear",
                raw,
            ),
        ),
    )


def parse(raw: bytes, **kwargs) -> SimulationParsedResults:
    return parse_simulation_execution_evidence(evidence_for(raw, **kwargs))


def assert_error(raw: bytes, code: str, **kwargs) -> SimulationRawParseError:
    with pytest.raises(SimulationRawParseError) as caught:
        parse(raw, **kwargs)
    assert caught.value.code == code
    assert "secret" not in caught.value.message
    assert DATE not in caught.value.message
    return caught.value


def test_public_exports_version_and_exact_signature():
    assert SIMULATION_RAW_PARSER_VERSION == "1.0"
    assert simulation.SIMULATION_RAW_PARSER_VERSION == "1.0"
    assert simulation.SimulationRawParseError is SimulationRawParseError
    assert simulation.SimulationComplexValue is SimulationComplexValue
    assert simulation.SimulationRunMeasurements is SimulationRunMeasurements
    assert simulation.SimulationParsedResults is SimulationParsedResults
    assert simulation.parse_simulation_execution_evidence is parse_simulation_execution_evidence

    signature = inspect.signature(parse_simulation_execution_evidence)
    assert list(signature.parameters) == ["evidence"]
    assert signature.parameters["evidence"].annotation is SimulationExecutionEvidence
    assert signature.return_annotation is SimulationParsedResults


def test_frozen_dataclasses_tuple_conversion_and_canonical_json():
    complex_value = SimulationComplexValue(1.0, -0.5)
    run = SimulationRunMeasurements(
        "ac-01", "rc_low_pass", "ac", 10, complex_value, SimulationComplexValue(0.9, -0.1)
    )
    results = SimulationParsedResults("1.0", [run])

    assert results.runs == (run,)
    assert complex_value.to_json() == '{"imag":-0.5,"real":1.0}'
    assert run.to_json() == json.dumps(
        run.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )
    assert results.to_json() == json.dumps(
        results.to_dict(),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    with pytest.raises(FrozenInstanceError):
        complex_value.real = 2.0
    with pytest.raises(FrozenInstanceError):
        results.version = "changed"


def test_successful_ac_low_pass_parsing():
    results = parse(raw_file())

    assert results.version == "1.0"
    assert len(results.runs) == 1
    run = results.runs[0]
    assert run.run_id == "ac-01"
    assert run.topology == "rc_low_pass"
    assert run.analysis_kind == "ac"
    assert run.frequency_hz == 10.0
    assert run.vin_voltage == SimulationComplexValue(1.0, 0.0)
    assert run.vout_voltage == SimulationComplexValue(0.9, -0.1)


def test_successful_ac_high_pass_parsing_with_different_vector_order():
    raw = raw_file(
        title="* rc_high_pass",
        variables=(
            ("frequency", "frequency"),
            ("v(vin)", "voltage"),
            ("i(v1)", "current"),
            ("v(vout)", "voltage"),
        ),
        values=(100.0, 0.0, 1.0, 0.0, -0.0002, -0.0004, 0.2, 0.4),
    )

    results = parse(raw, frequency_hz=100)

    run = results.runs[0]
    assert run.topology == "rc_high_pass"
    assert run.frequency_hz == 100
    assert run.vin_voltage == SimulationComplexValue(1.0, 0.0)
    assert run.vout_voltage == SimulationComplexValue(0.2, 0.4)


def test_successful_dc_operating_point_parsing():
    raw = raw_file(
        title="* resistive_divider",
        plotname="Operating Point",
        flags="real",
        variables=(("v(vin)", "voltage"), ("v(vout)", "voltage"), ("i(v1)", "current")),
        values=(5.0, 3.333333333333333, -0.0001666666666666667),
    )

    results = parse(raw, run_id="dc-op", analysis_kind="dc", frequency_hz=None)

    run = results.runs[0]
    assert run.topology == "resistive_divider"
    assert run.analysis_kind == "dc"
    assert run.frequency_hz is None
    assert run.vin_voltage == SimulationComplexValue(5.0, 0.0)
    assert run.vout_voltage == SimulationComplexValue(3.333333333333333, 0.0)


def test_multiple_ac_runs_preserve_order_and_frequency_representation():
    evidence = SimulationExecutionEvidence(
        SIMULATION_RUNNER_VERSION,
        (
            evidence_for(raw_file(values=(10.0, 0.0, 0.9, -0.1, 1.0, 0.0, 0.0, 0.0))).runs[0],
            SimulationRunEvidence(
                "ac-02",
                "ac",
                100,
                ("transfer_function", "vin_voltage", "vout_voltage"),
                0,
                "",
                "",
                raw_file(values=(100.0, 0.0, 0.5, -0.5, 1.0, 0.0, 0.0, 0.0)),
            ),
        ),
    )

    results = parse_simulation_execution_evidence(evidence)

    assert [run.run_id for run in results.runs] == ["ac-01", "ac-02"]
    assert [run.frequency_hz for run in results.runs] == [10.0, 100]


def test_real_and_complex_payload_layout_and_subnormal_frequency_imaginary():
    subnormal = math.nextafter(0.0, 1.0)
    raw = raw_file(values=(10.0, subnormal, 0.9, -0.1, 1.0, 0.0, -0.001, -0.002))

    results = parse(raw)

    assert results.runs[0].vin_voltage == SimulationComplexValue(1.0, 0.0)


@pytest.mark.parametrize(
    ("title", "analysis", "code"),
    [
        ("* rc_low_pass", "dc", "raw.title.invalid"),
        ("* resistive_divider", "ac", "raw.title.invalid"),
    ],
)
def test_trusted_title_to_analysis_mapping(title, analysis, code):
    raw = raw_file(title=title)
    kwargs = {"run_id": "dc-op", "analysis_kind": "dc", "frequency_hz": None} if analysis == "dc" else {}
    with pytest.raises(SimulationRawParseError) as caught:
        parse(raw, **kwargs)
    assert caught.value.code == code


def test_exact_canonical_frequency_matching():
    assert parse(raw_file(values=(10.0, 0.0, 0.9, -0.1, 1.0, 0.0, 0.0, 0.0))).runs[0]
    assert_error(
        raw_file(values=(10.000000000000002, 0.0, 0.9, -0.1, 1.0, 0.0, 0.0, 0.0)),
        "raw.frequency.mismatch",
    )


class HostileAnalysisKind:
    def __init__(self) -> None:
        self.eq_called = False
        self.ne_called = False

    def __eq__(self, other):
        self.eq_called = True
        raise RuntimeError("hostile equality must not run")

    def __ne__(self, other):
        self.ne_called = True
        raise RuntimeError("hostile inequality must not run")


def two_ac_run_evidence(second_analysis_kind) -> SimulationExecutionEvidence:
    second_run = SimulationRunEvidence(
        "ac-02",
        "ac",
        100,
        ("transfer_function", "vin_voltage", "vout_voltage"),
        0,
        "",
        "",
        raw_file(values=(100.0, 0.0, 0.5, -0.5, 1.0, 0.0, 0.0, 0.0)),
    )
    object.__setattr__(second_run, "analysis_kind", second_analysis_kind)
    return SimulationExecutionEvidence(
        SIMULATION_RUNNER_VERSION,
        (evidence_for(raw_file()).runs[0], second_run),
    )


def test_second_run_hostile_analysis_kind_is_rejected_before_comparison(monkeypatch):
    hostile = HostileAnalysisKind()
    raw_parse_called = False

    def fail_if_raw_parsed(*args):
        nonlocal raw_parse_called
        raw_parse_called = True
        raise AssertionError("raw parsing should not be reached")

    monkeypatch.setattr(raw_parser_module, "_parse_raw_file", fail_if_raw_parsed)

    with pytest.raises(SimulationRawParseError) as caught:
        parse_simulation_execution_evidence(two_ac_run_evidence(hostile))

    assert caught.value.code == "raw.evidence.malformed"
    assert caught.value.path == ("runs", 1, "analysis_kind")
    assert not hostile.eq_called
    assert not hostile.ne_called
    assert not raw_parse_called


def test_second_run_unhashable_analysis_kind_reports_precise_path(monkeypatch):
    raw_parse_called = False

    def fail_if_raw_parsed(*args):
        nonlocal raw_parse_called
        raw_parse_called = True
        raise AssertionError("raw parsing should not be reached")

    monkeypatch.setattr(raw_parser_module, "_parse_raw_file", fail_if_raw_parsed)

    with pytest.raises(SimulationRawParseError) as caught:
        parse_simulation_execution_evidence(two_ac_run_evidence(["ac"]))

    assert caught.value.code == "raw.evidence.malformed"
    assert caught.value.path == ("runs", 1, "analysis_kind")
    assert not raw_parse_called


def test_oversized_probe_tuple_is_rejected_before_element_traversal(monkeypatch):
    raw_parse_called = False

    def fail_if_raw_parsed(*args):
        nonlocal raw_parse_called
        raw_parse_called = True
        raise AssertionError("raw parsing should not be reached")

    evidence = evidence_for(
        raw_file(),
        probe_names=("transfer_function", "vin_voltage", "vout_voltage", *("extra",) * 10_000),
    )
    type_call_count = 0

    def counting_type(value):
        nonlocal type_call_count
        type_call_count += 1
        return builtins.type(value)

    monkeypatch.setattr(raw_parser_module, "_parse_raw_file", fail_if_raw_parsed)
    monkeypatch.setattr(raw_parser_module, "type", counting_type, raising=False)

    with pytest.raises(SimulationRawParseError) as caught:
        parse_simulation_execution_evidence(evidence)

    assert caught.value.code == "raw.evidence.malformed"
    assert caught.value.path == ("runs", 0, "probe_names")
    assert type_call_count < 20
    assert not raw_parse_called


@pytest.mark.parametrize(
    "frequency",
    [
        10**10000,
        -(10**10000),
        True,
    ],
    ids=["huge-positive", "huge-negative", "boolean"],
)
def test_invalid_large_integer_and_boolean_frequencies_are_rejected_before_raw_parsing(
    monkeypatch,
    frequency,
):
    raw_parse_called = False

    def fail_if_raw_parsed(*args):
        nonlocal raw_parse_called
        raw_parse_called = True
        raise AssertionError("raw parsing should not be reached")

    monkeypatch.setattr(raw_parser_module, "_parse_raw_file", fail_if_raw_parsed)

    run = evidence_for(raw_file()).runs[0]
    corrupted = replace(run)
    object.__setattr__(corrupted, "frequency_hz", frequency)

    evidence = SimulationExecutionEvidence(
        SIMULATION_RUNNER_VERSION,
        (corrupted,),
    )

    with pytest.raises(SimulationRawParseError) as caught:
        parse_simulation_execution_evidence(evidence)

    assert caught.value.code == "raw.evidence.malformed"
    assert caught.value.path == ("runs", 0, "frequency_hz")
    assert not raw_parse_called


@pytest.mark.parametrize("frequency", [1, 10.0, 1_000_000_000])
def test_valid_builtin_integer_and_float_frequencies_remain_accepted(frequency):
    raw = raw_file(
        values=(
            float(frequency),
            0.0,
            0.9,
            -0.1,
            1.0,
            0.0,
            -0.001,
            -0.002,
        )
    )

    results = parse(raw, frequency_hz=frequency)

    assert results.runs[0].frequency_hz == frequency


def test_evidence_validation_happens_before_raw_parsing():
    run = evidence_for(b"not a raw file").runs[0]
    corrupted = replace(run, returncode=7)
    evidence = SimulationExecutionEvidence(SIMULATION_RUNNER_VERSION, (corrupted,))

    with pytest.raises(SimulationRawParseError) as caught:
        parse_simulation_execution_evidence(evidence)

    assert caught.value.code == "raw.evidence.malformed"
    assert caught.value.path == ("runs", 0, "returncode")


def test_corrupted_dataclass_fields_are_normalized():
    evidence = evidence_for(raw_file())
    object.__setattr__(evidence, "runs", ["not-a-tuple"])

    with pytest.raises(SimulationRawParseError) as caught:
        parse_simulation_execution_evidence(evidence)

    assert caught.value.code == "raw.evidence.malformed"


def test_unsupported_evidence_version():
    evidence = SimulationExecutionEvidence("0.9", evidence_for(raw_file()).runs)
    with pytest.raises(SimulationRawParseError) as caught:
        parse_simulation_execution_evidence(evidence)
    assert caught.value.code == "raw.version.unsupported"


def test_empty_and_oversized_raw_output(monkeypatch):
    with pytest.raises(SimulationRawParseError) as caught:
        parse_simulation_execution_evidence(evidence_for(b""))
    assert caught.value.code == "raw.output.empty"

    monkeypatch.setattr(raw_parser_module, "_MAX_RAW_OUTPUT_BYTES", 8)
    with pytest.raises(SimulationRawParseError) as caught:
        parse_simulation_execution_evidence(evidence_for(raw_file()))
    assert caught.value.code == "raw.output.oversized"


def test_oversized_header_and_header_line(monkeypatch):
    monkeypatch.setattr(raw_parser_module, "_MAX_HEADER_BYTES", 10)
    assert_error(raw_file(), "raw.header.oversized")

    monkeypatch.setattr(raw_parser_module, "_MAX_HEADER_BYTES", 64 * 1024)
    monkeypatch.setattr(raw_parser_module, "_MAX_HEADER_LINE_BYTES", 8)
    assert_error(raw_file(), "raw.header.oversized")


@pytest.mark.parametrize("bad", [b"\xff", b"\x00", b"\r"])
def test_non_ascii_nul_and_cr_header_data(bad):
    raw = raw_file().replace(b"Title:", b"Title:" + bad, 1)
    assert_error(raw, "raw.header.invalid")


@pytest.mark.parametrize(
    "mutate",
    [
        lambda lines: lines[1:],
        lambda lines: [lines[1], lines[0], *lines[2:]],
        lambda lines: [lines[0], lines[0], *lines[1:]],
        lambda lines: [lines[0].replace("Title:", "Title"), *lines[1:]],
    ],
)
def test_missing_duplicate_malformed_and_reordered_header_fields(mutate):
    raw = raw_file()
    header, payload = raw.split(b"Binary:\n", 1)
    lines = header.decode("ascii").split("\n")
    mutated = "\n".join(mutate(lines)).encode("ascii") + b"\nBinary:\n" + payload
    assert_error(mutated, "raw.header.invalid")


def test_unsupported_values_ascii_mode():
    raw = raw_file().replace(b"Binary:\n", b"Values:\n", 1)
    assert_error(raw, "raw.format.unsupported")


def test_binary_payload_values_marker_in_ignored_current_slot_is_opaque():
    marker = finite_values_marker_double()
    raw = raw_file_with_ignored_current_bytes(marker)

    results = parse(raw)

    run = results.runs[0]
    assert marker in raw.split(b"Binary:\n", 1)[1]
    assert run.vin_voltage == SimulationComplexValue(1.0, 0.0)
    assert run.vout_voltage == SimulationComplexValue(0.9, -0.1)
    assert "i(v1)" not in run.to_dict()
    assert "i(v1)" not in results.to_json()


def test_date_values_substring_is_not_ascii_values_mode():
    raw = raw_file(date="Values:")

    results = parse(raw)

    assert results.runs[0].vin_voltage == SimulationComplexValue(1.0, 0.0)
    assert results.runs[0].vout_voltage == SimulationComplexValue(0.9, -0.1)


def test_date_binary_substring_is_not_binary_delimiter():
    results = parse(raw_file(date="Binary:"))

    assert results.runs[0].vin_voltage == SimulationComplexValue(1.0, 0.0)
    assert results.runs[0].vout_voltage == SimulationComplexValue(0.9, -0.1)


def test_date_prefixed_binary_substring_is_not_binary_delimiter():
    results = parse(raw_file(date="prefix Binary:"))

    assert results.runs[0].vin_voltage == SimulationComplexValue(1.0, 0.0)
    assert results.runs[0].vout_voltage == SimulationComplexValue(0.9, -0.1)


def test_binary_payload_values_line_marker_is_opaque_when_finite():
    marker = b"Values:\n"
    assert math.isfinite(struct.unpack("@d", marker)[0])
    raw = raw_file_with_ignored_current_bytes(marker)

    results = parse(raw)

    assert results.runs[0].vin_voltage == SimulationComplexValue(1.0, 0.0)
    assert results.runs[0].vout_voltage == SimulationComplexValue(0.9, -0.1)


def test_binary_payload_binary_line_marker_is_opaque_when_finite():
    marker = b"Binary:\n"
    assert math.isfinite(struct.unpack("@d", marker)[0])
    raw = raw_file_with_ignored_current_bytes(marker)

    results = parse(raw)

    assert marker in raw.split(b"Binary:\n", 1)[1]
    assert results.runs[0].vin_voltage == SimulationComplexValue(1.0, 0.0)
    assert results.runs[0].vout_voltage == SimulationComplexValue(0.9, -0.1)


def test_variable_row_binary_substring_is_not_binary_delimiter():
    raw = raw_file().replace(b"\t3\ti(v1)\tcurrent", b"\t3\ti(v1)\tBinary:", 1)

    results = parse(raw)

    assert results.runs[0].vin_voltage == SimulationComplexValue(1.0, 0.0)
    assert results.runs[0].vout_voltage == SimulationComplexValue(0.9, -0.1)


def test_missing_standalone_binary_with_date_binary_is_unsupported():
    raw = raw_file(date="Binary:").replace(b"\nBinary:\n", b"\n", 1)

    caught = assert_error(raw, "raw.format.unsupported")

    assert caught.path == ("runs", 0, "raw_output", "header")


def test_early_standalone_binary_before_variable_table_end_is_malformed_header():
    raw = raw_file().replace(b"\t1\tv(vout)\tvoltage\n", b"Binary:\n\t1\tv(vout)\tvoltage\n", 1)

    caught = assert_error(raw, "raw.header.invalid")

    assert caught.path == ("runs", 0, "raw_output", "header")


@pytest.mark.parametrize(
    ("raw", "code"),
    [
        (raw_file(points="zero"), "raw.count.invalid"),
        (raw_file(points="0"), "raw.count.invalid"),
        (raw_file(points="2"), "raw.count.invalid"),
        (
            raw_file(
                variables=tuple((f"v(n{i})", "voltage") for i in range(65)),
                values=tuple(0.0 for _ in range(130)),
            ),
            "raw.count.invalid",
        ),
    ],
)
def test_malformed_counts_zero_multiple_points_and_too_many_variables(raw, code):
    assert_error(raw, code)


def test_noncontiguous_and_duplicate_variable_indices_and_names():
    raw = raw_file().replace(b"\t1\tv(vout)\tvoltage", b"\t2\tv(vout)\tvoltage", 1)
    assert_error(raw, "raw.variables.invalid")

    duplicate = raw_file(
        variables=(
            ("frequency", "frequency"),
            ("v(vout)", "voltage"),
            ("v(vout)", "voltage"),
            ("i(v1)", "current"),
        )
    )
    assert_error(duplicate, "raw.variables.invalid")


@pytest.mark.parametrize(
    ("variables", "code"),
    [
        ((("frequency", "frequency"), ("v(vout)", "voltage"), ("i(v1)", "current")), "raw.vector.missing"),
        (
            (("frequency", "frequency"), ("v(vout)", "current"), ("v(vin)", "voltage")),
            "raw.variables.invalid",
        ),
    ],
)
def test_missing_or_wrongly_typed_required_vectors(variables, code):
    assert_error(raw_file(variables=variables, values=tuple(0.0 for _ in range(len(variables) * 2))), code)


@pytest.mark.parametrize(
    ("kwargs", "code"),
    [
        ({"title": "* secret_topology"}, "raw.title.invalid"),
        ({"plotname": "Transient Analysis"}, "raw.plot.invalid"),
        ({"flags": "real"}, "raw.flags.invalid"),
        ({"title": "* resistive_divider"}, "raw.title.invalid"),
    ],
)
def test_unsupported_plot_flags_topology_and_title_analysis_mismatch(kwargs, code):
    assert_error(raw_file(**kwargs), code)


def test_truncated_and_trailing_payload():
    raw = raw_file()
    assert_error(raw[:-1], "raw.payload.truncated")
    assert_error(raw + b"\x00", "raw.payload.trailing")


@pytest.mark.parametrize("index", range(8))
@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_non_finite_values_in_complex_payload(index, value):
    values = [10.0, 0.0, 0.9, -0.1, 1.0, 0.0, -0.001, -0.002]
    values[index] = value
    assert_error(raw_file(values=tuple(values)), "raw.value.non_finite")


@pytest.mark.parametrize("index", range(3))
@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_non_finite_values_in_real_payload(index, value):
    values = [5.0, 3.333333333333333, -0.0001666666666666667]
    values[index] = value
    raw = raw_file(
        title="* resistive_divider",
        plotname="Operating Point",
        flags="real",
        variables=(("v(vin)", "voltage"), ("v(vout)", "voltage"), ("i(v1)", "current")),
        values=tuple(values),
    )
    assert_error(raw, "raw.value.non_finite", run_id="dc-op", analysis_kind="dc", frequency_hz=None)


def test_ac_frequency_with_normal_nonzero_imaginary_component():
    raw = raw_file(values=(10.0, 1.0, 0.9, -0.1, 1.0, 0.0, 0.0, 0.0))
    assert_error(raw, "raw.frequency.mismatch")


def test_no_arbitrary_raw_metadata_appears_in_public_output_or_errors():
    raw = raw_file().replace(DATE.encode("ascii"), b"secret-date-value")
    results = parse(raw)

    serialized = results.to_json()
    assert "secret" not in serialized
    assert "stdout" not in serialized
    assert "stderr" not in serialized
    assert "i(v1)" not in serialized

    error = assert_error(raw.replace(b"Binary:\n", b"", 1), "raw.format.unsupported")
    assert "secret" not in error.to_dict()["message"]


def test_no_caller_controlled_parser_configuration_exists():
    signature = inspect.signature(parse_simulation_execution_evidence)
    assert len(signature.parameters) == 1


@pytest.mark.parametrize(
    "plan",
    [
        CircuitPlan(
            schema_version="1.0",
            topology="rc_low_pass",
            analysis="ac",
            parameters={"resistance_ohms": 1000, "capacitance_farads": 1e-6},
            requested_frequencies_hz=(10.0,),
        ),
        CircuitPlan(
            schema_version="1.0",
            topology="rc_high_pass",
            analysis="ac",
            parameters={"resistance_ohms": 1000, "capacitance_farads": 1e-6},
            requested_frequencies_hz=(100,),
        ),
        CircuitPlan(
            schema_version="1.0",
            topology="resistive_divider",
            analysis="dc",
            parameters={
                "resistance_top_ohms": 10_000,
                "resistance_bottom_ohms": 20_000,
                "input_voltage_volts": 5.0,
            },
        ),
    ],
)
def test_real_ngspice_plan_deck_runner_parser_chain(plan):
    executable = Path("/usr/bin/ngspice")
    if not executable.is_file() or not os.access(executable, os.X_OK):
        pytest.skip("fixed trusted ngspice executable is unavailable")
    try:
        evidence = run_simulation_deck(
            build_simulation_deck_from_assembly(build_simulation_assembly_from_plan(plan))
        )
    except simulation.SimulationRunnerError as exc:
        if exc.code in {
            "runner.executable.missing",
            "runner.executable.invalid",
            "runner.subprocess.start_failed",
        }:
            pytest.skip(f"fixed trusted ngspice executable is unavailable: {exc.code}")
        raise

    results = parse_simulation_execution_evidence(evidence)

    assert len(results.runs) == 1
    assert results.runs[0].topology == plan.topology
