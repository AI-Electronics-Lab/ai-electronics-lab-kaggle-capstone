"""Versioned, deterministic circuit-plan contract."""

from __future__ import annotations

import copy
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

SCHEMA_VERSION = "1.0"
SUPPORTED_TOPOLOGIES = frozenset({"rc_low_pass", "rc_high_pass", "resistive_divider"})
SUPPORTED_ANALYSES = frozenset({"ac", "dc"})

MIN_RESISTANCE_OHMS = 1.0
MAX_RESISTANCE_OHMS = 1e9
MIN_CAPACITANCE_FARADS = 1e-15
MAX_CAPACITANCE_FARADS = 1.0
MIN_FREQUENCY_HZ = 1e-6
MAX_FREQUENCY_HZ = 1e9
MAX_INPUT_VOLTAGE_VOLTS = 1e6
MAX_REQUESTED_FREQUENCIES = 32
MAX_ASSUMPTIONS = 20
MAX_ASSUMPTION_LENGTH = 240

_TOPOLOGY_ANALYSIS = {
    "rc_high_pass": "ac",
    "rc_low_pass": "ac",
    "resistive_divider": "dc",
}
_TOPOLOGY_PARAMETERS = {
    "rc_high_pass": ("capacitance_farads", "resistance_ohms"),
    "rc_low_pass": ("capacitance_farads", "resistance_ohms"),
    "resistive_divider": (
        "input_voltage_volts",
        "resistance_bottom_ohms",
        "resistance_top_ohms",
    ),
}


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({copy.deepcopy(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return frozenset(_freeze(item) for item in value)
    return copy.deepcopy(value)


def _as_frozen_sequence(value: Any) -> Any:
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return _freeze(value)


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    if isinstance(value, frozenset):
        return sorted((_thaw(item) for item in value), key=repr)
    return copy.deepcopy(value)


@dataclass(frozen=True, slots=True)
class CircuitPlan:
    """Immutable planner output; call validation before deterministic use."""

    schema_version: str
    topology: str
    analysis: str
    parameters: Mapping[str, Any]
    requested_frequencies_hz: tuple[Any, ...] = ()
    assumptions: tuple[Any, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "parameters", _freeze(self.parameters))
        object.__setattr__(
            self,
            "requested_frequencies_hz",
            _as_frozen_sequence(self.requested_frequencies_hz),
        )
        object.__setattr__(self, "assumptions", _as_frozen_sequence(self.assumptions))

    def to_dict(self) -> dict[str, Any]:
        parameters = _thaw(self.parameters)
        if isinstance(parameters, dict):
            parameters = {key: parameters[key] for key in sorted(parameters, key=str)}
        return {
            "schema_version": self.schema_version,
            "topology": self.topology,
            "analysis": self.analysis,
            "parameters": parameters,
            "requested_frequencies_hz": _thaw(self.requested_frequencies_hz),
            "assumptions": _thaw(self.assumptions),
        }

    def to_json(self) -> str:
        return json.dumps(
            self.to_dict(),
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
        )


@dataclass(frozen=True, slots=True)
class ValidationError:
    """A stable, structured circuit-plan validation failure."""

    code: str
    path: tuple[str | int, ...]
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "path": list(self.path), "message": self.message}


class CircuitPlanValidationError(ValueError):
    """Raised when a valid CircuitPlan is required but validation fails."""

    def __init__(self, errors: tuple[ValidationError, ...]) -> None:
        self.errors = errors
        super().__init__(f"CircuitPlan validation failed with {len(errors)} error(s)")


def _error(code: str, path: tuple[str | int, ...], message: str) -> ValidationError:
    return ValidationError(code=code, path=path, message=message)


def _numeric_error(
    value: Any,
    path: tuple[str | int, ...],
    minimum: float,
    maximum: float,
    *,
    magnitude: bool = False,
) -> ValidationError | None:
    if isinstance(value, bool):
        return _error("number.boolean", path, "boolean values are not numeric contract values")
    if not isinstance(value, (int, float)):
        code = "value.mutable" if isinstance(value, (Mapping, tuple, frozenset)) else "number.type"
        return _error(code, path, "value must be an int or float")
    if not math.isfinite(value):
        return _error("number.non_finite", path, "value must be finite")
    comparable = abs(value) if magnitude else value
    if comparable < minimum or comparable > maximum:
        return _error(
            "number.out_of_range",
            path,
            f"value must be between {minimum} and {maximum}",
        )
    return None


def validate_circuit_plan(plan: CircuitPlan) -> tuple[ValidationError, ...]:
    """Return every deterministic validation error in stable order."""

    errors: list[ValidationError] = []
    if plan.schema_version != SCHEMA_VERSION:
        errors.append(
            _error(
                "schema_version.unsupported",
                ("schema_version",),
                f"schema_version must be {SCHEMA_VERSION!r}",
            )
        )

    topology_supported = (
        isinstance(plan.topology, str) and plan.topology in SUPPORTED_TOPOLOGIES
    )
    if not topology_supported:
        errors.append(_error("topology.unsupported", ("topology",), "topology is not supported"))

    if not isinstance(plan.analysis, str) or plan.analysis not in SUPPORTED_ANALYSES:
        errors.append(_error("analysis.unsupported", ("analysis",), "analysis is not supported"))
    elif topology_supported and plan.analysis != _TOPOLOGY_ANALYSIS[plan.topology]:
        errors.append(
            _error(
                "analysis.topology_mismatch",
                ("analysis",),
                "analysis does not match the selected topology",
            )
        )

    if not isinstance(plan.parameters, Mapping):
        errors.append(_error("parameters.type", ("parameters",), "parameters must be a mapping"))
    elif topology_supported:
        required = set(_TOPOLOGY_PARAMETERS[plan.topology])
        actual = set(plan.parameters)
        for key in sorted(required - actual):
            errors.append(
                _error("parameter.missing", ("parameters", key), "required parameter is missing")
            )
        for key in sorted(actual - required, key=str):
            errors.append(
                _error("parameter.unknown", ("parameters", str(key)), "parameter is not allowed")
            )
        for key in sorted(required & actual):
            value = plan.parameters[key]
            if "resistance" in key:
                numeric_error = _numeric_error(
                    value,
                    ("parameters", key),
                    MIN_RESISTANCE_OHMS,
                    MAX_RESISTANCE_OHMS,
                )
            elif key == "capacitance_farads":
                numeric_error = _numeric_error(
                    value,
                    ("parameters", key),
                    MIN_CAPACITANCE_FARADS,
                    MAX_CAPACITANCE_FARADS,
                )
            else:
                numeric_error = _numeric_error(
                    value,
                    ("parameters", key),
                    math.nextafter(0.0, 1.0),
                    MAX_INPUT_VOLTAGE_VOLTS,
                    magnitude=True,
                )
            if numeric_error is not None:
                errors.append(numeric_error)

    frequencies = plan.requested_frequencies_hz
    if not isinstance(frequencies, tuple):
        errors.append(
            _error(
                "frequencies.type",
                ("requested_frequencies_hz",),
                "requested frequencies must be a sequence",
            )
        )
    else:
        if len(frequencies) > MAX_REQUESTED_FREQUENCIES:
            errors.append(
                _error(
                    "frequencies.too_many",
                    ("requested_frequencies_hz",),
                    f"at most {MAX_REQUESTED_FREQUENCIES} frequencies are allowed",
                )
            )
        if topology_supported and plan.topology == "resistive_divider" and frequencies:
            errors.append(
                _error(
                    "frequencies.not_allowed_for_dc",
                    ("requested_frequencies_hz",),
                    "requested frequencies are not allowed for a DC divider",
                )
            )
        comparable_frequencies: list[float] = []
        all_comparable = True
        for index, value in enumerate(frequencies):
            numeric_error = _numeric_error(
                value,
                ("requested_frequencies_hz", index),
                MIN_FREQUENCY_HZ,
                MAX_FREQUENCY_HZ,
            )
            if numeric_error is not None:
                errors.append(numeric_error)
                all_comparable = False
            else:
                comparable_frequencies.append(float(value))
        if all_comparable and any(
            current <= previous
            for previous, current in zip(comparable_frequencies, comparable_frequencies[1:])
        ):
            errors.append(
                _error(
                    "frequencies.not_strictly_increasing",
                    ("requested_frequencies_hz",),
                    "requested frequencies must be strictly increasing and unique",
                )
            )

    assumptions = plan.assumptions
    if not isinstance(assumptions, tuple):
        errors.append(_error("assumptions.type", ("assumptions",), "assumptions must be a sequence"))
    else:
        if len(assumptions) > MAX_ASSUMPTIONS:
            errors.append(
                _error(
                    "assumptions.too_many",
                    ("assumptions",),
                    f"at most {MAX_ASSUMPTIONS} assumptions are allowed",
                )
            )
        for index, assumption in enumerate(assumptions):
            path = ("assumptions", index)
            if isinstance(assumption, (Mapping, tuple, frozenset)):
                errors.append(_error("value.mutable", path, "nested containers are not allowed"))
            elif not isinstance(assumption, str):
                errors.append(_error("assumption.type", path, "assumption must be a string"))
            elif not assumption or assumption != assumption.strip():
                errors.append(
                    _error("assumption.malformed", path, "assumption must be non-empty and trimmed")
                )
            elif len(assumption) > MAX_ASSUMPTION_LENGTH:
                errors.append(
                    _error(
                        "assumption.too_long",
                        path,
                        f"assumption must be at most {MAX_ASSUMPTION_LENGTH} characters",
                    )
                )
            elif any(not character.isprintable() for character in assumption):
                errors.append(
                    _error("assumption.malformed", path, "assumption must not contain control characters")
                )

    return tuple(errors)


def require_valid_circuit_plan(plan: CircuitPlan) -> CircuitPlan:
    """Return plan or raise CircuitPlanValidationError with structured errors."""

    errors = validate_circuit_plan(plan)
    if errors:
        raise CircuitPlanValidationError(errors)
    return plan


__all__ = [
    "CircuitPlan",
    "CircuitPlanValidationError",
    "ValidationError",
    "require_valid_circuit_plan",
    "validate_circuit_plan",
]
