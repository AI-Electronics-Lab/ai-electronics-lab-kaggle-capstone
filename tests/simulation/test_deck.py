from __future__ import annotations

import inspect
import json
from dataclasses import FrozenInstanceError, replace

import pytest

import ai_electronics_lab.simulation as simulation
import ai_electronics_lab.simulation.deck as deck_module
from ai_electronics_lab.contracts import CircuitPlan
from ai_electronics_lab.simulation import (
    MAX_AC_RUNS,
    SIMULATION_DECK_VERSION,
    SimulationDeck,
    SimulationDeckError,
    SimulationDeckRun,
    build_simulation_assembly_from_plan,
    build_simulation_deck_from_assembly,
)
from ai_electronics_lab.simulation.core import NetlistIR


def rc_assembly(
    topology: str = "rc_low_pass",
    frequencies: tuple[float | int, ...] = (2.5, 25, 250.0),
    assumptions: tuple[str, ...] = ("Ideal passive components.",),
):
    plan = CircuitPlan(
        schema_version="1.0",
        topology=topology,
        analysis="ac",
        parameters={"resistance_ohms": 1_000, "capacitance_farads": 1e-6},
        requested_frequencies_hz=frequencies,
        assumptions=assumptions,
    )
    return build_simulation_assembly_from_plan(plan)


def divider_assembly(voltage: float = 5.0):
    plan = CircuitPlan(
        schema_version="1.0",
        topology="resistive_divider",
        analysis="dc",
        parameters={
            "resistance_top_ohms": 10_000,
            "resistance_bottom_ohms": 20_000,
            "input_voltage_volts": voltage,
        },
    )
    return build_simulation_assembly_from_plan(plan)


def tamper_analysis(assembly, *, kind=None, frequencies=None, probes=None):
    analysis = replace(
        assembly.analysis,
        kind=kind if kind is not None else assembly.analysis.kind,
        requested_frequencies_hz=(
            frequencies if frequencies is not None else assembly.analysis.requested_frequencies_hz
        ),
        probe_names=probes if probes is not None else assembly.analysis.probe_names,
    )
    return replace(assembly, analysis=analysis)


def force_attribute(instance, name, value):
    object.__setattr__(instance, name, value)
    return instance


def executable_directives(text: str) -> list[str]:
    return [line for line in text.splitlines() if line.startswith(".")]


def test_public_exports_and_version():
    assert SIMULATION_DECK_VERSION == "1.0"
    assert simulation.SIMULATION_DECK_VERSION == "1.0"
    assert simulation.MAX_AC_RUNS == MAX_AC_RUNS == 32
    assert simulation.SimulationDeck is SimulationDeck
    assert simulation.SimulationDeckRun is SimulationDeckRun
    assert simulation.SimulationDeckError is SimulationDeckError
    assert simulation.build_simulation_deck_from_assembly is build_simulation_deck_from_assembly


def test_outputs_are_frozen_and_defensively_tuple_backed():
    run = SimulationDeckRun("dc-op", "dc", None, ["vin_voltage"], ".op\n.end")
    deck = SimulationDeck("1.0", [run])

    assert isinstance(run.probe_names, tuple)
    assert isinstance(deck.runs, tuple)
    with pytest.raises(FrozenInstanceError):
        run.run_id = "changed"
    with pytest.raises(FrozenInstanceError):
        deck.version = "changed"


