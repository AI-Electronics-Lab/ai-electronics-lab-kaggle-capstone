"""Deterministic analytical verification of parsed simulation measurements."""

from __future__ import annotations

import gc
import json
import math
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Literal

from ai_electronics_lab.contracts import (
    CircuitPlan,
    CircuitPlanValidationError,
    require_valid_circuit_plan,
)
from ai_electronics_lab.simulation.deck import MAX_AC_RUNS
from ai_electronics_lab.simulation.raw_parser import (
    SIMULATION_RAW_PARSER_VERSION,
    SimulationComplexValue,
    SimulationParsedResults,
    SimulationRunMeasurements,
)

SIMULATION_VERIFIER_VERSION = "1.0"
VERIFICATION_ABSOLUTE_TOLERANCE = 1e-9
VERIFICATION_RELATIVE_TOLERANCE = 1e-6
VERIFICATION_WARNING_MULTIPLIER = 10.0
VERIFICATION_DENOMINATOR_FLOOR = 1e-12

VerificationStatus = Literal["PASS", "WARN", "FAIL"]

_STATUS_SEVERITY: dict[VerificationStatus, int] = {"PASS": 0, "WARN": 1, "FAIL": 2}
_SUPPORTED_TOPOLOGIES = frozenset({"rc_low_pass", "rc_high_pass", "resistive_divider"})
_SUPPORTED_ANALYSES = frozenset({"ac", "dc"})
_COMPARISON_METRICS = frozenset(
    {"vin_voltage", "transfer_function", "divider_ratio", "vout_voltage"}
)
_NORMAL_REASONS = frozenset(
    {
        "verification.within_tolerance",
        "verification.near_tolerance",
        "verification.outside_tolerance",
        "verification.denominator_too_small",
    }
)


class SimulationVerificationError(ValueError):
    """Stable structured failure at the deterministic verification boundary."""

    def __init__(self, code: str, path: tuple[str | int, ...], message: str) -> None:
        self.code = code
        self.path = path
        self.message = message
        location = ".".join(str(item) for item in path) or "<root>"
        super().__init__(f"{code} at {location}: {message}")

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "path": list(self.path), "message": self.message}


@dataclass(frozen=True, slots=True)
class VerificationTolerancePolicy:
    """The fixed non-configurable verifier tolerance policy."""

    absolute_tolerance: float = VERIFICATION_ABSOLUTE_TOLERANCE
    relative_tolerance: float = VERIFICATION_RELATIVE_TOLERANCE
    warning_multiplier: float = VERIFICATION_WARNING_MULTIPLIER
    denominator_floor: float = VERIFICATION_DENOMINATOR_FLOOR

    def __post_init__(self) -> None:
        expected = (
            VERIFICATION_ABSOLUTE_TOLERANCE,
            VERIFICATION_RELATIVE_TOLERANCE,
            VERIFICATION_WARNING_MULTIPLIER,
            VERIFICATION_DENOMINATOR_FLOOR,
        )
        actual = (
            self.absolute_tolerance,
            self.relative_tolerance,
            self.warning_multiplier,
            self.denominator_floor,
        )
        if any(type(value) is not float for value in actual) or actual != expected:
            _fail(
                "verification.input.malformed",
                ("tolerance_policy",),
                "verification tolerance policy is fixed",
            )

    def to_dict(self) -> dict[str, float]:
        return {
            "absolute_tolerance": self.absolute_tolerance,
            "denominator_floor": self.denominator_floor,
            "relative_tolerance": self.relative_tolerance,
            "warning_multiplier": self.warning_multiplier,
        }


