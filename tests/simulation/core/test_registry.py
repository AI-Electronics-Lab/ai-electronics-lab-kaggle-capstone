from __future__ import annotations

import pytest

from src.ai_electronics_lab.simulation.core import (
    RegistryContract,
    RegistryDescriptor,
    RegistryDuplicateError,
    RegistryKind,
    RegistryNotFoundError,
    RegistryUnsupportedKindError,
    RegistryValidationError,
)


def test_supported_kinds_are_explicit_and_follow_the_layer_order():
    assert RegistryContract.supported_kinds() == (
        "topology_block",
        "assembly",
        "capability",
    )


def test_registry_registers_lists_gets_and_removes_descriptors_deterministically():
    registry = RegistryContract()
    topology_block = RegistryDescriptor(
        kind=RegistryKind.TOPOLOGY_BLOCK,
        identifier="rc_low_pass",
        summary="Reusable RC low-pass block",
        version="v1",
        metadata={"ports": ["vin", "vout"]},
    )
    capability = RegistryDescriptor(
        kind="capability",
        identifier="rc_low_pass_lab",
        summary="User-facing RC lab capability",
        metadata={"stage": "m8.7"},
    )

    registry.register(capability)
    registry.register(topology_block)

    assert registry.contains("capability", "rc_low_pass_lab") is True
    assert registry.get("capability", "rc_low_pass_lab") == capability
    assert [descriptor.kind for descriptor in registry.list()] == ["topology_block", "capability"]
    assert [descriptor.identifier for descriptor in registry.list("topology_block")] == ["rc_low_pass"]
    assert registry.to_dict() == {
        "supported_kinds": ["topology_block", "assembly", "capability"],
        "descriptors": [
            {
                "kind": "topology_block",
                "identifier": "rc_low_pass",
                "summary": "Reusable RC low-pass block",
                "version": "v1",
                "metadata": {"ports": ["vin", "vout"]},
            },
            {
                "kind": "capability",
                "identifier": "rc_low_pass_lab",
                "summary": "User-facing RC lab capability",
                "version": "",
                "metadata": {"stage": "m8.7"},
            },
        ],
    }

    removed = registry.remove("capability", "rc_low_pass_lab")
    assert removed == capability
    assert registry.contains("capability", "rc_low_pass_lab") is False

    with pytest.raises(RegistryNotFoundError, match="unknown registry entry"):
        registry.get("capability", "rc_low_pass_lab")


def test_duplicate_registration_is_rejected_explicitly():
    registry = RegistryContract()
    descriptor = RegistryDescriptor(kind="assembly", identifier="two_stage_amp")
    registry.register(descriptor)

    with pytest.raises(RegistryDuplicateError, match="duplicate registry entry"):
        registry.register(RegistryDescriptor(kind=RegistryKind.ASSEMBLY, identifier="two_stage_amp"))


def test_unsupported_kind_is_rejected_by_the_registry_contract():
    registry = RegistryContract()
    descriptor = RegistryDescriptor(kind="topology_block_v2", identifier="future_block")

    with pytest.raises(RegistryUnsupportedKindError, match="unsupported registry kind"):
        registry.register(descriptor)


@pytest.mark.parametrize(
    "descriptor_kwargs, error_match",
    [
        ({"kind": "", "identifier": "rc_low_pass"}, "descriptor kind"),
        ({"kind": "capability", "identifier": ""}, "descriptor identifier"),
        ({"kind": "capability", "identifier": "rc low pass"}, "descriptor identifier"),
        ({"kind": "capability", "identifier": "rc_low_pass", "version": "bad version"}, "descriptor version"),
        ({"kind": "capability", "identifier": "rc_low_pass", "metadata": {"bad key": True}}, "descriptor metadata key"),
        ({"kind": "capability", "identifier": "rc_low_pass", "metadata": {"payload": object()}}, "unsupported value"),
    ],
)
def test_descriptor_validation_rejects_invalid_fields(descriptor_kwargs: dict[str, object], error_match: str):
    with pytest.raises(RegistryValidationError, match=error_match):
        RegistryDescriptor(**descriptor_kwargs)


def test_validate_catches_mutated_registry_state():
    registry = RegistryContract([RegistryDescriptor(kind="capability", identifier="rc_low_pass_lab")])
    registry._descriptors[("capability", "rc_low_pass_lab")] = RegistryDescriptor(  # noqa: SLF001
        kind="future_kind",
        identifier="rc_low_pass_lab",
    )

    with pytest.raises(RegistryUnsupportedKindError, match="unsupported registry kind"):
        registry.validate()
