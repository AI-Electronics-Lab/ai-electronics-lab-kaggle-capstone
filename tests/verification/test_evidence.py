from __future__ import annotations

import dataclasses
import inspect
import json
import math
from types import MappingProxyType

import pytest

from ai_electronics_lab.contracts import CircuitPlan
from ai_electronics_lab.contracts.circuit_plan import SCHEMA_VERSION
from ai_electronics_lab.simulation import (
    SIMULATION_RAW_PARSER_VERSION,
    SimulationComplexValue,
    SimulationParsedResults,
    SimulationRunMeasurements,
)
from ai_electronics_lab.verification import (
    SIMULATION_VERIFIER_VERSION,
    VERIFICATION_ABSOLUTE_TOLERANCE,
    VERIFICATION_DENOMINATOR_FLOOR,
    VERIFICATION_RELATIVE_TOLERANCE,
    VERIFICATION_WARNING_MULTIPLIER,
    SimulationVerificationError,
    SimulationVerificationResults,
    VerificationComparison,
    VerificationComplexValue,
    VerificationRunResult,
    VerificationTolerancePolicy,
    verify_simulation_results,
)


def _rc_plan(topology: str, frequency: float, *, resistance: float = 1000.0, capacitance: float = 1e-6) -> CircuitPlan:
    return CircuitPlan(
        schema_version=SCHEMA_VERSION,
        topology=topology,
        analysis="ac",
        parameters={
            "resistance_ohms": resistance,
            "capacitance_farads": capacitance,
        },
        requested_frequencies_hz=(frequency,),
        assumptions=(),
    )


def _divider_plan(input_voltage: float = 5.0) -> CircuitPlan:
    return CircuitPlan(
        schema_version=SCHEMA_VERSION,
        topology="resistive_divider",
        analysis="dc",
        parameters={
            "input_voltage_volts": input_voltage,
            "resistance_top_ohms": 1000.0,
            "resistance_bottom_ohms": 2000.0,
        },
        requested_frequencies_hz=(),
        assumptions=(),
    )


def _run(
    *,
    run_id: str,
    topology: str,
    analysis_kind: str,
    frequency_hz: float | int | None,
    vin: complex,
    vout: complex,
) -> SimulationRunMeasurements:
    return SimulationRunMeasurements(
        run_id=run_id,
        topology=topology,  # type: ignore[arg-type]
        analysis_kind=analysis_kind,  # type: ignore[arg-type]
        frequency_hz=frequency_hz,
        vin_voltage=SimulationComplexValue(float(vin.real), float(vin.imag)),
        vout_voltage=SimulationComplexValue(float(vout.real), float(vout.imag)),
    )


def _results(*runs: SimulationRunMeasurements, version: str = SIMULATION_RAW_PARSER_VERSION) -> SimulationParsedResults:
    return SimulationParsedResults(version=version, runs=tuple(runs))


def _exact_rc(topology: str, frequency: float, resistance: float = 1000.0, capacitance: float = 1e-6) -> complex:
    x = 2.0 * math.pi * frequency * resistance * capacitance
    if topology == "rc_low_pass":
        return complex(1.0 / (1.0 + x * x), -x / (1.0 + x * x))
    return complex(x * x / (1.0 + x * x), x / (1.0 + x * x))


def _comparison(result: SimulationVerificationResults, metric: str) -> VerificationComparison:
    return next(item for item in result.runs[0].comparisons if item.metric == metric)


def test_public_constants_contract() -> None:
    assert SIMULATION_VERIFIER_VERSION == "1.0"
    assert VERIFICATION_ABSOLUTE_TOLERANCE == 1e-9
    assert VERIFICATION_RELATIVE_TOLERANCE == 1e-6
    assert VERIFICATION_WARNING_MULTIPLIER == 10.0
    assert VERIFICATION_DENOMINATOR_FLOOR == 1e-12


@pytest.mark.parametrize(
    ("topology", "expected"),
    [
        ("rc_low_pass", complex(0.5, -0.5)),
        ("rc_high_pass", complex(0.5, 0.5)),
    ],
)
def test_exact_rc_analytical_values(topology: str, expected: complex) -> None:
    frequency = 1.0 / (2.0 * math.pi * 1000.0 * 1e-6)
    plan = _rc_plan(topology, frequency)
    result = verify_simulation_results(
        plan,
        _results(
            _run(
                run_id="ac-01",
                topology=topology,
                analysis_kind="ac",
                frequency_hz=frequency,
                vin=1.0 + 0.0j,
                vout=expected,
            )
        ),
    )

    assert result.status == "PASS"
    assert [item.metric for item in result.runs[0].comparisons] == [
        "vin_voltage",
        "transfer_function",
        "vout_voltage",
    ]
    assert result.runs[0].cutoff_frequency_hz == pytest.approx(frequency)
    for item in result.runs[0].comparisons:
        assert item.status == "PASS"
        assert item.reason_code == "verification.within_tolerance"