@dataclass(frozen=True, slots=True)
class VerificationComplexValue:
    """One finite complex value used by verification evidence."""

    real: float
    imag: float

    def __post_init__(self) -> None:
        if type(self.real) is not float or type(self.imag) is not float:
            _fail(
                "verification.input.malformed",
                (),
                "verification complex values must be built-in floats",
            )
        if not math.isfinite(self.real) or not math.isfinite(self.imag):
            _fail(
                "verification.value.non_finite",
                (),
                "verification complex values must be finite",
            )

    def to_dict(self) -> dict[str, float | None]:
        magnitude = _finite_hypot(self.real, self.imag, ())
        phase_degrees: float | None
        if magnitude < VERIFICATION_DENOMINATOR_FLOOR:
            phase_degrees = None
        else:
            phase_degrees = math.degrees(math.atan2(self.imag, self.real))
            _require_finite(phase_degrees, ())
        return {
            "imag": self.imag,
            "magnitude": magnitude,
            "phase_degrees": phase_degrees,
            "real": self.real,
        }

    def to_json(self) -> str:
        return _canonical_json(self.to_dict())


@dataclass(frozen=True, slots=True)
class VerificationComparison:
    """One ordered expected-versus-measured metric comparison."""

    metric: str
    expected: VerificationComplexValue
    measured: VerificationComplexValue | None
    absolute_error: float | None
    relative_error: float | None
    pass_limit: float
    warning_limit: float
    status: VerificationStatus
    reason_code: str

    def __post_init__(self) -> None:
        if type(self.metric) is not str or self.metric not in _COMPARISON_METRICS:
            _fail("verification.input.malformed", ("metric",), "comparison metric is invalid")
        if type(self.expected) is not VerificationComplexValue:
            _fail(
                "verification.input.malformed",
                ("expected",),
                "comparison expected value is invalid",
            )
        if self.measured is not None and type(self.measured) is not VerificationComplexValue:
            _fail(
                "verification.input.malformed",
                ("measured",),
                "comparison measured value is invalid",
            )
        for name, value in (
            ("absolute_error", self.absolute_error),
            ("relative_error", self.relative_error),
        ):
            if value is not None and (type(value) is not float or not math.isfinite(value)):
                _fail(
                    "verification.value.non_finite",
                    (name,),
                    "comparison numeric value must be a finite built-in float",
                )
            if value is not None and value < 0.0:
                _fail(
                    "verification.input.malformed",
                    (name,),
                    "comparison error must be nonnegative",
                )
        for name, value in (
            ("pass_limit", self.pass_limit),
            ("warning_limit", self.warning_limit),
        ):
            if type(value) is not float or not math.isfinite(value):
                _fail(
                    "verification.value.non_finite",
                    (name,),
                    "comparison limit must be a finite built-in float",
                )
            if value <= 0.0:
                _fail(
                    "verification.input.malformed",
                    (name,),
                    "comparison limit must be positive",
                )
        if type(self.status) is not str or self.status not in _STATUS_SEVERITY:
            _fail("verification.input.malformed", ("status",), "comparison status is invalid")
        if type(self.reason_code) is not str or self.reason_code not in _NORMAL_REASONS:
            _fail(
                "verification.input.malformed",
                ("reason_code",),
                "comparison reason code is invalid",
            )

        expected_magnitude = _finite_hypot(self.expected.real, self.expected.imag, ())
        expected_pass_limit = _pass_limit(expected_magnitude)
        expected_warning_limit = _require_finite(
            VERIFICATION_WARNING_MULTIPLIER * expected_pass_limit,
            (),
        )
        if self.pass_limit != expected_pass_limit or self.warning_limit != expected_warning_limit:
            _fail(
                "verification.input.malformed",
                ("pass_limit",),
                "comparison limits do not match the fixed policy",
            )

        if self.reason_code == "verification.denominator_too_small":
            if (
                self.measured is not None
                or self.absolute_error is not None
                or self.relative_error is not None
                or self.status != "FAIL"
            ):
                _fail(
                    "verification.input.malformed",
                    (),
                    "denominator failure comparison is incoherent",
                )
            return

        if self.measured is None or self.absolute_error is None:
            _fail(
                "verification.input.malformed",
                (),
                "normal comparison is incomplete",
            )
        error_real = _require_finite(self.measured.real - self.expected.real, ())
        error_imag = _require_finite(self.measured.imag - self.expected.imag, ())
        expected_absolute_error = _finite_hypot(error_real, error_imag, ())
        expected_relative_error = (
            _finite_divide(expected_absolute_error, expected_magnitude, ())
            if expected_magnitude >= VERIFICATION_DENOMINATOR_FLOOR
            else None
        )
        if (
            self.absolute_error != expected_absolute_error
            or self.relative_error != expected_relative_error
        ):
            _fail(
                "verification.input.malformed",
                ("absolute_error",),
                "comparison errors do not match the compared values",
            )
        if expected_absolute_error <= expected_pass_limit:
            expected_status: VerificationStatus = "PASS"
            expected_reason = "verification.within_tolerance"
        elif expected_absolute_error <= expected_warning_limit:
            expected_status = "WARN"
            expected_reason = "verification.near_tolerance"
        else:
            expected_status = "FAIL"
            expected_reason = "verification.outside_tolerance"
        if self.status != expected_status or self.reason_code != expected_reason:
            _fail(
                "verification.input.malformed",
                ("status",),
                "comparison classification is incoherent",
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "absolute_error": self.absolute_error,
            "expected": self.expected.to_dict(),
            "measured": None if self.measured is None else self.measured.to_dict(),
            "metric": self.metric,
            "pass_limit": self.pass_limit,
            "reason_code": self.reason_code,
            "relative_error": self.relative_error,
            "status": self.status,
            "warning_limit": self.warning_limit,
        }


