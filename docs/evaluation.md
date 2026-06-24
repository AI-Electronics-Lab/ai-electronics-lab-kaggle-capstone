# Deterministic evaluation report

## Evaluation record

- Evaluation date: `2026-06-24T17:00:45Z`
- Evaluated implementation commit: `3a6a8201fc2e18b92ec43f3407f852e8d85c8197`
- Dependency runner: `uv 0.11.21 (x86_64-unknown-linux-gnu)`
- Collection command: `uv run pytest --collect-only -q`
- Verification command: `bash scripts/verify.sh`
- Result: `634` tests passed
- Pytest warnings: `5`
- Ruff: PASS
- Package import smoke: PASS

The evaluated implementation is the canonical merged `main` commit named above. This report branch
changes documentation only.

The automated suite uses deterministic fixtures and bounded fakes where appropriate. It does not
require an OpenRouter API key or a live external model request.

## Test distribution

| Area | Collected tests |
| --- | ---: |
| `tests/adk` | 6 |
| `tests/contracts` | 25 |
| `tests/orchestration` | 18 |
| `tests/planning` | 135 |
| `tests/simulation` | 365 |
| `tests/skills` | 8 |
| `tests/verification` | 31 |
| `tests/web` | 46 |
| **Total** | **634** |

The largest areas are simulation boundaries, planning and provider handling, web safety, and
deterministic verification. The suite also includes the guidance-only Agent Skill and optional
Google ADK adapter.

## Representative evaluation cases

| Evaluation objective | Reproducible test reference | Result |
| --- | --- | --- |
| Supported RC low-pass contract | `tests/contracts/test_circuit_plan.py::test_valid_rc_plans[rc_low_pass]` | PASS in complete suite |
| Supported RC high-pass contract | `tests/contracts/test_circuit_plan.py::test_valid_rc_plans[rc_high_pass]` | PASS in complete suite |
| Supported resistive-divider contract | `tests/contracts/test_circuit_plan.py::test_valid_resistive_divider_plan` | PASS in complete suite |
| Unsupported topology and mismatched analysis rejection | `tests/contracts/test_circuit_plan.py::test_unsupported_topology_and_mismatched_analysis_have_stable_codes` | PASS in complete suite |
| Unsupported model request is not repaired | `tests/planning/test_openrouter.py::test_unsupported_topology_is_not_repairable` | PASS in complete suite |
| Provider transport and response failures remain bounded | `tests/planning/test_openrouter.py::test_provider_transport_and_json_failures_do_not_repair` | PASS in complete suite |
| Planner failures map to stable orchestration errors | `tests/orchestration/test_planner_mapping_regression.py::test_planner_failures_map_to_stable_orchestration_errors` | PASS in complete suite |
| Deterministic PASS, WARN, and FAIL policy | `tests/verification/test_evidence.py::test_pass_warn_fail_policy` | PASS in complete suite |
| Exact tolerance-boundary classification | `tests/verification/test_evidence.py::test_tolerance_boundaries_are_inclusive_and_unrounded` | PASS in complete suite |
| Near-zero denominator produces deterministic failure | `tests/verification/test_evidence.py::test_near_zero_measured_vin_produces_denominator_failure` | PASS in complete suite |
| ADK failure does not disclose exception text | `tests/adk/test_workflow.py::test_unexpected_service_failure_does_not_expose_exception_text` | PASS in complete suite |

Additional boundary coverage is concentrated in:

- `tests/simulation/test_runner.py`: 45 tests;
- `tests/simulation/test_raw_parser.py`: 92 tests;
- `tests/web/test_app.py`: 46 tests;
- `tests/skills/test_verified_circuit_simulation_skill.py`:
  8 tests.

## Name-based discoverability inventory

The following counts are generated from collected pytest node names. They overlap and are provided
only as a navigation aid; they are not code-coverage percentages or independent benchmark scores.

| Search dimension | Matching collected node IDs |
| --- | ---: |
| supported low-pass | 39 |
| supported high-pass | 42 |
| supported divider | 58 |
| unsupported input | 20 |
| malformed or invalid input | 221 |
| provider or repair failure | 54 |
| verification or verdict | 175 |
| safe error or disclosure | 48 |

## Deterministic verdict evaluation

The verifier tests explicitly exercise:

- exact analytical RC low-pass and RC high-pass values;
- exact positive and negative resistive-divider values;
- PASS results within the fixed tolerance;
- WARN results between the pass and warning limits;
- FAIL results beyond the warning limit;
- inclusive and unrounded tolerance boundaries;
- denominator-floor behavior;
- malformed and incoherent plan/result rejection;
- hostile input objects rejected before their hooks execute.

The model does not select the tolerances or verdict. The fixed deterministic verifier remains the
authority for PASS, WARN, and FAIL.

## Evaluation limitations

This report does not claim:

- line, branch, mutation, or formal proof coverage;
- model-quality, latency, throughput, or cost benchmarking;
- live OpenRouter availability;
- public-hosting or multi-user security;
- support for circuits outside the three frozen topologies;
- that name-based inventory counts are mutually exclusive;
- that passing tests eliminate all implementation defects.

The reported warnings are deprecation warnings from installed framework or dependency code and did
not fail the suite.

## Reproduction

From a clean checkout of the named commit:

    uv sync --extra dev --extra adk --frozen
    uv run ruff check .
    uv run pytest -q
    uv run python -c "import ai_electronics_lab; print('package_import=ok')"
    uv run pytest --collect-only -q

Representative verdict-policy cases can be run with:

    uv run pytest -q \
      tests/verification/test_evidence.py::test_pass_warn_fail_policy \
      tests/verification/test_evidence.py::test_tolerance_boundaries_are_inclusive_and_unrounded

## Conclusion

At the named commit, the complete deterministic suite passed. The evidence covers the supported
topologies, malformed and unsupported requests, provider and repair failures, trusted simulation
construction, bounded ngspice execution, raw parsing, deterministic verdicts, safe errors, the local
web boundary, the Agent Skill, and the ADK adapter.

This is reproducible engineering evidence for the frozen capstone scope, not a claim of unrestricted
general-purpose circuit design or formal security certification.
