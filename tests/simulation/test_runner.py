from __future__ import annotations

import inspect
import json
import os
import signal
import sys
import time
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest

import ai_electronics_lab.simulation as simulation
import ai_electronics_lab.simulation.runner as runner_module
from ai_electronics_lab.contracts import CircuitPlan
from ai_electronics_lab.simulation import (
    SIMULATION_RUNNER_VERSION,
    SimulationDeck,
    SimulationExecutionEvidence,
    SimulationRunEvidence,
    SimulationRunnerError,
    build_simulation_assembly_from_plan,
    build_simulation_deck_from_assembly,
    run_simulation_deck,
)


def deck_for(topology="rc_low_pass", frequencies=(10.0, 100.0)):
    plan = CircuitPlan(
        schema_version="1.0",
        topology=topology,
        analysis="ac",
        parameters={"resistance_ohms": 1_000, "capacitance_farads": 1e-6},
        requested_frequencies_hz=frequencies,
    )
    return build_simulation_deck_from_assembly(build_simulation_assembly_from_plan(plan))


def dc_deck():
    plan = CircuitPlan(
        schema_version="1.0",
        topology="resistive_divider",
        analysis="dc",
        parameters={
            "resistance_top_ohms": 10_000,
            "resistance_bottom_ohms": 20_000,
            "input_voltage_volts": 5.0,
        },
    )
    return build_simulation_deck_from_assembly(build_simulation_assembly_from_plan(plan))


def make_fake(tmp_path: Path, body: str) -> Path:
    fake = tmp_path / "ngspice"
    fake.write_text(f"#!{sys.executable}\n" + body)
    fake.chmod(0o755)
    return fake


def install_fake(monkeypatch, fake: Path) -> None:
    monkeypatch.setattr(runner_module, "_NGSPICE_CANDIDATES", (str(fake),))


def success_fake(tmp_path: Path, *, raw_prefix: bytes = b"raw:") -> Path:
    observed = tmp_path / "observed.json"
    return make_fake(
        tmp_path,
        f'''
import json, os, pathlib, sys
cwd = pathlib.Path.cwd()
input_bytes = pathlib.Path("input.cir").read_bytes()
pathlib.Path({str(observed)!r}).write_text(json.dumps({{
    "argv": sys.argv,
    "cwd": str(cwd),
    "env": dict(os.environ),
    "input_hex": input_bytes.hex(),
}}))
pathlib.Path("output.raw").write_bytes({raw_prefix!r} + input_bytes)
print("stdout text")
print("stderr text", file=sys.stderr)
''',
    )


def read_observed(tmp_path: Path) -> dict:
    return json.loads((tmp_path / "observed.json").read_text())


def tamper_run(deck: SimulationDeck, **changes) -> SimulationDeck:
    runs = list(deck.runs)
    runs[0] = replace(runs[0], **changes)
    return SimulationDeck(deck.version, tuple(runs))


def tamper_text(deck: SimulationDeck, replacement) -> SimulationDeck:
    text = deck.runs[0].netlist_text
    return tamper_run(deck, netlist_text=replacement(text))


def corrupt_run_field(deck: SimulationDeck, field: str, value) -> SimulationDeck:
    runs = list(deck.runs)
    corrupted = replace(runs[0])
    object.__setattr__(corrupted, field, value)
    runs[0] = corrupted
    return SimulationDeck(deck.version, tuple(runs))