@dataclass(frozen=True, slots=True)
class VerificationRunResult:
    """Ordered verification evidence for one simulation run."""

    run_id: str
    topology: str
    analysis_kind: str
    frequency_hz: float | int | None
    cutoff_frequency_hz: float | None
    status: VerificationStatus
    reason_codes: tuple[str, ...]
    comparisons: tuple[VerificationComparison, ...]

    def __post_init__(self) -> None:
        if type(self.run_id) is not str or not self.run_id:
            _fail("verification.input.malformed", ("run_id",), "run ID is invalid")
        if type(self.topology) is not str or self.topology not in _SUPPORTED_TOPOLOGIES:
            _fail("verification.input.malformed", ("topology",), "run topology is invalid")
        if type(self.analysis_kind) is not str or self.analysis_kind not in _SUPPORTED_ANALYSES:
            _fail(
                "verification.input.malformed",
                ("analysis_kind",),
                "run analysis kind is invalid",
            )
        _validate_optional_number(self.frequency_hz, ("frequency_hz",))
        if self.cutoff_frequency_hz is not None and (
            type(self.cutoff_frequency_hz) is not float
            or not math.isfinite(self.cutoff_frequency_hz)
        ):
            _fail(
                "verification.value.non_finite",
                ("cutoff_frequency_hz",),
                "cutoff frequency must be a finite built-in float",
            )
        if type(self.status) is not str or self.status not in _STATUS_SEVERITY:
            _fail("verification.input.malformed", ("status",), "run status is invalid")
        if type(self.reason_codes) is not tuple or not self.reason_codes:
            _fail(
                "verification.input.malformed",
                ("reason_codes",),
                "run reason codes must be a non-empty tuple",
            )
        if any(type(code) is not str or code not in _NORMAL_REASONS for code in self.reason_codes):
            _fail(
                "verification.input.malformed",
                ("reason_codes",),
                "run reason code is invalid",
            )
        if len(set(self.reason_codes)) != len(self.reason_codes):
            _fail(
                "verification.input.malformed",
                ("reason_codes",),
                "run reason codes must be duplicate-free",
            )
        if type(self.comparisons) is not tuple or not self.comparisons:
            _fail(
                "verification.input.malformed",
                ("comparisons",),
                "run comparisons must be a non-empty tuple",
            )
        if any(type(item) is not VerificationComparison for item in self.comparisons):
            _fail(
                "verification.input.malformed",
                ("comparisons",),
                "run comparison is invalid",
            )
        expected_status = _greatest_status(tuple(item.status for item in self.comparisons))
        expected_reasons = tuple(dict.fromkeys(item.reason_code for item in self.comparisons))
        if self.status != expected_status or self.reason_codes != expected_reasons:
            _fail(
                "verification.input.malformed",
                (),
                "run verification summary is incoherent",
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "analysis_kind": self.analysis_kind,
            "comparisons": [comparison.to_dict() for comparison in self.comparisons],
            "cutoff_frequency_hz": self.cutoff_frequency_hz,
            "frequency_hz": self.frequency_hz,
            "reason_codes": list(self.reason_codes),
            "run_id": self.run_id,
            "status": self.status,
            "topology": self.topology,
        }