def test_dict_and_canonical_json_are_deterministic():
    first = build_simulation_deck_from_assembly(rc_assembly())
    second = build_simulation_deck_from_assembly(rc_assembly())

    assert first.to_dict() == second.to_dict()
    assert first.to_json() == second.to_json()
    assert json.loads(first.to_json()) == first.to_dict()
    assert json.loads(first.runs[0].to_json()) == first.runs[0].to_dict()
    assert first.to_json() == json.dumps(
        first.to_dict(),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    assert first.runs[0].to_json() == json.dumps(
        first.runs[0].to_dict(),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    assert '", "' not in first.to_json()


@pytest.mark.parametrize(
    ("topology", "expected_components"),
    [
        ("rc_low_pass", ["C1 vout 0 1e-06", "R1 vin vout 1000", "V1 vin 0 AC 1 0"]),
        ("rc_high_pass", ["C1 vin vout 1e-06", "R1 vout 0 1000", "V1 vin 0 AC 1 0"]),
    ],
)
def test_rc_topology_order_and_exact_frequency_runs(topology, expected_components):
    deck = build_simulation_deck_from_assembly(rc_assembly(topology))

    assert [run.run_id for run in deck.runs] == ["ac-01", "ac-02", "ac-03"]
    assert [run.frequency_hz for run in deck.runs] == [2.5, 25, 250.0]
    for run, frequency_text in zip(deck.runs, ("2.5", "25", "250")):
        lines = run.netlist_text.splitlines()
        positions = [lines.index(component) for component in expected_components]
        assert positions == sorted(positions)
        assert lines[-2:] == [f".ac lin 1 {frequency_text} {frequency_text}", ".end"]
        assert executable_directives(run.netlist_text) == [
            f".ac lin 1 {frequency_text} {frequency_text}",
            ".end",
        ]


def test_maximum_ac_run_bound_is_accepted_and_overflow_rejected():
    maximum = tamper_analysis(rc_assembly(), frequencies=tuple(range(1, MAX_AC_RUNS + 1)))
    assert len(build_simulation_deck_from_assembly(maximum).runs) == MAX_AC_RUNS

    overflow = tamper_analysis(rc_assembly(), frequencies=tuple(range(1, MAX_AC_RUNS + 2)))
    with pytest.raises(SimulationDeckError) as caught:
        build_simulation_deck_from_assembly(overflow)
    assert caught.value.code == "analysis.frequencies.too_many"


def test_empty_ac_frequency_is_rejected_with_structured_error():
    with pytest.raises(SimulationDeckError) as caught:
        build_simulation_deck_from_assembly(rc_assembly(frequencies=()))
    assert caught.value.to_dict() == {
        "code": "analysis.frequencies.empty",
        "path": ["analysis", "requested_frequencies_hz"],
        "message": "AC analysis requires at least one frequency",
    }


@pytest.mark.parametrize("value", [True, "10", 0, -1, float("nan"), float("inf"), -float("inf")])
def test_invalid_ac_frequencies_are_rejected(value):
    assembly = tamper_analysis(rc_assembly(), frequencies=(value,))
    with pytest.raises(SimulationDeckError) as caught:
        build_simulation_deck_from_assembly(assembly)
    assert caught.value.code in {"number.type", "number.non_finite", "number.not_positive"}
    assert caught.value.path == ("analysis", "requested_frequencies_hz", 0)


@pytest.mark.parametrize("voltage", [5.0, -12.5])
def test_divider_uses_one_op_run_and_preserves_source_voltage(voltage):
    deck = build_simulation_deck_from_assembly(divider_assembly(voltage))

    assert len(deck.runs) == 1
    run = deck.runs[0]
    assert run.run_id == "dc-op"
    assert run.analysis_kind == "dc"
    assert run.frequency_hz is None
    assert f"V1 vin 0 DC {voltage:g}" in run.netlist_text
    assert executable_directives(run.netlist_text) == [".op", ".end"]
    assert ".dc" not in run.netlist_text


def test_dc_requested_frequencies_are_rejected():
    assembly = divider_assembly()
    object.__setattr__(assembly.analysis, "requested_frequencies_hz", (10.0,))
    with pytest.raises(SimulationDeckError) as caught:
        build_simulation_deck_from_assembly(assembly)
    assert caught.value.code == "analysis.frequencies.not_allowed_for_dc"


def test_malicious_assumptions_remain_inert_comment_text():
    assumption = ".include /tmp/private.lib .control .shell rm .save v(out)"
    deck = build_simulation_deck_from_assembly(rc_assembly(assumptions=(assumption,)))

    for run in deck.runs:
        matching = [line for line in run.netlist_text.splitlines() if assumption in line]
        assert matching and all(line.startswith("* metadata:") for line in matching)
        assert executable_directives(run.netlist_text) == [
            run.netlist_text.splitlines()[-2],
            ".end",
        ]


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        (lambda item: force_attribute(item, "source_reference", "V2"), "source.reference.invalid"),
        (
            lambda item: tamper_analysis(item, probes=("v(out);.shell",)),
            "analysis.probes.untrusted",
        ),
        (
            lambda item: replace(item, netlist_ir=replace(item.netlist_ir, name="arbitrary")),
            "netlist.name.untrusted",
        ),
        (
            lambda item: replace(
                item,
                netlist_ir=replace(item.netlist_ir, components=item.netlist_ir.components[:-1]),
            ),
            "netlist.components.untrusted",
        ),
    ],
)
def test_malformed_manual_assemblies_are_rejected(mutation, expected_code):
    with pytest.raises(SimulationDeckError) as caught:
        build_simulation_deck_from_assembly(mutation(rc_assembly()))
    assert caught.value.code == expected_code