def test_exact_resistive_divider_and_negative_voltage() -> None:
    for input_voltage in (5.0, -5.0):
        expected_vout = input_voltage * (2.0 / 3.0)
        result = verify_simulation_results(
            _divider_plan(input_voltage),
            _results(
                _run(
                    run_id="dc-op",
                    topology="resistive_divider",
                    analysis_kind="dc",
                    frequency_hz=None,
                    vin=complex(input_voltage, 0.0),
                    vout=complex(expected_vout, 0.0),
                )
            ),
        )
        assert result.status == "PASS"
        assert [item.metric for item in result.runs[0].comparisons] == [
            "vin_voltage",
            "divider_ratio",
            "vout_voltage",
        ]
        ratio = _comparison(result, "divider_ratio")
        assert ratio.expected.real == pytest.approx(2.0 / 3.0)
        assert ratio.measured is not None
        assert ratio.measured.real == pytest.approx(2.0 / 3.0)
        assert result.runs[0].cutoff_frequency_hz is None


@pytest.mark.parametrize(
    ("delta_factor", "expected_status", "expected_reason"),
    [
        (0.5, "PASS", "verification.within_tolerance"),
        (2.0, "WARN", "verification.near_tolerance"),
        (11.0, "FAIL", "verification.outside_tolerance"),
    ],
)
def test_pass_warn_fail_policy(delta_factor: float, expected_status: str, expected_reason: str) -> None:
    plan = _divider_plan(1.0)
    expected_vout = 2.0 / 3.0
    pass_limit = VERIFICATION_ABSOLUTE_TOLERANCE + VERIFICATION_RELATIVE_TOLERANCE * abs(expected_vout)
    measured_vout = expected_vout + delta_factor * pass_limit
    result = verify_simulation_results(
        plan,
        _results(
            _run(
                run_id="dc-op",
                topology="resistive_divider",
                analysis_kind="dc",
                frequency_hz=None,
                vin=1.0 + 0.0j,
                vout=complex(measured_vout, 0.0),
            )
        ),
    )
    comparison = _comparison(result, "vout_voltage")
    assert comparison.status == expected_status
    assert comparison.reason_code == expected_reason
    assert comparison.pass_limit == pytest.approx(pass_limit)
    assert comparison.warning_limit == pytest.approx(10.0 * pass_limit)


def test_tolerance_boundaries_are_inclusive_and_unrounded() -> None:
    expected_vout = 2.0 / 3.0
    pass_limit = VERIFICATION_ABSOLUTE_TOLERANCE + VERIFICATION_RELATIVE_TOLERANCE * expected_vout

    cases = [
        (expected_vout + pass_limit, "PASS"),
        (math.nextafter(expected_vout + pass_limit, math.inf), "WARN"),
        (expected_vout + VERIFICATION_WARNING_MULTIPLIER * pass_limit, "WARN"),
        (
            math.nextafter(
                expected_vout + VERIFICATION_WARNING_MULTIPLIER * pass_limit,
                math.inf,
            ),
            "FAIL",
        ),
    ]

    for measured_vout, expected_status in cases:
        result = verify_simulation_results(
            _divider_plan(1.0),
            _results(
                _run(
                    run_id="dc-op",
                    topology="resistive_divider",
                    analysis_kind="dc",
                    frequency_hz=None,
                    vin=1.0 + 0.0j,
                    vout=complex(measured_vout, 0.0),
                )
            ),
        )
        assert _comparison(result, "vout_voltage").status == expected_status