@dataclass(frozen=True, slots=True)
class SimulationVerificationResults:
    """Immutable ordered verification evidence for a complete simulation."""

    version: str
    status: VerificationStatus
    tolerance_policy: VerificationTolerancePolicy
    runs: tuple[VerificationRunResult, ...]

    def __post_init__(self) -> None:
        if type(self.version) is not str or self.version != SIMULATION_VERIFIER_VERSION:
            _fail("verification.version.unsupported", ("version",), "verifier version is unsupported")
        if type(self.status) is not str or self.status not in _STATUS_SEVERITY:
            _fail("verification.input.malformed", ("status",), "overall status is invalid")
        if type(self.tolerance_policy) is not VerificationTolerancePolicy:
            _fail(
                "verification.input.malformed",
                ("tolerance_policy",),
                "tolerance policy is invalid",
            )
        if type(self.runs) is not tuple or not self.runs:
            _fail(
                "verification.input.malformed",
                ("runs",),
                "verification runs must be a non-empty tuple",
            )
        if any(type(run) is not VerificationRunResult for run in self.runs):
            _fail("verification.input.malformed", ("runs",), "verification run is invalid")
        if self.status != _greatest_status(tuple(run.status for run in self.runs)):
            _fail(
                "verification.input.malformed",
                ("status",),
                "overall verification status is incoherent",
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "runs": [run.to_dict() for run in self.runs],
            "status": self.status,
            "tolerance_policy": self.tolerance_policy.to_dict(),
            "version": self.version,
        }

    def to_json(self) -> str:
        return _canonical_json(self.to_dict())


def verify_simulation_results(
    plan: CircuitPlan,
    parsed_results: SimulationParsedResults,
) -> SimulationVerificationResults:
    """Verify parsed ngspice voltage measurements against fixed analytical models."""

    try:
        validated_plan = _validate_plan(plan)
        runs = _validate_parsed_results(parsed_results)
        _validate_coherence(validated_plan, runs)
        verified_runs = tuple(
            _verify_run(validated_plan, run, index) for index, run in enumerate(runs)
        )
        return SimulationVerificationResults(
            version=SIMULATION_VERIFIER_VERSION,
            status=_greatest_status(tuple(run.status for run in verified_runs)),
            tolerance_policy=VerificationTolerancePolicy(),
            runs=verified_runs,
        )
    except SimulationVerificationError:
        raise
    except CircuitPlanValidationError as exc:
        path = exc.errors[0].path if exc.errors else ()
        raise SimulationVerificationError(
            "verification.plan.invalid",
            path,
            "circuit plan is invalid",
        ) from None
    except OverflowError as exc:
        raise SimulationVerificationError(
            "verification.numeric_overflow",
            (),
            "verification arithmetic overflowed",
        ) from exc
    except (ArithmeticError, AssertionError, AttributeError, IndexError, KeyError, TypeError, ValueError) as exc:
        raise SimulationVerificationError(
            "verification.input.malformed",
            (),
            "verification inputs are malformed",
        ) from exc


verify_simulation_results.__annotations__ = {
    "plan": CircuitPlan,
    "parsed_results": SimulationParsedResults,
    "return": SimulationVerificationResults,
}


