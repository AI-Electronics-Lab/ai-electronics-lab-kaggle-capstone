"""Deterministic CircuitPlan-to-CircuitGraph adapter."""

from __future__ import annotations

from typing import Any

from ai_electronics_lab.contracts import CircuitPlan, require_valid_circuit_plan

from .blocks.filters import build_rc_high_pass, build_rc_low_pass
from .blocks.networks import build_resistive_divider
from .core import CircuitGraph

CIRCUIT_PLAN_ADAPTER_VERSION = "1.0"


def build_circuit_graph_from_plan(plan: CircuitPlan) -> CircuitGraph:
    """Validate a plan, then dispatch to one fixed trusted topology builder."""

    validated_plan = require_valid_circuit_plan(plan)
    canonical_plan = validated_plan.to_dict()
    parameters = canonical_plan["parameters"]
    metadata: dict[str, Any] = {
        "circuit_plan_adapter_version": CIRCUIT_PLAN_ADAPTER_VERSION,
        "validated_circuit_plan": canonical_plan,
    }

    if validated_plan.topology == "rc_low_pass":
        return build_rc_low_pass(
            resistance_ohms=parameters["resistance_ohms"],
            capacitance_farads=parameters["capacitance_farads"],
            vin="vin",
            vout="vout",
            gnd="0",
            metadata=metadata,
        )
    if validated_plan.topology == "rc_high_pass":
        return build_rc_high_pass(
            resistance_ohms=parameters["resistance_ohms"],
            capacitance_farads=parameters["capacitance_farads"],
            vin="vin",
            vout="vout",
            gnd="0",
            metadata=metadata,
        )
    if validated_plan.topology == "resistive_divider":
        return build_resistive_divider(
            resistance_top_ohms=parameters["resistance_top_ohms"],
            resistance_bottom_ohms=parameters["resistance_bottom_ohms"],
            vin="vin",
            vout="vout",
            gnd="0",
            metadata=metadata,
        )

    raise AssertionError("validated CircuitPlan topology has no trusted builder")


__all__ = ["CIRCUIT_PLAN_ADAPTER_VERSION", "build_circuit_graph_from_plan"]