def test_denominator_floor_boundary_is_exact() -> None:
    plan = _divider_plan(1.0)
    below = math.nextafter(VERIFICATION_DENOMINATOR_FLOOR, 0.0)
    below_result = verify_simulation_results(
        plan,
        _results(
            _run(
                run_id="dc-op",
                topology="resistive_divider",
                analysis_kind="dc",
                frequency_hz=None,
                vin=complex(below, 0.0),
                vout=complex(below * (2.0 / 3.0), 0.0),
            )
        ),
    )
    assert _comparison(below_result, "divider_ratio").reason_code == (
        "verification.denominator_too_small"
    )

    floor_result = verify_simulation_results(
        plan,
        _results(
            _run(
                run_id="dc-op",
                topology="resistive_divider",
                analysis_kind="dc",
                frequency_hz=None,
                vin=complex(VERIFICATION_DENOMINATOR_FLOOR, 0.0),
                vout=complex(VERIFICATION_DENOMINATOR_FLOOR * (2.0 / 3.0), 0.0),
            )
        ),
    )
    assert _comparison(floor_result, "divider_ratio").measured is not None


def test_near_zero_expected_value_has_null_relative_error_and_phase() -> None:
    plan = _rc_plan(
        "rc_high_pass",
        1e-6,
        resistance=1.0,
        capacitance=1e-15,
    )
    expected = _exact_rc("rc_high_pass", 1e-6, 1.0, 1e-15)
    result = verify_simulation_results(
        plan,
        _results(
            _run(
                run_id="ac-01",
                topology="rc_high_pass",
                analysis_kind="ac",
                frequency_hz=1e-6,
                vin=1.0 + 0.0j,
                vout=expected,
            )
        ),
    )
    comparison = _comparison(result, "transfer_function")
    assert comparison.relative_error is None
    assert comparison.expected.to_dict()["phase_degrees"] is None


def test_near_zero_measured_vin_produces_denominator_failure() -> None:
    plan = _rc_plan("rc_low_pass", 1000.0)
    result = verify_simulation_results(
        plan,
        _results(
            _run(
                run_id="ac-01",
                topology="rc_low_pass",
                analysis_kind="ac",
                frequency_hz=1000.0,
                vin=0.0 + 0.0j,
                vout=0.1 + 0.1j,
            )
        ),
    )
    comparison = _comparison(result, "transfer_function")
    assert comparison.measured is None
    assert comparison.absolute_error is None
    assert comparison.relative_error is None
    assert comparison.status == "FAIL"
    assert comparison.reason_code == "verification.denominator_too_small"
    assert result.status == "FAIL"


def test_scale_aware_complex_division_handles_huge_finite_components() -> None:
    plan = _divider_plan(1.0)
    result = verify_simulation_results(
        plan,
        _results(
            _run(
                run_id="dc-op",
                topology="resistive_divider",
                analysis_kind="dc",
                frequency_hz=None,
                vin=complex(1e308, 1e308),
                vout=complex(5e307, 5e307),
            )
        ),
    )
    ratio = _comparison(result, "divider_ratio")
    assert ratio.measured is not None
    assert ratio.measured.real == pytest.approx(0.5)
    assert ratio.measured.imag == pytest.approx(0.0)
    assert math.isfinite(ratio.absolute_error or 0.0)


def test_ordered_ac_runs_are_preserved() -> None:
    frequencies = (10.0, 1000.0)
    plan = CircuitPlan(
        schema_version=SCHEMA_VERSION,
        topology="rc_low_pass",
        analysis="ac",
        parameters={"resistance_ohms": 1000.0, "capacitance_farads": 1e-6},
        requested_frequencies_hz=frequencies,
        assumptions=(),
    )
    runs = tuple(
        _run(
            run_id=f"ac-{index + 1:02d}",
            topology="rc_low_pass",
            analysis_kind="ac",
            frequency_hz=frequency,
            vin=1.0 + 0.0j,
            vout=_exact_rc("rc_low_pass", frequency),
        )
        for index, frequency in enumerate(frequencies)
    )
    result = verify_simulation_results(plan, _results(*runs))
    assert [run.run_id for run in result.runs] == ["ac-01", "ac-02"]
    assert [run.frequency_hz for run in result.runs] == [10.0, 1000.0]


@pytest.mark.parametrize(
    "mutator",
    [
        lambda parsed: object.__setattr__(parsed.runs[0], "run_id", "ac-02"),
        lambda parsed: object.__setattr__(parsed.runs[0], "topology", "rc_high_pass"),
        lambda parsed: object.__setattr__(parsed.runs[0], "analysis_kind", "dc"),
        lambda parsed: object.__setattr__(parsed.runs[0], "frequency_hz", 999.0),
    ],
)
def test_plan_result_mismatch_is_rejected(mutator: object) -> None:
    plan = _rc_plan("rc_low_pass", 1000.0)
    parsed = _results(
        _run(
            run_id="ac-01",
            topology="rc_low_pass",
            analysis_kind="ac",
            frequency_hz=1000.0,
            vin=1.0 + 0.0j,
            vout=_exact_rc("rc_low_pass", 1000.0),
        )
    )
    mutator(parsed)  # type: ignore[operator]
    with pytest.raises(SimulationVerificationError) as captured:
        verify_simulation_results(plan, parsed)
    assert captured.value.code == "verification.results.mismatch"