def _validate_plan(plan: CircuitPlan) -> CircuitPlan:
    if type(plan) is not CircuitPlan:
        _fail("verification.input.malformed", (), "plan must be CircuitPlan")
    if type(plan.schema_version) is not str:
        _fail("verification.input.malformed", ("schema_version",), "plan version must be a string")
    if type(plan.topology) is not str:
        _fail("verification.input.malformed", ("topology",), "plan topology must be a string")
    if type(plan.analysis) is not str:
        _fail("verification.input.malformed", ("analysis",), "plan analysis must be a string")
    parameters = _exact_mapping_proxy_dict(plan.parameters, ("parameters",))
    if type(plan.requested_frequencies_hz) is not tuple:
        _fail(
            "verification.input.malformed",
            ("requested_frequencies_hz",),
            "requested frequencies are malformed",
        )
    if type(plan.assumptions) is not tuple:
        _fail("verification.input.malformed", ("assumptions",), "plan assumptions are malformed")
    for key in parameters:
        if type(key) is not str:
            _fail("verification.input.malformed", ("parameters",), "parameter key is malformed")
        value = parameters[key]
        _validate_exact_number(value, ("parameters", key))
    for index, value in enumerate(plan.requested_frequencies_hz):
        _validate_exact_number(value, ("requested_frequencies_hz", index))
    for index, value in enumerate(plan.assumptions):
        if type(value) is not str:
            _fail(
                "verification.input.malformed",
                ("assumptions", index),
                "plan assumption is malformed",
            )
    try:
        return require_valid_circuit_plan(plan)
    except CircuitPlanValidationError:
        raise
    except (ArithmeticError, AttributeError, IndexError, KeyError, TypeError, ValueError) as exc:
        raise SimulationVerificationError(
            "verification.input.malformed",
            (),
            "circuit plan is malformed",
        ) from exc


def _exact_mapping_proxy_dict(
    value: object,
    path: tuple[str | int, ...],
) -> dict[str, object]:
    if type(value) is not MappingProxyType:
        _fail("verification.input.malformed", path, "plan parameters are malformed")
    referents = gc.get_referents(value)
    if len(referents) != 1 or type(referents[0]) is not dict:
        _fail("verification.input.malformed", path, "plan parameters are malformed")
    return referents[0]


def _validate_parsed_results(
    parsed_results: SimulationParsedResults,
) -> tuple[SimulationRunMeasurements, ...]:
    if type(parsed_results) is not SimulationParsedResults:
        _fail(
            "verification.input.malformed",
            (),
            "parsed results must be SimulationParsedResults",
        )
    if type(parsed_results.version) is not str:
        _fail(
            "verification.input.malformed",
            ("version",),
            "parsed result version must be a string",
        )
    if parsed_results.version != SIMULATION_RAW_PARSER_VERSION:
        _fail(
            "verification.version.unsupported",
            ("version",),
            "parsed result version is unsupported",
        )
    if type(parsed_results.runs) is not tuple:
        _fail("verification.input.malformed", ("runs",), "runs must be an immutable tuple")
    if not parsed_results.runs or len(parsed_results.runs) > MAX_AC_RUNS:
        _fail("verification.input.malformed", ("runs",), "run count is outside the verifier limit")
    for index, run in enumerate(parsed_results.runs):
        _validate_run(run, index)
    return parsed_results.runs


def _validate_run(run: SimulationRunMeasurements, index: int) -> None:
    path = ("runs", index)
    if type(run) is not SimulationRunMeasurements:
        _fail("verification.input.malformed", path, "run must be SimulationRunMeasurements")
    if type(run.run_id) is not str:
        _fail("verification.input.malformed", path + ("run_id",), "run ID must be a string")
    if type(run.topology) is not str or run.topology not in _SUPPORTED_TOPOLOGIES:
        _fail("verification.input.malformed", path + ("topology",), "run topology is invalid")
    if type(run.analysis_kind) is not str or run.analysis_kind not in _SUPPORTED_ANALYSES:
        _fail(
            "verification.input.malformed",
            path + ("analysis_kind",),
            "run analysis kind is invalid",
        )
    _validate_optional_number(run.frequency_hz, path + ("frequency_hz",))
    _validate_complex_input(run.vin_voltage, path + ("vin_voltage",))
    _validate_complex_input(run.vout_voltage, path + ("vout_voltage",))


