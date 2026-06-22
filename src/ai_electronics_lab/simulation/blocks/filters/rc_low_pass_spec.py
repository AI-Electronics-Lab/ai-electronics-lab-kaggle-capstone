from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from math import pi
from typing import Iterable

__all__ = [
    "RC_LOW_PASS_DEFAULT_CAPACITANCE_FARADS",
    "RC_LOW_PASS_MAX_CAPACITANCE_FARADS",
    "RC_LOW_PASS_MAX_FREQUENCY_HZ",
    "RC_LOW_PASS_MAX_RESISTANCE_OHMS",
    "RC_LOW_PASS_MIN_CAPACITANCE_FARADS",
    "RC_LOW_PASS_MIN_FREQUENCY_HZ",
    "RC_LOW_PASS_MIN_RESISTANCE_OHMS",
    "RcLowPassPromptSpec",
    "RcLowPassSpecError",
    "parse_rc_low_pass_prompt",
    "resolve_rc_low_pass_spec",
]

RC_LOW_PASS_DEFAULT_CAPACITANCE_FARADS = 100e-9
RC_LOW_PASS_MIN_RESISTANCE_OHMS = 1.0
RC_LOW_PASS_MAX_RESISTANCE_OHMS = 1e9
RC_LOW_PASS_MIN_CAPACITANCE_FARADS = 1e-15
RC_LOW_PASS_MAX_CAPACITANCE_FARADS = 1.0
RC_LOW_PASS_MIN_FREQUENCY_HZ = 1e-6
RC_LOW_PASS_MAX_FREQUENCY_HZ = 1e9


class RcLowPassSpecError(ValueError):
    """Raised when an RC low-pass prompt/spec cannot be parsed or resolved."""


@dataclass(frozen=True, slots=True)
class RcLowPassPromptSpec:
    raw_text: str = ""
    resistance_ohms: float | None = None
    capacitance_farads: float | None = None
    cutoff_frequency_hz: float | None = None
    input_frequency_hz: float | None = None
    markers: tuple[str, ...] = ()

    def is_resolved(self) -> bool:
        return (
            self.resistance_ohms is not None
            and self.capacitance_farads is not None
            and self.cutoff_frequency_hz is not None
        )


_LABEL_MARKERS = (
    "фнч",
    "низкочастотный",
    "срез",
    "конденсатор",
    "резистор",
    "low-pass",
    "low pass",
    "cutoff",
    "corner frequency",
    "corner",
    "capacitor",
    "resistor",
    "frequency",
    "input",
    "vin",
    "r=",
    "c=",
    "fc=",
)

_NUMBER_PATTERN = r"(?P<value>\d+(?:[.,]\d+)?(?:[eE][-+]?\d+)?)"
_UNIT_TOKEN_PATTERN = r"(?P<unit>[\w\u00B5\u03BC\u03A9\u03C9\u0410-\u044F]+)?"

_RESISTANCE_LABELS = (
    r"\br\d+\b",
    r"\br\b",
    r"resistor",
    r"резистор",
)
_CAPACITANCE_LABELS = (
    r"\bc\d+\b",
    r"\bc\b",
    r"capacitor",
    r"конденсатор",
)
_CUTOFF_LABELS = (
    r"\bfc\b",
    r"cutoff(?:\s+frequency)?",
    r"corner(?:\s+frequency)?",
    r"срез",
)
_INPUT_FREQUENCY_LABELS = (
    r"input(?:\s+frequency)?",
    r"\bvin\b",
    r"\bвход\b(?:ная)?(?:\s+частота)?",
)