def test_unsupported_parser_version_is_rejected() -> None:
    parsed = _results(
        _run(
            run_id="dc-op",
            topology="resistive_divider",
            analysis_kind="dc",
            frequency_hz=None,
            vin=5.0 + 0.0j,
            vout=(10.0 / 3.0) + 0.0j,
        ),
        version="9.9",
    )
    with pytest.raises(SimulationVerificationError) as captured:
        verify_simulation_results(_divider_plan(), parsed)
    assert captured.value.code == "verification.version.unsupported"
    assert captured.value.path == ("version",)


def test_invalid_but_well_typed_plan_maps_to_plan_invalid() -> None:
    plan = CircuitPlan(
        schema_version=SCHEMA_VERSION,
        topology="rc_low_pass",
        analysis="dc",
        parameters={"resistance_ohms": 1000.0, "capacitance_farads": 1e-6},
        requested_frequencies_hz=(1000.0,),
        assumptions=(),
    )
    with pytest.raises(SimulationVerificationError) as captured:
        verify_simulation_results(plan, object())  # type: ignore[arg-type]
    assert captured.value.code == "verification.plan.invalid"


def test_exact_outer_types_are_required() -> None:
    class PlanSubclass(CircuitPlan):
        pass

    with pytest.raises(SimulationVerificationError) as captured:
        verify_simulation_results(
            PlanSubclass(
                schema_version=SCHEMA_VERSION,
                topology="resistive_divider",
                analysis="dc",
                parameters={
                    "input_voltage_volts": 5.0,
                    "resistance_top_ohms": 1000.0,
                    "resistance_bottom_ohms": 2000.0,
                },
            ),
            object(),  # type: ignore[arg-type]
        )
    assert captured.value.code == "verification.input.malformed"


def test_hostile_numeric_subclass_is_rejected_before_hooks_execute() -> None:
    called = False

    class HostileFloat(float):
        def __eq__(self, other: object) -> bool:
            nonlocal called
            called = True
            raise AssertionError

        def __float__(self) -> float:
            nonlocal called
            called = True
            raise AssertionError

    run = _run(
        run_id="ac-01",
        topology="rc_low_pass",
        analysis_kind="ac",
        frequency_hz=1000.0,
        vin=1.0 + 0.0j,
        vout=_exact_rc("rc_low_pass", 1000.0),
    )
    object.__setattr__(run, "frequency_hz", HostileFloat(1000.0))
    with pytest.raises(SimulationVerificationError) as captured:
        verify_simulation_results(_rc_plan("rc_low_pass", 1000.0), _results(run))
    assert captured.value.code == "verification.input.malformed"
    assert called is False


def test_hostile_mapping_is_rejected_before_mapping_hooks_execute() -> None:
    called = False

    class HostileMapping(dict[str, float]):
        def __iter__(self):
            nonlocal called
            called = True
            raise AssertionError

    plan = _divider_plan()
    object.__setattr__(plan, "parameters", HostileMapping())
    with pytest.raises(SimulationVerificationError) as captured:
        verify_simulation_results(plan, object())  # type: ignore[arg-type]
    assert captured.value.code == "verification.input.malformed"
    assert called is False


def test_mapping_proxy_over_hostile_mapping_is_rejected_without_hooks() -> None:
    called = False

    class HostileMapping(dict[str, float]):
        def __iter__(self):
            nonlocal called
            called = True
            raise RuntimeError("hostile iterator executed")

        def __getitem__(self, key: str) -> float:
            nonlocal called
            called = True
            raise RuntimeError("hostile lookup executed")

    plan = _divider_plan()
    hostile = HostileMapping(dict(plan.parameters))
    object.__setattr__(plan, "parameters", MappingProxyType(hostile))

    with pytest.raises(SimulationVerificationError) as captured:
        verify_simulation_results(plan, object())  # type: ignore[arg-type]

    assert captured.value.code == "verification.input.malformed"
    assert captured.value.path == ("parameters",)
    assert called is False