def _validate_optional_number(value: object, path: tuple[str | int, ...]) -> None:
    if value is None:
        return
    _validate_exact_number(value, path)


def _validate_exact_number(value: object, path: tuple[str | int, ...]) -> None:
    if type(value) not in {int, float}:
        _fail("verification.input.malformed", path, "numeric value must be a built-in int or float")
    if type(value) is float and not math.isfinite(value):
        _fail("verification.value.non_finite", path, "numeric value must be finite")


def _validate_complex_input(value: object, path: tuple[str | int, ...]) -> None:
    if type(value) is not SimulationComplexValue:
        _fail("verification.input.malformed", path, "voltage must be SimulationComplexValue")
    if type(value.real) is not float or type(value.imag) is not float:
        _fail(
            "verification.input.malformed",
            path,
            "voltage components must be built-in floats",
        )
    if not math.isfinite(value.real) or not math.isfinite(value.imag):
        _fail("verification.value.non_finite", path, "voltage components must be finite")


def _validate_coherence(
    plan: CircuitPlan,
    runs: tuple[SimulationRunMeasurements, ...],
) -> None:
    if plan.topology in {"rc_low_pass", "rc_high_pass"}:
        if plan.analysis != "ac" or len(runs) != len(plan.requested_frequencies_hz):
            _mismatch()
        for index, (run, frequency) in enumerate(zip(runs, plan.requested_frequencies_hz)):
            if (
                run.run_id != f"ac-{index + 1:02d}"
                or run.topology != plan.topology
                or run.analysis_kind != "ac"
                or run.frequency_hz is None
                or run.frequency_hz != frequency
            ):
                _mismatch(("runs", index))
        return

    if (
        plan.topology != "resistive_divider"
        or plan.analysis != "dc"
        or plan.requested_frequencies_hz
        or len(runs) != 1
    ):
        _mismatch()
    run = runs[0]
    if (
        run.run_id != "dc-op"
        or run.topology != "resistive_divider"
        or run.analysis_kind != "dc"
        or run.frequency_hz is not None
    ):
        _mismatch(("runs", 0))


def _mismatch(path: tuple[str | int, ...] = ()) -> None:
    _fail(
        "verification.results.mismatch",
        path,
        "parsed results do not match the circuit plan",
    )


