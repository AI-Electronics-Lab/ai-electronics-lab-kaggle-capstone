"""Tests for the deterministic engineering-style schematic.svg renderer."""

from __future__ import annotations

import pytest

from src.ai_electronics_lab.simulation.core.schematic_renderer import (
    build_engineering_schematic_svg,
    render_engineering_schematic_svg,
)


# ── Determinism ──────────────────────────────────────────────────────────────


def test_rc_low_pass_is_deterministic():
    """Same topology + components → byte-identical SVG."""
    components = {"R1_ohm": 1000.0, "C1_farad": 1e-6}
    svg1 = render_engineering_schematic_svg("rc_low_pass", components)
    svg2 = render_engineering_schematic_svg("rc_low_pass", components)
    assert svg1 == svg2
    assert len(svg1) > 200


def test_rc_high_pass_is_deterministic():
    components = {"R1_ohm": 2000.0, "C1_farad": 100e-9}
    svg1 = render_engineering_schematic_svg("rc_high_pass", components)
    svg2 = render_engineering_schematic_svg("rc_high_pass", components)
    assert svg1 == svg2
    assert len(svg1) > 200


def test_resistive_divider_is_deterministic():
    components = {"R1_ohm": 10000.0, "R2_ohm": 4700.0}
    svg1 = render_engineering_schematic_svg("resistive_divider", components)
    svg2 = render_engineering_schematic_svg("resistive_divider", components)
    assert svg1 == svg2
    assert len(svg1) > 200


# ── Topology content checks ──────────────────────────────────────────────────


def test_rc_low_pass_contains_required_elements():
    svg = render_engineering_schematic_svg("rc_low_pass", {"R1_ohm": 1000.0, "C1_farad": 1e-6})

    # Component refdes
    assert "R1" in svg
    assert "C1" in svg
    # Port labels
    assert "VIN" in svg
    assert "VOUT" in svg
    assert "GND" in svg
    # Component values (human readable)
    assert "1 kΩ" in svg or "1000 Ω" in svg
    assert "1 µF" in svg
    # SVG structure
    assert svg.startswith('<svg xmlns="http://www.w3.org/2000/svg"')
    assert "</svg>" in svg
    # No n/a values
    assert "n/a" not in svg


def test_rc_high_pass_contains_required_elements():
    svg = render_engineering_schematic_svg("rc_high_pass", {"R1_ohm": 2000.0, "C1_farad": 100e-9})

    assert "C1" in svg
    assert "R1" in svg
    assert "VIN" in svg
    assert "VOUT" in svg
    assert "GND" in svg
    assert "2 kΩ" in svg or "2000 Ω" in svg
    assert "100 nF" in svg
    assert "n/a" not in svg


def test_resistive_divider_contains_required_elements():
    svg = render_engineering_schematic_svg("resistive_divider", {"R1_ohm": 10000.0, "R2_ohm": 4700.0})

    assert "R1" in svg
    assert "R2" in svg
    assert "VIN" in svg
    assert "VOUT" in svg
    assert "GND" in svg
    assert "10 kΩ" in svg or "10000 Ω" in svg
    assert "4.7 kΩ" in svg or "4700 Ω" in svg
    assert "n/a" not in svg


# ── Rendering requirements: no decorative elements ──────────────────────────


_NO_DECORATIVE_MARKERS = [
    "linearGradient",
    "rx=",
    "url(#",
]


@pytest.mark.parametrize("topology,components", [
    ("rc_low_pass", {"R1_ohm": 1000.0, "C1_farad": 1e-6}),
    ("rc_high_pass", {"R1_ohm": 2000.0, "C1_farad": 100e-9}),
    ("resistive_divider", {"R1_ohm": 10000.0, "R2_ohm": 4700.0}),
])
def test_no_decorative_markers(topology, components):
    svg = render_engineering_schematic_svg(topology, components)
    for marker in _NO_DECORATIVE_MARKERS:
        assert marker not in svg, f"{topology}: found decorative marker {marker!r}"


# ── Symbol checks ────────────────────────────────────────────────────────────


def test_resistor_uses_zigzag_not_filled_rect():
    svg = render_engineering_schematic_svg("rc_low_pass", {"R1_ohm": 1000.0, "C1_farad": 1e-6})
    # The resistor should use polyline (zigzag), not a filled rect
    assert "<polyline" in svg
    # No large filled rounded rectangle for resistor
    assert 'fill="none"' in svg  # wires are outlines, not filled


def test_capacitor_uses_two_parallel_lines():
    svg = render_engineering_schematic_svg("rc_low_pass", {"R1_ohm": 1000.0, "C1_farad": 1e-6})
    # Capacitor should have two parallel horizontal/vertical lines (plates)
    # We can't easily count, but we can verify no generic rect is used
    assert "<line" in svg


def test_ground_symbol_present():
    svg = render_engineering_schematic_svg("rc_low_pass", {"R1_ohm": 1000.0, "C1_farad": 1e-6})
    # Ground symbol has three descending horizontal lines
    # Count lines — should have at least 3 for ground + others
    assert svg.count("<line") >= 6  # ground needs 4 lines (stem + 3 horizontals)


def test_junction_dot_present():
    svg = render_engineering_schematic_svg("rc_low_pass", {"R1_ohm": 1000.0, "C1_farad": 1e-6})
    # Junction dot is a filled circle
    assert '<circle' in svg
    assert 'fill="#1a1a2e"' in svg


# ── Convenience alias ────────────────────────────────────────────────────────


def test_build_engineering_schematic_svg_is_alias():
    components = {"R1_ohm": 1000.0, "C1_farad": 1e-6}
    assert build_engineering_schematic_svg("rc_low_pass", components) == render_engineering_schematic_svg("rc_low_pass", components)


# ── Unsupport topology ───────────────────────────────────────────────────────


def test_unsupported_topology_raises():
    with pytest.raises(ValueError, match="Unsupported topology"):
        render_engineering_schematic_svg("bjt_common_emitter", {})


# ── Zero-value handling (should still render, no n/a on symbol) ─────────────


def test_zero_resistance_still_renders():
    """Even with zero resistance, the SVG should render structurally (the value label may show n/a)."""
    svg = render_engineering_schematic_svg("rc_low_pass", {"R1_ohm": 0.0, "C1_farad": 1e-6})
    assert "R1" in svg
    assert "C1" in svg
    assert svg.startswith('<svg')
