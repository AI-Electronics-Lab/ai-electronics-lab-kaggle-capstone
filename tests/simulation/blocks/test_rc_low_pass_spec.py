from __future__ import annotations

import math

import pytest

from ai_electronics_lab.simulation.blocks.filters.rc_low_pass_spec import (
    RC_LOW_PASS_DEFAULT_CAPACITANCE_FARADS,
    RcLowPassPromptSpec,
    RcLowPassSpecError,
    parse_rc_low_pass_prompt,
    resolve_rc_low_pass_spec,
)


@pytest.mark.parametrize(
    ("prompt", "expected_resistance_ohms", "expected_capacitance_farads", "expected_cutoff_frequency_hz"),
    [
        (
            "RC low-pass: fc = 1 kHz",
            1591.5494309189535,
            RC_LOW_PASS_DEFAULT_CAPACITANCE_FARADS,
            1000.0,
        ),
        (
            "ФНЧ: срез 500 Hz, резистор 1 kΩ",
            1000.0,
            318.3098861837907e-9,
            500.0,
        ),
        (
            "RC low-pass: fc 1 kHz, capacitor 220 nF",
            723.4315595086152,
            220e-9,
            1000.0,
        ),
    ],
)
def test_resolve_rc_low_pass_spec_applies_the_documented_resolution_rules(
    prompt: str,
    expected_resistance_ohms: float,
    expected_capacitance_farads: float,
    expected_cutoff_frequency_hz: float,
):
    spec = resolve_rc_low_pass_spec(prompt)

    assert math.isclose(spec.resistance_ohms or 0.0, expected_resistance_ohms, rel_tol=1e-9)
    assert math.isclose(spec.capacitance_farads or 0.0, expected_capacitance_farads, rel_tol=1e-9)
    assert math.isclose(spec.cutoff_frequency_hz or 0.0, expected_cutoff_frequency_hz, rel_tol=1e-9)


def test_parse_rc_low_pass_prompt_handles_ru_markers_units_and_input_frequency():
    spec = parse_rc_low_pass_prompt("ФНЧ, низкочастотный срез 1 кГц, вход 10 кГц, конденсатор 220 нФ")

    assert spec.markers[:3] == ("фнч", "низкочастотный", "срез")
    assert math.isclose(spec.cutoff_frequency_hz or 0.0, 1000.0, rel_tol=1e-9)
    assert math.isclose(spec.input_frequency_hz or 0.0, 10000.0, rel_tol=1e-9)
    assert math.isclose(spec.capacitance_farads or 0.0, 220e-9, rel_tol=1e-9)
    assert spec.resistance_ohms is None


def test_parse_rc_low_pass_prompt_understands_russian_set_capacitor_phrase():
    spec = parse_rc_low_pass_prompt("Поставь конденсатор на 1 мкФ. Сохрани все остальные параметрнтры.")

    assert math.isclose(spec.capacitance_farads or 0.0, 1e-6, rel_tol=1e-9)
    assert spec.resistance_ohms is None
    assert spec.cutoff_frequency_hz is None


def test_parse_rc_low_pass_prompt_retains_explicit_r_c_and_milli_units():
    spec = parse_rc_low_pass_prompt("R1 1 mOhm C1 100 nF cutoff frequency 1 kHz")

    assert math.isclose(spec.resistance_ohms or 0.0, 1e-3, rel_tol=1e-9)
    assert math.isclose(spec.capacitance_farads or 0.0, 100e-9, rel_tol=1e-9)
    assert math.isclose(spec.cutoff_frequency_hz or 0.0, 1000.0, rel_tol=1e-9)


def test_parse_rc_low_pass_prompt_preserves_uppercase_mega_prefixes():
    spec = parse_rc_low_pass_prompt("resistor 1 MOhm input 1 MHz")

    assert math.isclose(spec.resistance_ohms or 0.0, 1e6, rel_tol=1e-9)
    assert math.isclose(spec.input_frequency_hz or 0.0, 1e6, rel_tol=1e-9)


@pytest.mark.parametrize(
    "prompt, match",
    [
        ("RC low-pass: resistor 1 kΩ", "resistance-only"),
        ("RC low-pass: capacitor 220 nF", "capacitance-only"),
    ],
)
def test_resolve_rc_low_pass_spec_rejects_partial_specs_without_a_cutoff(prompt: str, match: str):
    with pytest.raises(RcLowPassSpecError, match=match):
        resolve_rc_low_pass_spec(prompt)


@pytest.mark.parametrize(
    "spec",
    [
        RcLowPassPromptSpec(resistance_ohms=0.5, capacitance_farads=100e-9),
        RcLowPassPromptSpec(resistance_ohms=1000.0, capacitance_farads=2.0),
    ],
)
def test_resolve_rc_low_pass_spec_enforces_validation_ranges(spec: RcLowPassPromptSpec):
    with pytest.raises(RcLowPassSpecError, match="within"):
        resolve_rc_low_pass_spec(spec)


def test_resolve_rc_low_pass_spec_rejects_inconsistent_explicit_triplets():
    with pytest.raises(RcLowPassSpecError, match="inconsistent"):
        resolve_rc_low_pass_spec(
            RcLowPassPromptSpec(
                resistance_ohms=1000.0,
                capacitance_farads=100e-9,
                cutoff_frequency_hz=999.0,
            )
        )