def parse_rc_low_pass_prompt(prompt: str) -> RcLowPassPromptSpec:
    if not isinstance(prompt, str):
        raise RcLowPassSpecError("prompt must be a string")

    text = unicodedata.normalize("NFKC", prompt)
    normalized_text = _normalize_text(prompt)
    markers = tuple(marker for marker in _LABEL_MARKERS if marker in normalized_text)

    resistance_ohms = _extract_quantity(text, _RESISTANCE_LABELS, kind="resistance")
    capacitance_farads = _extract_quantity(text, _CAPACITANCE_LABELS, kind="capacitance")
    cutoff_frequency_hz = _extract_quantity(text, _CUTOFF_LABELS, kind="frequency") or _extract_bare_frequency(text)
    input_frequency_hz = _extract_quantity(text, _INPUT_FREQUENCY_LABELS, kind="frequency")

    return RcLowPassPromptSpec(
        raw_text=prompt,
        resistance_ohms=resistance_ohms,
        capacitance_farads=capacitance_farads,
        cutoff_frequency_hz=cutoff_frequency_hz,
        input_frequency_hz=input_frequency_hz,
        markers=markers,
    )


def _extract_bare_frequency(text: str) -> float | None:
    patterns = (
        rf"{_NUMBER_PATTERN}\s*(?P<unit>[\w\u00B5\u03BC\u03A9\u03C9\u0410-\u044F]+)",
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match is None:
            continue
        value = _parse_number(match.group("value"))
        unit_token = match.groupdict().get("unit") or ""
        try:
            return _convert_quantity(value, unit_token, kind="frequency")
        except RcLowPassSpecError:
            continue
    return None


def resolve_rc_low_pass_spec(spec_or_prompt: str | RcLowPassPromptSpec) -> RcLowPassPromptSpec:
    if isinstance(spec_or_prompt, str):
        spec = parse_rc_low_pass_prompt(spec_or_prompt)
    elif isinstance(spec_or_prompt, RcLowPassPromptSpec):
        spec = spec_or_prompt
    else:
        raise RcLowPassSpecError("spec_or_prompt must be a string or RcLowPassPromptSpec")

    resistance_ohms = spec.resistance_ohms
    capacitance_farads = spec.capacitance_farads
    cutoff_frequency_hz = spec.cutoff_frequency_hz

    supplied = sum(
        value is not None
        for value in (resistance_ohms, capacitance_farads, cutoff_frequency_hz)
    )

    if supplied == 3:
        _validate_resistance(resistance_ohms)
        _validate_capacitance(capacitance_farads)
        _validate_frequency(cutoff_frequency_hz)
        assert resistance_ohms is not None
        assert capacitance_farads is not None
        assert cutoff_frequency_hz is not None
        expected_cutoff_frequency_hz = _derive_cutoff_frequency_hz(resistance_ohms, capacitance_farads)
        if not _within_tolerance(cutoff_frequency_hz, expected_cutoff_frequency_hz):
            raise RcLowPassSpecError(
                "supplied R, C, and cutoff frequency are inconsistent"
            )
        return spec

    if resistance_ohms is not None and capacitance_farads is not None:
        _validate_resistance(resistance_ohms)
        _validate_capacitance(capacitance_farads)
        cutoff_frequency_hz = _derive_cutoff_frequency_hz(resistance_ohms, capacitance_farads)
    elif cutoff_frequency_hz is not None and capacitance_farads is not None:
        _validate_frequency(cutoff_frequency_hz)
        _validate_capacitance(capacitance_farads)
        resistance_ohms = _derive_resistance_ohms(cutoff_frequency_hz, capacitance_farads)
    elif cutoff_frequency_hz is not None and resistance_ohms is not None:
        _validate_frequency(cutoff_frequency_hz)
        _validate_resistance(resistance_ohms)
        capacitance_farads = _derive_capacitance_farads(cutoff_frequency_hz, resistance_ohms)
    elif cutoff_frequency_hz is not None:
        _validate_frequency(cutoff_frequency_hz)
        capacitance_farads = RC_LOW_PASS_DEFAULT_CAPACITANCE_FARADS
        resistance_ohms = _derive_resistance_ohms(cutoff_frequency_hz, capacitance_farads)
    elif resistance_ohms is not None and capacitance_farads is None:
        raise RcLowPassSpecError(
            "resistance-only RC prompts need an explicit cutoff frequency or a documented default counterpart"
        )
    elif capacitance_farads is not None and resistance_ohms is None:
        raise RcLowPassSpecError(
            "capacitance-only RC prompts need an explicit cutoff frequency or a documented default counterpart"
        )
    else:
        raise RcLowPassSpecError(
            "RC low-pass prompts must provide at least a cutoff frequency or an R/C pair"
        )

    _validate_resistance(resistance_ohms)
    _validate_capacitance(capacitance_farads)
    _validate_frequency(cutoff_frequency_hz)

    return RcLowPassPromptSpec(
        raw_text=spec.raw_text,
        resistance_ohms=resistance_ohms,
        capacitance_farads=capacitance_farads,
        cutoff_frequency_hz=cutoff_frequency_hz,
        input_frequency_hz=spec.input_frequency_hz,
        markers=spec.markers,
    )


def _normalize_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text).lower()
    return normalized.replace("μ", "u").replace("µ", "u")


