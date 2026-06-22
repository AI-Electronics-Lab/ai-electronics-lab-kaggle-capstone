from __future__ import annotations

import json

from ai_electronics_lab.simulation.blocks.filters import build_rc_low_pass


def test_rc_low_pass_contract_serializes_source_of_truth_metadata():
    graph = build_rc_low_pass(
        resistance_ohms=1_000,
        capacitance_farads=1e-6,
        vin="vin",
        vout="vout",
    )

    payload = graph.to_dict()
    assert payload["metadata"]["block"] == "rc_low_pass"
    assert payload["metadata"]["capability_id"] == "rc_low_pass"
    assert payload["metadata"]["archetype_id"] == "rc_low_pass_vertical_slice"
    assert json.loads(graph.to_json())["ports"][1]["name"] == "VIN"