def _verify_run(
    plan: CircuitPlan,
    run: SimulationRunMeasurements,
    _index: int,
) -> VerificationRunResult:
    measured_vin = _copy_complex(run.vin_voltage)
    measured_vout = _copy_complex(run.vout_voltage)

    if plan.topology in {"rc_low_pass", "rc_high_pass"}:
        frequency_hz = float(run.frequency_hz)  # coherence guarantees one finite numeric value
        resistance = float(plan.parameters["resistance_ohms"])
        capacitance = float(plan.parameters["capacitance_farads"])
        omega = _finite_product((2.0, math.pi, frequency_hz), ("runs", _index, "omega"))
        x = _finite_product((omega, resistance, capacitance), ("runs", _index, "x"))
        cutoff = _finite_divide(
            1.0,
            _finite_product((2.0, math.pi, resistance, capacitance), ("runs", _index, "cutoff")),
            ("runs", _index, "cutoff"),
        )
        denominator = _require_finite(1.0 + x * x, ("runs", _index, "analytical_denominator"))
        if plan.topology == "rc_low_pass":
            expected_transfer = VerificationComplexValue(
                _finite_divide(1.0, denominator, ("runs", _index, "expected_transfer")),
                _finite_divide(-x, denominator, ("runs", _index, "expected_transfer")),
            )
        else:
            expected_transfer = VerificationComplexValue(
                _finite_divide(x * x, denominator, ("runs", _index, "expected_transfer")),
                _finite_divide(x, denominator, ("runs", _index, "expected_transfer")),
            )
        expected_vin = VerificationComplexValue(1.0, 0.0)
        measured_transfer = _divide_or_none(measured_vout, measured_vin)
        comparisons = (
            _compare("vin_voltage", expected_vin, measured_vin),
            _compare_or_denominator_failure(
                "transfer_function",
                expected_transfer,
                measured_transfer,
            ),
            _compare("vout_voltage", expected_transfer, measured_vout),
        )
        return _make_run_result(run, cutoff, comparisons)

    input_voltage = float(plan.parameters["input_voltage_volts"])
    resistance_top = float(plan.parameters["resistance_top_ohms"])
    resistance_bottom = float(plan.parameters["resistance_bottom_ohms"])
    resistance_sum = _require_finite(
        resistance_top + resistance_bottom,
        ("runs", _index, "divider_resistance_sum"),
    )
    ratio = _finite_divide(
        resistance_bottom,
        resistance_sum,
        ("runs", _index, "expected_ratio"),
    )
    expected_vin = VerificationComplexValue(input_voltage, 0.0)
    expected_ratio = VerificationComplexValue(ratio, 0.0)
    expected_vout = VerificationComplexValue(
        _require_finite(input_voltage * ratio, ("runs", _index, "expected_vout")),
        0.0,
    )
    measured_ratio = _divide_or_none(measured_vout, measured_vin)
    comparisons = (
        _compare("vin_voltage", expected_vin, measured_vin),
        _compare_or_denominator_failure("divider_ratio", expected_ratio, measured_ratio),
        _compare("vout_voltage", expected_vout, measured_vout),
    )
    return _make_run_result(run, None, comparisons)


def _copy_complex(value: SimulationComplexValue) -> VerificationComplexValue:
    return VerificationComplexValue(value.real, value.imag)


def _divide_or_none(
    numerator: VerificationComplexValue,
    denominator: VerificationComplexValue,
) -> VerificationComplexValue | None:
    magnitude = _finite_hypot(denominator.real, denominator.imag, ())
    if magnitude < VERIFICATION_DENOMINATOR_FLOOR:
        return None
    scale = max(abs(denominator.real), abs(denominator.imag))
    if scale == 0.0:
        return None
    br = denominator.real / scale
    bi = denominator.imag / scale
    denominator_scaled = _require_finite(br * br + bi * bi, ())
    ar = _finite_divide(numerator.real, scale, ())
    ai = _finite_divide(numerator.imag, scale, ())
    real = _finite_divide(
        _require_finite(ar * br + ai * bi, ()),
        denominator_scaled,
        (),
    )
    imag = _finite_divide(
        _require_finite(ai * br - ar * bi, ()),
        denominator_scaled,
        (),
    )
    return VerificationComplexValue(real, imag)


def _compare_or_denominator_failure(
    metric: str,
    expected: VerificationComplexValue,
    measured: VerificationComplexValue | None,
) -> VerificationComparison:
    if measured is not None:
        return _compare(metric, expected, measured)
    expected_magnitude = _finite_hypot(expected.real, expected.imag, ())
    pass_limit = _pass_limit(expected_magnitude)
    warning_limit = _require_finite(VERIFICATION_WARNING_MULTIPLIER * pass_limit, ())
    return VerificationComparison(
        metric=metric,
        expected=expected,
        measured=None,
        absolute_error=None,
        relative_error=None,
        pass_limit=pass_limit,
        warning_limit=warning_limit,
        status="FAIL",
        reason_code="verification.denominator_too_small",
    )