def _extract_quantity(text: str, labels: Iterable[str], *, kind: str) -> float | None:
    label_pattern = "|".join(labels)
    patterns = (
        rf"(?:{label_pattern})\s*(?:[:=]|\bна\b|\bв\b)?\s*{_NUMBER_PATTERN}\s*{_UNIT_TOKEN_PATTERN}",
        rf"{_NUMBER_PATTERN}\s*{_UNIT_TOKEN_PATTERN}\s*(?:{label_pattern})",
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match is None:
            continue
        value = _parse_number(match.group("value"))
        unit_token = match.groupdict().get("unit") or ""
        return _convert_quantity(value, unit_token, kind=kind)
    return None


def _parse_number(raw_value: str) -> float:
    return float(raw_value.replace(",", "."))


def _convert_quantity(value: float, unit_token: str, *, kind: str) -> float:
    scale = _unit_scale(unit_token, kind=kind)
    return value * scale


def _unit_scale(unit_token: str, *, kind: str) -> float:
    normalized = _normalize_unit_token(unit_token)
    if normalized == "":
        return 1.0

    exact_aliases = _exact_unit_aliases(kind)
    if normalized in exact_aliases:
        return exact_aliases[normalized]

    prefix, base = _split_prefix_and_base(normalized)
    if base not in _base_units(kind):
        if base == "":
            return _prefix_scale(prefix, kind=kind)
        raise RcLowPassSpecError(f"unsupported {kind} unit: {unit_token!r}")

    return _prefix_scale(prefix, kind=kind) * _base_unit_scale(base, kind=kind)


def _normalize_unit_token(unit_token: str) -> str:
    normalized = unicodedata.normalize("NFKC", unit_token).strip()
    normalized = normalized.replace("μ", "u").replace("µ", "u")
    normalized = normalized.replace("мк", "u")
    normalized = normalized.replace("Ω", "ohm").replace("ω", "ohm")
    normalized = normalized.replace("Ом", "ohm").replace("ом", "ohm")
    normalized = normalized.replace("оhm", "ohm")
    normalized = normalized.replace("Ф", "f").replace("ф", "f")
    normalized = normalized.replace("Гц", "hz").replace("гц", "hz")
    normalized = normalized.replace("К", "K").replace("к", "k")
    normalized = normalized.replace("М", "M").replace("м", "m")
    normalized = normalized.replace("П", "p").replace("п", "p")
    normalized = normalized.replace("Н", "n").replace("н", "n")
    normalized = normalized.replace("u", "u").replace("U", "U")
    return normalized


def _split_prefix_and_base(normalized_unit: str) -> tuple[str, str]:
    bases = ("ohm", "hz", "f")
    normalized_lower = normalized_unit.casefold()
    for base in bases:
        if normalized_lower.endswith(base):
            return normalized_unit[: -len(base)], base
    return normalized_unit, ""


def _base_units(kind: str) -> tuple[str, ...]:
    if kind == "resistance":
        return ("ohm",)
    if kind == "frequency":
        return ("hz",)
    if kind == "capacitance":
        return ("f",)
    raise RcLowPassSpecError(f"unsupported quantity kind: {kind!r}")


def _exact_unit_aliases(kind: str) -> dict[str, float]:
    if kind == "resistance":
        return {
            "ohm": 1.0,
            "": 1.0,
        }
    if kind == "frequency":
        return {
            "hz": 1.0,
            "": 1.0,
        }
    if kind == "capacitance":
        return {
            "f": 1.0,
            "": 1.0,
        }
    raise RcLowPassSpecError(f"unsupported quantity kind: {kind!r}")


def _prefix_scale(prefix: str, *, kind: str) -> float:
    if prefix == "":
        return 1.0
    prefix_scales = {
        "resistance": {"k": 1e3, "K": 1e3, "M": 1e6, "m": 1e-3, "g": 1e9, "G": 1e9, "d": 1e-1, "c": 1e-2, "milli": 1e-3},
        "frequency": {"k": 1e3, "K": 1e3, "M": 1e6, "m": 1e-3, "g": 1e9, "G": 1e9, "d": 1e-1, "c": 1e-2, "milli": 1e-3},
        "capacitance": {
            "u": 1e-6,
            "U": 1e-6,
            "n": 1e-9,
            "N": 1e-9,
            "p": 1e-12,
            "P": 1e-12,
            "f": 1e-15,
            "F": 1e-15,
            "k": 1e3,
            "K": 1e3,
            "M": 1e6,
            "m": 1e-3,
            "milli": 1e-3,
        },
    }
    scales = prefix_scales[kind]
    if prefix in scales:
        return scales[prefix]
    raise RcLowPassSpecError(f"unsupported {kind} prefix: {prefix!r}")


def _base_unit_scale(base: str, *, kind: str) -> float:
    if kind == "resistance" and base == "ohm":
        return 1.0
    if kind == "frequency" and base == "hz":
        return 1.0
    if kind == "capacitance" and base == "f":
        return 1.0
    raise RcLowPassSpecError(f"unsupported {kind} unit: {base!r}")


def _derive_cutoff_frequency_hz(resistance_ohms: float, capacitance_farads: float) -> float:
    return 1.0 / (2.0 * pi * resistance_ohms * capacitance_farads)


def _derive_resistance_ohms(cutoff_frequency_hz: float, capacitance_farads: float) -> float:
    return 1.0 / (2.0 * pi * cutoff_frequency_hz * capacitance_farads)


def _derive_capacitance_farads(cutoff_frequency_hz: float, resistance_ohms: float) -> float:
    return 1.0 / (2.0 * pi * cutoff_frequency_hz * resistance_ohms)


def _validate_resistance(value: float | None) -> None:
    if value is None:
        raise RcLowPassSpecError("resistance_ohms is required")
    if not (RC_LOW_PASS_MIN_RESISTANCE_OHMS <= value <= RC_LOW_PASS_MAX_RESISTANCE_OHMS):
        raise RcLowPassSpecError(
            f"resistance_ohms must be within {RC_LOW_PASS_MIN_RESISTANCE_OHMS:g}..{RC_LOW_PASS_MAX_RESISTANCE_OHMS:g} ohms"
        )


def _validate_capacitance(value: float | None) -> None:
    if value is None:
        raise RcLowPassSpecError("capacitance_farads is required")
    if not (RC_LOW_PASS_MIN_CAPACITANCE_FARADS <= value <= RC_LOW_PASS_MAX_CAPACITANCE_FARADS):
        raise RcLowPassSpecError(
            f"capacitance_farads must be within {RC_LOW_PASS_MIN_CAPACITANCE_FARADS:g}..{RC_LOW_PASS_MAX_CAPACITANCE_FARADS:g} farads"
        )


def _validate_frequency(value: float | None) -> None:
    if value is None:
        raise RcLowPassSpecError("cutoff_frequency_hz is required")
    if not (RC_LOW_PASS_MIN_FREQUENCY_HZ <= value <= RC_LOW_PASS_MAX_FREQUENCY_HZ):
        raise RcLowPassSpecError(
            f"cutoff_frequency_hz must be within {RC_LOW_PASS_MIN_FREQUENCY_HZ:g}..{RC_LOW_PASS_MAX_FREQUENCY_HZ:g} hertz"
        )


def _within_tolerance(left: float, right: float) -> bool:
    return abs(left - right) <= max(1e-9, abs(right) * 1e-6)