def test_comparison_contract_rejects_incoherent_public_values() -> None:
    expected = VerificationComplexValue(1.0, 0.0)
    measured = VerificationComplexValue(1.0, 0.0)
    pass_limit = VERIFICATION_ABSOLUTE_TOLERANCE + VERIFICATION_RELATIVE_TOLERANCE
    valid = {
        "metric": "vin_voltage",
        "expected": expected,
        "measured": measured,
        "absolute_error": 0.0,
        "relative_error": 0.0,
        "pass_limit": pass_limit,
        "warning_limit": VERIFICATION_WARNING_MULTIPLIER * pass_limit,
        "status": "PASS",
        "reason_code": "verification.within_tolerance",
    }
    invalid_overrides = (
        {"metric": "arbitrary"},
        {"absolute_error": -1.0},
        {"relative_error": -1.0},
        {"pass_limit": 0.0},
        {"warning_limit": pass_limit},
        {"status": "FAIL"},
        {"reason_code": "verification.outside_tolerance"},
    )

    for override in invalid_overrides:
        values = {**valid, **override}
        with pytest.raises(SimulationVerificationError) as captured:
            VerificationComparison(**values)  # type: ignore[arg-type]
        assert captured.value.code == "verification.input.malformed"


def test_mutated_non_finite_voltage_is_rejected() -> None:
    run = _run(
        run_id="dc-op",
        topology="resistive_divider",
        analysis_kind="dc",
        frequency_hz=None,
        vin=5.0 + 0.0j,
        vout=(10.0 / 3.0) + 0.0j,
    )
    object.__setattr__(run.vout_voltage, "real", math.inf)
    with pytest.raises(SimulationVerificationError) as captured:
        verify_simulation_results(_divider_plan(), _results(run))
    assert captured.value.code == "verification.value.non_finite"


def test_numeric_overflow_is_normalized() -> None:
    run = _run(
        run_id="dc-op",
        topology="resistive_divider",
        analysis_kind="dc",
        frequency_hz=None,
        vin=5.0 + 0.0j,
        vout=complex(float.fromhex("0x1.fffffffffffffp+1023"), float.fromhex("0x1.fffffffffffffp+1023")),
    )
    with pytest.raises(SimulationVerificationError) as captured:
        verify_simulation_results(_divider_plan(), _results(run))
    assert captured.value.code == "verification.numeric_overflow"
    assert "1.797" not in captured.value.message


def test_result_contracts_are_frozen_and_tuple_backed() -> None:
    result = verify_simulation_results(
        _divider_plan(),
        _results(
            _run(
                run_id="dc-op",
                topology="resistive_divider",
                analysis_kind="dc",
                frequency_hz=None,
                vin=5.0 + 0.0j,
                vout=(10.0 / 3.0) + 0.0j,
            )
        ),
    )
    assert type(result.runs) is tuple
    assert type(result.runs[0].comparisons) is tuple
    assert type(result.runs[0].reason_codes) is tuple
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.status = "FAIL"  # type: ignore[misc]


def test_dictionary_and_json_are_canonical_and_ascii_safe() -> None:
    result = verify_simulation_results(
        _divider_plan(),
        _results(
            _run(
                run_id="dc-op",
                topology="resistive_divider",
                analysis_kind="dc",
                frequency_hz=None,
                vin=5.0 + 0.0j,
                vout=(10.0 / 3.0) + 0.0j,
            )
        ),
    )
    first = result.to_json()
    second = result.to_json()
    assert first == second
    assert first == json.dumps(
        result.to_dict(),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )
    assert json.loads(first) == result.to_dict()


def test_public_annotations_and_exports() -> None:
    assert inspect.signature(verify_simulation_results).parameters.keys() == {"plan", "parsed_results"}
    assert verify_simulation_results.__annotations__ == {
        "plan": CircuitPlan,
        "parsed_results": SimulationParsedResults,
        "return": SimulationVerificationResults,
    }
    for public_type in (
        VerificationTolerancePolicy,
        VerificationComplexValue,
        VerificationComparison,
        VerificationRunResult,
        SimulationVerificationResults,
    ):
        assert dataclasses.is_dataclass(public_type)


def test_fixed_policy_rejects_configuration() -> None:
    with pytest.raises(SimulationVerificationError) as captured:
        VerificationTolerancePolicy(absolute_tolerance=2e-9)
    assert captured.value.code == "verification.input.malformed"


def test_plan_parameters_are_normally_mapping_proxy() -> None:
    assert type(_divider_plan().parameters) is MappingProxyType
