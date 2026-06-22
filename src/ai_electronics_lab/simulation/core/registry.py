from __future__ import annotations

import copy
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Any

__all__ = [
    "RegistryContract",
    "RegistryDescriptor",
    "RegistryDuplicateError",
    "RegistryError",
    "RegistryKind",
    "RegistryNotFoundError",
    "RegistryUnsupportedKindError",
    "RegistryValidationError",
]


class RegistryError(ValueError):
    """Raised when registry contract data is invalid or inconsistent."""


class RegistryValidationError(RegistryError):
    """Raised when a descriptor or registry payload fails validation."""


class RegistryDuplicateError(RegistryError):
    """Raised when a descriptor is registered more than once."""


class RegistryNotFoundError(RegistryError):
    """Raised when a descriptor lookup or removal misses."""


class RegistryUnsupportedKindError(RegistryError):
    """Raised when a descriptor kind is outside the supported registry contract."""


class RegistryKind(StrEnum):
    TOPOLOGY_BLOCK = "topology_block"
    ASSEMBLY = "assembly"
    CAPABILITY = "capability"


_SUPPORTED_KIND_ORDER: tuple[RegistryKind, ...] = (
    RegistryKind.TOPOLOGY_BLOCK,
    RegistryKind.ASSEMBLY,
    RegistryKind.CAPABILITY,
)
_SUPPORTED_KIND_VALUES: tuple[str, ...] = tuple(kind.value for kind in _SUPPORTED_KIND_ORDER)
_KIND_INDEX = {kind.value: index for index, kind in enumerate(_SUPPORTED_KIND_ORDER)}


@dataclass(frozen=True, slots=True)
class RegistryDescriptor:
    kind: str | RegistryKind
    identifier: str
    summary: str = ""
    version: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        normalized_kind = _normalize_token("descriptor kind", self.kind)
        _validate_token("descriptor identifier", self.identifier)
        if self.version:
            _validate_token("descriptor version", self.version)
        if not isinstance(self.summary, str):
            raise RegistryValidationError("descriptor summary must be a string")
        normalized_metadata = _validate_metadata("descriptor metadata", self.metadata)

        object.__setattr__(self, "kind", normalized_kind)
        object.__setattr__(self, "metadata", _freeze_mapping(normalized_metadata))

    @property
    def key(self) -> tuple[str, str]:
        return (self.kind, self.identifier)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "identifier": self.identifier,
            "summary": self.summary,
            "version": self.version,
            "metadata": _sorted_mapping(self.metadata),
        }


class RegistryContract:
    """In-memory registry contract for future topology blocks, assemblies, and capabilities."""

    def __init__(self, descriptors: Iterable[RegistryDescriptor] | None = None) -> None:
        self._descriptors: dict[tuple[str, str], RegistryDescriptor] = {}
        if descriptors is not None:
            for descriptor in descriptors:
                self.register(descriptor)

    @staticmethod
    def supported_kinds() -> tuple[str, ...]:
        return _SUPPORTED_KIND_VALUES

    def register(self, descriptor: RegistryDescriptor) -> RegistryDescriptor:
        _validate_descriptor(descriptor)
        if descriptor.kind not in self.supported_kinds():
            raise RegistryUnsupportedKindError(f"unsupported registry kind: {descriptor.kind!r}")

        key = descriptor.key
        if key in self._descriptors:
            raise RegistryDuplicateError(f"duplicate registry entry: {descriptor.kind!r}/{descriptor.identifier!r}")

        self._descriptors[key] = descriptor
        return descriptor

    def get(self, kind: str | RegistryKind, identifier: str) -> RegistryDescriptor:
        key = (_normalize_token("registry kind", kind), _validate_identifier(identifier))
        try:
            return self._descriptors[key]
        except KeyError as exc:
            raise RegistryNotFoundError(f"unknown registry entry: {key[0]!r}/{key[1]!r}") from exc

    def contains(self, kind: str | RegistryKind, identifier: str) -> bool:
        key = (_normalize_token("registry kind", kind), _validate_identifier(identifier))
        return key in self._descriptors

    def remove(self, kind: str | RegistryKind, identifier: str) -> RegistryDescriptor:
        key = (_normalize_token("registry kind", kind), _validate_identifier(identifier))
        try:
            return self._descriptors.pop(key)
        except KeyError as exc:
            raise RegistryNotFoundError(f"unknown registry entry: {key[0]!r}/{key[1]!r}") from exc

    def list(self, kind: str | RegistryKind | None = None) -> tuple[RegistryDescriptor, ...]:
        if kind is None:
            return tuple(sorted(self._descriptors.values(), key=_descriptor_sort_key))

        normalized_kind = _normalize_token("registry kind", kind)
        return tuple(
            sorted(
                (descriptor for descriptor in self._descriptors.values() if descriptor.kind == normalized_kind),
                key=_descriptor_sort_key,
            )
        )

    def clear(self) -> None:
        self._descriptors.clear()

    def validate(self) -> None:
        for descriptor in self._descriptors.values():
            _validate_descriptor(descriptor)
            if descriptor.kind not in self.supported_kinds():
                raise RegistryUnsupportedKindError(f"unsupported registry kind: {descriptor.kind!r}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "supported_kinds": list(self.supported_kinds()),
            "descriptors": [descriptor.to_dict() for descriptor in self.list()],
        }


def _descriptor_sort_key(descriptor: RegistryDescriptor) -> tuple[int, str, str]:
    return (_KIND_INDEX.get(descriptor.kind, len(_KIND_INDEX)), descriptor.kind, descriptor.identifier)


def _validate_descriptor(descriptor: Any) -> None:
    if not isinstance(descriptor, RegistryDescriptor):
        raise RegistryValidationError("descriptor must be a RegistryDescriptor")


def _validate_identifier(identifier: Any) -> str:
    return _validate_token("registry identifier", identifier)


def _normalize_token(label: str, value: Any) -> str:
    if isinstance(value, RegistryKind):
        return value.value
    return _validate_token(label, value)


def _validate_token(label: str, value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RegistryValidationError(f"{label} must be a non-empty string")
    if value != value.strip():
        raise RegistryValidationError(f"{label} must not contain leading or trailing whitespace: {value!r}")
    if any(character.isspace() for character in value):
        raise RegistryValidationError(f"{label} must not contain whitespace: {value!r}")
    return value


def _validate_metadata(label: str, value: Mapping[str, Any] | None) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise RegistryValidationError(f"{label} must be a mapping or None")

    normalized: dict[str, Any] = {}
    for key, item in value.items():
        _validate_token(f"{label} key", key)
        _validate_renderer_safe_value(f"{label}.{key}", item)
        normalized[key] = item
    return normalized


def _validate_renderer_safe_value(label: str, value: Any) -> None:
    if value is None or isinstance(value, (str, int, float, bool)):
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            _validate_token(f"{label} key", key)
            _validate_renderer_safe_value(f"{label}.{key}", item)
        return
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _validate_renderer_safe_value(f"{label}[{index}]", item)
        return
    raise RegistryValidationError(f"{label} contains an unsupported value: {value!r}")


def _freeze_mapping(value: Mapping[str, Any] | None) -> Mapping[str, Any]:
    frozen = copy.deepcopy(dict(value or {}))
    return MappingProxyType(frozen)


def _sorted_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    return {key: copy.deepcopy(value[key]) for key in sorted(value)}