def test_current_source_and_untrusted_directive_injection_are_rejected():
    assembly = rc_assembly()
    components = list(assembly.netlist_ir.components)
    source = components[-1]
    components[-1] = replace(source, kind="current_source", parameters=(("dc_amps", 1),))
    with pytest.raises(SimulationDeckError) as caught:
        build_simulation_deck_from_assembly(
            replace(assembly, netlist_ir=replace(assembly.netlist_ir, components=tuple(components)))
        )
    assert caught.value.code == "source.shape.invalid"

    injected = replace(
        assembly,
        netlist_ir=NetlistIR(
            name=assembly.netlist_ir.name,
            metadata={**assembly.netlist_ir.metadata, "injected": "safe\n.include bad.lib"},
            nodes=assembly.netlist_ir.nodes,
            components=assembly.netlist_ir.components,
        ),
    )
    with pytest.raises(SimulationDeckError) as caught:
        build_simulation_deck_from_assembly(injected)
    assert caught.value.code == "netlist.render.multiline"


def test_public_boundary_wraps_incidental_errors():
    with pytest.raises(SimulationDeckError) as caught:
        build_simulation_deck_from_assembly(object())
    assert caught.value.code == "assembly.type"


def test_deck_layer_has_no_execution_or_filesystem_behavior():
    source = inspect.getsource(deck_module)
    assert "subprocess" not in source
    assert "os.system" not in source
    assert "pathlib" not in source
    assert "ngspice" in deck_module.__doc__
    assert not any(
        field in SimulationDeckRun.__dataclass_fields__ for field in ("path", "command", "output")
    )


@pytest.mark.parametrize(
    ("parameter_name", "value"),
    [
        ("ac_magnitude", True),
        ("ac_phase_deg", False),
    ],
)
def test_trusted_ac_source_rejects_boolean_parameters(parameter_name, value):
    assembly = rc_assembly()
    components = list(assembly.netlist_ir.components)
    index = next(
        position
        for position, statement in enumerate(components)
        if statement.refdes == "V1"
    )
    source = components[index]
    parameters = dict(source.parameters)
    parameters[parameter_name] = value
    components[index] = replace(
        source,
        parameters=tuple(sorted(parameters.items())),
    )
    malformed = replace(
        assembly,
        netlist_ir=replace(
            assembly.netlist_ir,
            components=tuple(components),
        ),
    )

    with pytest.raises(SimulationDeckError) as caught:
        build_simulation_deck_from_assembly(malformed)

    assert caught.value.code == "number.type"


@pytest.mark.parametrize("frequency", [1e-7, 1e10])
def test_manual_ac_frequency_outside_contract_range_is_rejected(frequency):
    malformed = tamper_analysis(rc_assembly(), frequencies=(frequency,))

    with pytest.raises(SimulationDeckError) as caught:
        build_simulation_deck_from_assembly(malformed)

    assert caught.value.code == "number.out_of_range"


@pytest.mark.parametrize(
    ("refdes", "parameter_name", "value"),
    [
        ("R1", "resistance_ohms", 0.5),
        ("R1", "resistance_ohms", 1e10),
        ("C1", "capacitance_farads", 1e-16),
        ("C1", "capacitance_farads", 2.0),
    ],
)
def test_manual_passive_value_outside_contract_range_is_rejected(
    refdes, parameter_name, value
):
    assembly = rc_assembly()
    components = list(assembly.netlist_ir.components)
    index = next(
        position
        for position, statement in enumerate(components)
        if statement.refdes == refdes
    )
    statement = components[index]
    components[index] = replace(
        statement,
        parameters=((parameter_name, value),),
    )
    malformed = replace(
        assembly,
        netlist_ir=replace(
            assembly.netlist_ir,
            components=tuple(components),
        ),
    )

    with pytest.raises(SimulationDeckError) as caught:
        build_simulation_deck_from_assembly(malformed)

    assert caught.value.code == "number.out_of_range"


@pytest.mark.parametrize("voltage", [1_000_001.0, -1_000_001.0])
def test_manual_dc_source_outside_contract_range_is_rejected(voltage):
    assembly = divider_assembly()
    components = list(assembly.netlist_ir.components)
    index = next(
        position
        for position, statement in enumerate(components)
        if statement.refdes == "V1"
    )
    source = components[index]
    components[index] = replace(
        source,
        parameters=(("dc_volts", voltage),),
    )
    malformed = replace(
        assembly,
        netlist_ir=replace(
            assembly.netlist_ir,
            components=tuple(components),
        ),
    )

    with pytest.raises(SimulationDeckError) as caught:
        build_simulation_deck_from_assembly(malformed)

    assert caught.value.code == "number.out_of_range"