def process_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def wait_until_process_exits(pid: int, *, timeout: float = 2.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not process_exists(pid):
            return True
        time.sleep(0.02)
    return not process_exists(pid)


def cleanup_pid_file(pid_file: Path) -> None:
    if not pid_file.exists():
        return
    try:
        pid = int(pid_file.read_text())
    except ValueError:
        return
    if process_exists(pid):
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        wait_until_process_exits(pid)


def descendant_fake(tmp_path: Path, *, exit_code: int) -> tuple[Path, Path, Path]:
    marker = tmp_path / f"descendant-term-{exit_code}.txt"
    pid_file = tmp_path / f"descendant-pid-{exit_code}.txt"
    fake = make_fake(
        tmp_path,
        f"""
import os, pathlib, signal, sys, time
marker = pathlib.Path({str(marker)!r})
pid_file = pathlib.Path({str(pid_file)!r})
pid = os.fork()
if pid == 0:
    sys.stdout.close()
    sys.stderr.close()
    def handle_term(signum, frame):
        marker.write_text(f"terminated:{{os.getpid()}}")
        raise SystemExit(0)
    signal.signal(signal.SIGTERM, handle_term)
    pid_file.write_text(str(os.getpid()))
    while True:
        time.sleep(0.05)
for _ in range(100):
    if pid_file.exists():
        break
    time.sleep(0.01)
pathlib.Path("output.raw").write_bytes(b"raw")
sys.exit({exit_code})
""",
    )
    return fake, marker, pid_file


def test_public_exports_and_version():
    assert SIMULATION_RUNNER_VERSION == "1.0"
    assert simulation.SIMULATION_RUNNER_VERSION == "1.0"
    assert simulation.SimulationRunnerError is SimulationRunnerError
    assert simulation.SimulationRunEvidence is SimulationRunEvidence
    assert simulation.SimulationExecutionEvidence is SimulationExecutionEvidence
    assert simulation.run_simulation_deck is run_simulation_deck


def test_evidence_is_frozen_tuple_backed_and_canonical_json():
    run = SimulationRunEvidence("r", "ac", 10.0, ["a"], 0, "out", "err", b"\x00raw")
    evidence = SimulationExecutionEvidence("1.0", [run])

    assert run.probe_names == ("a",)
    assert evidence.runs == (run,)
    assert run.to_dict()["raw_output_base64"] == "AHJhdw=="
    assert json.loads(run.to_json()) == run.to_dict()
    assert evidence.to_json() == json.dumps(
        evidence.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )
    with pytest.raises(FrozenInstanceError):
        run.stdout = "changed"
    with pytest.raises(FrozenInstanceError):
        evidence.version = "changed"


def test_successful_ac_execution_preserves_order_and_captures_evidence(tmp_path, monkeypatch):
    fake = success_fake(tmp_path)
    install_fake(monkeypatch, fake)
    deck = deck_for(frequencies=(10.0, 100.0))

    evidence = run_simulation_deck(deck)

    assert [run.run_id for run in evidence.runs] == ["ac-01", "ac-02"]
    assert [run.frequency_hz for run in evidence.runs] == [10.0, 100.0]
    assert all(run.stdout == "stdout text\n" for run in evidence.runs)
    assert all(run.stderr == "stderr text\n" for run in evidence.runs)
    assert evidence.runs[0].raw_output == b"raw:" + deck.runs[0].netlist_text.encode()


def test_successful_dc_execution(tmp_path, monkeypatch):
    fake = success_fake(tmp_path, raw_prefix=b"dcraw:")
    install_fake(monkeypatch, fake)

    evidence = run_simulation_deck(dc_deck())

    assert len(evidence.runs) == 1
    assert evidence.runs[0].run_id == "dc-op"
    assert evidence.runs[0].analysis_kind == "dc"
    assert evidence.runs[0].frequency_hz is None
    assert evidence.runs[0].raw_output.startswith(b"dcraw:")


def test_fixed_argv_startup_suppression_private_cwd_minimal_env_and_input_bytes(tmp_path, monkeypatch):
    fake = success_fake(tmp_path)
    install_fake(monkeypatch, fake)
    monkeypatch.setenv("AEL_SENTINEL_SECRET", "must-not-leak")
    monkeypatch.setenv("PATH", "/untrusted")
    deck = deck_for(frequencies=(25.0,))

    evidence = run_simulation_deck(deck)
    observed = read_observed(tmp_path)

    assert observed["argv"] == [str(fake), "-n", "-b", "-r", "output.raw", "input.cir"]
    assert Path(observed["cwd"]).name.startswith("ai-electronics-lab-ngspice-")
    assert not Path(observed["cwd"]).exists()
    assert observed["env"] == {
        "HOME": observed["cwd"],
        "TMPDIR": observed["cwd"],
        "LANG": "C",
        "LC_ALL": "C",
    }
    assert bytes.fromhex(observed["input_hex"]) == deck.runs[0].netlist_text.encode("utf-8")
    assert evidence.runs[0].raw_output.endswith(deck.runs[0].netlist_text.encode("utf-8"))


def test_missing_and_invalid_executable(tmp_path, monkeypatch):
    monkeypatch.setattr(runner_module, "_NGSPICE_CANDIDATES", (str(tmp_path / "missing"),))
    with pytest.raises(SimulationRunnerError) as caught:
        run_simulation_deck(deck_for(frequencies=(10.0,)))
    assert caught.value.code == "runner.executable.missing"

    invalid = tmp_path / "ngspice"
    invalid.write_text("not executable")
    invalid.chmod(0o644)
    monkeypatch.setattr(runner_module, "_NGSPICE_CANDIDATES", (str(invalid),))
    with pytest.raises(SimulationRunnerError) as caught:
        run_simulation_deck(deck_for(frequencies=(10.0,)))
    assert caught.value.code == "runner.executable.invalid"


def test_process_start_failure(monkeypatch, tmp_path):
    fake = tmp_path / "ngspice"
    fake.write_text("fake")
    fake.chmod(0o755)
    monkeypatch.setattr(runner_module, "_NGSPICE_CANDIDATES", (str(fake),))

    def fail_start(*args, **kwargs):
        raise OSError("boom")

    monkeypatch.setattr(runner_module, "_POPEN", fail_start)
    with pytest.raises(SimulationRunnerError) as caught:
        run_simulation_deck(deck_for(frequencies=(10.0,)))
    assert caught.value.code == "runner.subprocess.start_failed"
    assert "boom" not in caught.value.message


def test_nonzero_exit_missing_raw_and_cleanup_after_failure(tmp_path, monkeypatch):
    cwd_file = tmp_path / "cwd.txt"
    fake = make_fake(
        tmp_path,
        f'''
import pathlib, sys
pathlib.Path({str(cwd_file)!r}).write_text(str(pathlib.Path.cwd()))
pathlib.Path("output.raw").write_bytes(b"raw")
sys.exit(7)
''',
    )
    install_fake(monkeypatch, fake)
    with pytest.raises(SimulationRunnerError) as caught:
        run_simulation_deck(deck_for(frequencies=(10.0,)))
    assert caught.value.code == "runner.exit.nonzero"
    assert not Path(cwd_file.read_text()).exists()

    fake = make_fake(tmp_path, "import sys\nsys.exit(0)\n")
    install_fake(monkeypatch, fake)
    with pytest.raises(SimulationRunnerError) as caught:
        run_simulation_deck(deck_for(frequencies=(10.0,)))
    assert caught.value.code == "runner.raw_output.missing"


@pytest.mark.parametrize("exit_code", [0, 7])
def test_descendant_process_group_is_terminated_after_leader_exit(tmp_path, monkeypatch, exit_code):
    fake, marker, pid_file = descendant_fake(tmp_path, exit_code=exit_code)
    install_fake(monkeypatch, fake)

    try:
        if exit_code == 0:
            evidence = run_simulation_deck(deck_for(frequencies=(10.0,)))
            assert evidence.runs[0].raw_output == b"raw"
        else:
            with pytest.raises(SimulationRunnerError) as caught:
                run_simulation_deck(deck_for(frequencies=(10.0,)))
            assert caught.value.code == "runner.exit.nonzero"

        assert marker.exists()
        descendant_pid = int(pid_file.read_text())
        assert wait_until_process_exits(descendant_pid)
    finally:
        cleanup_pid_file(pid_file)


def test_per_run_timeout_and_total_timeout(tmp_path, monkeypatch):
    fake = make_fake(tmp_path, "import time\ntime.sleep(1)\n")
    install_fake(monkeypatch, fake)
    monkeypatch.setattr(runner_module, "_PER_RUN_TIMEOUT_SECONDS", 0.05)
    monkeypatch.setattr(runner_module, "_TOTAL_TIMEOUT_SECONDS", 1.0)
    with pytest.raises(SimulationRunnerError) as caught:
        run_simulation_deck(deck_for(frequencies=(10.0,)))
    assert caught.value.code == "runner.timeout.per_run"

    monkeypatch.setattr(runner_module, "_PER_RUN_TIMEOUT_SECONDS", 1.0)
    monkeypatch.setattr(runner_module, "_TOTAL_TIMEOUT_SECONDS", 0.05)
    with pytest.raises(SimulationRunnerError) as caught:
        run_simulation_deck(deck_for(frequencies=(10.0,)))
    assert caught.value.code == "runner.timeout.total"


@pytest.mark.parametrize(
    ("stream", "code"),
    [("stdout", "runner.stdout.overflow"), ("stderr", "runner.stderr.overflow")],
)
def test_stdout_and_stderr_overflow(tmp_path, monkeypatch, stream, code):
    target = "sys.stdout" if stream == "stdout" else "sys.stderr"
    fake = make_fake(
        tmp_path,
        f'''
import sys, pathlib, time
pathlib.Path("output.raw").write_bytes(b"raw")
{target}.buffer.write(b"x" * 32)
{target}.flush()
time.sleep(0.2)
''',
    )
    install_fake(monkeypatch, fake)
    monkeypatch.setattr(runner_module, "_MAX_STDOUT_BYTES", 8)
    monkeypatch.setattr(runner_module, "_MAX_STDERR_BYTES", 8)
    with pytest.raises(SimulationRunnerError) as caught:
        run_simulation_deck(deck_for(frequencies=(10.0,)))
    assert caught.value.code == code


def test_raw_output_overflow(tmp_path, monkeypatch):
    fake = make_fake(
        tmp_path,
        '''
import pathlib, time
pathlib.Path("output.raw").write_bytes(b"x" * 64)
time.sleep(0.2)
''',
    )
    install_fake(monkeypatch, fake)
    monkeypatch.setattr(runner_module, "_MAX_RAW_OUTPUT_BYTES", 8)
    with pytest.raises(SimulationRunnerError) as caught:
        run_simulation_deck(deck_for(frequencies=(10.0,)))
    assert caught.value.code == "runner.raw_output.overflow"


def test_validation_rejects_before_executable_resolution(monkeypatch):
    deck = tamper_run(deck_for(frequencies=(10.0,)), run_id="evil")

    def unexpected_resolution():
        pytest.fail("executable resolution happened before validation")

    monkeypatch.setattr(runner_module, "_resolve_executable", unexpected_resolution)
    with pytest.raises(SimulationRunnerError) as caught:
        run_simulation_deck(deck)
    assert caught.value.code == "runner.deck.malformed"
    assert caught.value.path == ("runs", 0, "run_id")


@pytest.mark.parametrize(
    ("field", "value", "path"),
    [
        ("analysis_kind", [], ("runs", 0, "analysis_kind")),
        ("run_id", object(), ("runs", 0, "run_id")),
        (
            "probe_names",
            ["transfer_function", "vin_voltage", "vout_voltage"],
            ("runs", 0, "probe_names"),
        ),
        ("frequency_hz", object(), ("runs", 0, "frequency_hz")),
        ("netlist_text", object(), ("runs", 0, "netlist_text")),
    ],
)
def test_corrupted_run_fields_are_normalized_before_executable_resolution(
    monkeypatch, field, value, path
):
    deck = corrupt_run_field(deck_for(frequencies=(10.0,)), field, value)

    def unexpected_resolution():
        pytest.fail("executable resolution happened before validation")

    monkeypatch.setattr(runner_module, "_resolve_executable", unexpected_resolution)
    with pytest.raises(SimulationRunnerError) as caught:
        run_simulation_deck(deck)
    assert caught.value.code == "runner.deck.malformed"
    assert caught.value.path == path


def test_corrupted_deck_container_is_normalized_before_executable_resolution(monkeypatch):
    deck = SimulationDeck("1.0", deck_for(frequencies=(10.0,)).runs)
    object.__setattr__(deck, "runs", list(deck.runs))

    def unexpected_resolution():
        pytest.fail("executable resolution happened before validation")

    monkeypatch.setattr(runner_module, "_resolve_executable", unexpected_resolution)
    with pytest.raises(SimulationRunnerError) as caught:
        run_simulation_deck(deck)
    assert caught.value.code == "runner.deck.malformed"
    assert caught.value.path == ("runs",)


@pytest.mark.parametrize("alias", ["1_000", "+1000", "01000", "1e3"])
def test_noncanonical_numeric_aliases_are_rejected(alias):
    deck = tamper_text(
        deck_for(frequencies=(10.0,)),
        lambda s: s.replace("R1 vin vout 1000", f"R1 vin vout {alias}"),
    )
    with pytest.raises(SimulationRunnerError) as caught:
        run_simulation_deck(deck)
    assert caught.value.code == "runner.deck.malformed"


def test_selector_oserror_is_normalized_and_process_is_terminated(tmp_path, monkeypatch):
    pid_file = tmp_path / "selector-pid.txt"
    fake = make_fake(
        tmp_path,
        f"""
import pathlib, time, os
pathlib.Path({str(pid_file)!r}).write_text(str(os.getpid()))
time.sleep(10)
""",
    )
    install_fake(monkeypatch, fake)
    original_selector = runner_module.selectors.DefaultSelector

    class FailingSelector:
        def __init__(self):
            self._inner = original_selector()

        def register(self, *args, **kwargs):
            return self._inner.register(*args, **kwargs)

        def unregister(self, *args, **kwargs):
            return self._inner.unregister(*args, **kwargs)

        def get_map(self):
            return self._inner.get_map()

        def select(self, timeout=None):
            raise OSError("selector failed")

        def close(self):
            return self._inner.close()

    monkeypatch.setattr(runner_module.selectors, "DefaultSelector", FailingSelector)
    try:
        with pytest.raises(SimulationRunnerError) as caught:
            run_simulation_deck(deck_for(frequencies=(10.0,)))
        assert caught.value.code == "runner.io.failed"
        if pid_file.exists():
            assert wait_until_process_exits(int(pid_file.read_text()))
        assert "selector failed" not in caught.value.message
    finally:
        cleanup_pid_file(pid_file)


@pytest.mark.parametrize(
    "mutated",
    [
        lambda d: SimulationDeck("9.9", d.runs),
        lambda d: tamper_run(d, run_id="ac-99"),
        lambda d: tamper_run(d, probe_names=("v(out)",)),
        lambda d: tamper_run(d, frequency_hz=True),
        lambda d: tamper_run(d, frequency_hz=float("nan")),
        lambda d: tamper_text(d, lambda s: s.replace(".ac lin 1 10 10", ".include private.lib")),
        lambda d: tamper_text(d, lambda s: s.replace("vin vout", "vin shellnode", 1)),
        lambda d: tamper_text(d, lambda s: s.replace("R1 vin vout 1000", "L1 vin vout 1000")),
        lambda d: tamper_text(d, lambda s: s.replace("V1 vin 0 AC 1 0", "V1 vin 0 AC 1 nan")),
        lambda d: tamper_text(d, lambda s: s.replace("R1 vin vout 1000", "R1 vin vout true")),
        lambda d: tamper_text(d, lambda s: s + "\n"),
        lambda d: tamper_text(d, lambda s: s.replace("\nR1", "\n\nR1")),
        lambda d: tamper_text(d, lambda s: s.replace("* rc_low_pass", "* rc_low_pass\r")),
        lambda d: tamper_text(d, lambda s: s.replace("R1", "R1\x00", 1)),
        lambda d: tamper_text(d, lambda s: s.replace("* metadata:", "metadata:", 1)),
        lambda d: tamper_text(d, lambda s: s.replace(".end", ".save all\n.end")),
    ],
)
def test_malformed_manual_decks_and_injection_attempts_are_rejected(mutated):
    with pytest.raises(SimulationRunnerError) as caught:
        run_simulation_deck(mutated(deck_for(frequencies=(10.0,))))
    assert caught.value.code in {"runner.deck.malformed", "runner.version.unsupported"}


def test_dc_shape_and_topology_mismatch_rejections():
    malformed = tamper_run(dc_deck(), run_id="dc-01")
    with pytest.raises(SimulationRunnerError) as caught:
        run_simulation_deck(malformed)
    assert caught.value.path == ("runs", 0, "run_id")

    malformed = tamper_text(dc_deck(), lambda s: s.replace("* resistive_divider", "* rc_low_pass"))
    with pytest.raises(SimulationRunnerError) as caught:
        run_simulation_deck(malformed)
    assert caught.value.code == "runner.deck.malformed"


def test_public_signature_has_no_caller_controlled_execution_parameters():
    signature = inspect.signature(run_simulation_deck)
    assert list(signature.parameters) == ["deck"]
    source = inspect.getsource(runner_module)
    assert "shell=False" in source
    assert "os.environ" not in source


@pytest.mark.skipif(not Path("/usr/bin/ngspice").is_file(), reason="trusted ngspice unavailable")
def test_optional_real_ngspice_smoke():
    evidence = run_simulation_deck(deck_for(frequencies=(10.0,)))
    assert evidence.runs[0].returncode == 0
    assert evidence.runs[0].raw_output