def _compare(
    metric: str,
    expected: VerificationComplexValue,
    measured: VerificationComplexValue,
) -> VerificationComparison:
    error_real = _require_finite(measured.real - expected.real, ())
    error_imag = _require_finite(measured.imag - expected.imag, ())
    absolute_error = _finite_hypot(error_real, error_imag, ())
    expected_magnitude = _finite_hypot(expected.real, expected.imag, ())
    pass_limit = _pass_limit(expected_magnitude)
    warning_limit = _require_finite(VERIFICATION_WARNING_MULTIPLIER * pass_limit, ())
    relative_error = (
        _finite_divide(absolute_error, expected_magnitude, ())
        if expected_magnitude >= VERIFICATION_DENOMINATOR_FLOOR
        else None
    )
    if absolute_error <= pass_limit:
        status: VerificationStatus = "PASS"
        reason = "verification.within_tolerance"
    elif absolute_error <= warning_limit:
        status = "WARN"
        reason = "verification.near_tolerance"
    else:
        status = "FAIL"
        reason = "verification.outside_tolerance"
    return VerificationComparison(
        metric=metric,
        expected=expected,
        measured=measured,
        absolute_error=absolute_error,
        relative_error=relative_error,
        pass_limit=pass_limit,
        warning_limit=warning_limit,
        status=status,
        reason_code=reason,
    )


def _pass_limit(expected_magnitude: float) -> float:
    return _require_finite(
        VERIFICATION_ABSOLUTE_TOLERANCE
        + VERIFICATION_RELATIVE_TOLERANCE * expected_magnitude,
        (),
    )


def _make_run_result(
    run: SimulationRunMeasurements,
    cutoff_frequency_hz: float | None,
    comparisons: tuple[VerificationComparison, ...],
) -> VerificationRunResult:
    reasons = tuple(dict.fromkeys(comparison.reason_code for comparison in comparisons))
    return VerificationRunResult(
        run_id=run.run_id,
        topology=run.topology,
        analysis_kind=run.analysis_kind,
        frequency_hz=run.frequency_hz,
        cutoff_frequency_hz=cutoff_frequency_hz,
        status=_greatest_status(tuple(comparison.status for comparison in comparisons)),
        reason_codes=reasons,
        comparisons=comparisons,
    )


def _greatest_status(statuses: tuple[VerificationStatus, ...]) -> VerificationStatus:
    if not statuses:
        _fail("verification.input.malformed", (), "verification status set is empty")
    return max(statuses, key=_STATUS_SEVERITY.__getitem__)


def _finite_product(values: tuple[float, ...], path: tuple[str | int, ...]) -> float:
    result = 1.0
    for value in values:
        result = _require_finite(result * value, path)
    return result


def _finite_divide(
    numerator: float,
    denominator: float,
    path: tuple[str | int, ...],
) -> float:
    try:
        value = numerator / denominator
    except OverflowError as exc:
        raise SimulationVerificationError(
            "verification.numeric_overflow",
            path,
            "verification arithmetic overflowed",
        ) from exc
    except ZeroDivisionError as exc:
        raise SimulationVerificationError(
            "verification.numeric_overflow",
            path,
            "verification arithmetic is not finite",
        ) from exc
    return _require_finite(value, path)


def _finite_hypot(real: float, imag: float, path: tuple[str | int, ...]) -> float:
    return _require_finite(math.hypot(real, imag), path)


def _require_finite(value: float, path: tuple[str | int, ...]) -> float:
    if type(value) is not float or not math.isfinite(value):
        _fail(
            "verification.numeric_overflow",
            path,
            "verification arithmetic is not finite",
        )
    return value


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )


def _fail(code: str, path: tuple[str | int, ...], message: str) -> None:
    raise SimulationVerificationError(code, path, message)


__all__ = [
    "SIMULATION_VERIFIER_VERSION",
    "VERIFICATION_ABSOLUTE_TOLERANCE",
    "VERIFICATION_DENOMINATOR_FLOOR",
    "VERIFICATION_RELATIVE_TOLERANCE",
    "VERIFICATION_WARNING_MULTIPLIER",
    "SimulationVerificationError",
    "SimulationVerificationResults",
    "VerificationComparison",
    "VerificationComplexValue",
    "VerificationRunResult",
    "VerificationTolerancePolicy",
    "verify_simulation_results",
]
