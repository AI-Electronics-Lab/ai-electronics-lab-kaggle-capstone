# Deterministic simulation evidence verifier

## Purpose

Version 1.0 adds a deterministic verification boundary after bounded ngspice raw parsing and
before any future natural-language explanation:

    validated CircuitPlan
    + immutable SimulationParsedResults
    -> deterministic analytical calculations
    -> bounded comparison metrics
    -> immutable PASS, WARN, or FAIL verification evidence

The verifier answers one narrow question: do the parsed ngspice voltage measurements agree with
the analytical behavior implied by the validated circuit plan within a fixed, documented
numerical tolerance policy?

The verifier does not execute ngspice, parse raw bytes, construct a circuit, render a netlist,
invoke an LLM, generate prose explanations, persist data, accept user-defined tolerances, or
modify either input object.

## Supported scope

Version 1.0 supports exactly:

- RC low-pass AC analysis;
- RC high-pass AC analysis;
- resistive-divider DC operating-point analysis.

No other topology or analysis kind is accepted.

## Public API

The implementation must expose these names from
`ai_electronics_lab.verification`:

- `SIMULATION_VERIFIER_VERSION = "1.0"`
- `VERIFICATION_ABSOLUTE_TOLERANCE = 1e-9`
- `VERIFICATION_RELATIVE_TOLERANCE = 1e-6`
- `VERIFICATION_WARNING_MULTIPLIER = 10.0`
- `VERIFICATION_DENOMINATOR_FLOOR = 1e-12`
- `SimulationVerificationError`
- `VerificationTolerancePolicy`
- `VerificationComplexValue`
- `VerificationComparison`
- `VerificationRunResult`
- `SimulationVerificationResults`
- `verify_simulation_results(plan, parsed_results)`

The function accepts exactly one validated `CircuitPlan` and one
`SimulationParsedResults` instance and returns one immutable
`SimulationVerificationResults`.

## Trust boundary

Both inputs are treated as untrusted even though their normal constructors create frozen
dataclasses. Callers may manually construct objects or mutate frozen fields through low-level
mechanisms.

Before comparison or arithmetic, the verifier must:

1. require the outer plan object to be exactly `CircuitPlan`;
2. require deterministic circuit-plan validation to succeed;
3. require the parsed-results object to be exactly `SimulationParsedResults`;
4. require its version to equal `SIMULATION_RAW_PARSER_VERSION`;
5. require `runs` to be an exact tuple within the existing bounded run count;
6. require every run to be exactly `SimulationRunMeasurements`;
7. exact-type validate every run field before equality, ordering, hashing, division, or
   arithmetic;
8. require every complex voltage to be exactly `SimulationComplexValue`;
9. require every real and imaginary component to be an exact built-in finite float;
10. require complete structural coherence between the plan and every parsed run.

Boolean values are never accepted as numbers. User-defined numeric subclasses, mappings,
sequences, comparison operators, conversion hooks, and arithmetic hooks must not execute at the
verifier boundary.

Existing `SimulationVerificationError` instances are preserved. Unexpected malformed-object
failures are normalized to a stable `SimulationVerificationError` without exposing internal
object representations.

## Plan and result coherence

### RC analyses

For `rc_low_pass` and `rc_high_pass`:

- plan analysis must be `ac`;
- the parsed run count must equal the requested-frequency count;
- runs must be ordered as `ac-01`, `ac-02`, and so on;
- every run topology must exactly equal the plan topology;
- every run analysis kind must be `ac`;
- every run frequency must numerically equal the corresponding requested frequency;
- no additional, missing, duplicate, or reordered run is accepted.

### Resistive divider

For `resistive_divider`:

- plan analysis must be `dc`;
- requested frequencies must be empty;
- parsed results must contain exactly one run;
- the run ID must be `dc-op`;
- topology must be `resistive_divider`;
- analysis kind must be `dc`;
- frequency must be `None`.

A coherence failure is a verifier input error, not a PASS, WARN, or FAIL electrical result.

## Fixed tolerance policy

Version 1.0 uses one non-configurable tolerance policy:

- absolute tolerance: `1e-9`;
- relative tolerance: `1e-6`;
- warning multiplier: `10.0`;
- denominator floor: `1e-12`.

For an expected complex value `E` and measured complex value `M`:

    absolute_error = magnitude(M - E)
    pass_limit = absolute_tolerance + relative_tolerance * magnitude(E)
    warning_limit = warning_multiplier * pass_limit

Classification is performed without rounding:

- `PASS` when `absolute_error <= pass_limit`;
- `WARN` when `pass_limit < absolute_error <= warning_limit`;
- `FAIL` when `absolute_error > warning_limit`.

Relative error is:

    absolute_error / magnitude(E)

only when `magnitude(E) >= denominator_floor`. Otherwise relative error is `None`.

All limits and calculated metrics must remain finite. A non-finite intermediate or output is a
stable verifier error and must never be serialized.

## Complex-value representation

`VerificationComplexValue` contains exact built-in float fields:

- `real`;
- `imag`.

Its deterministic dictionary representation additionally contains:

- `magnitude`, calculated with `math.hypot`;
- `phase_degrees`, calculated with `atan2` and expressed in the interval
  `[-180.0, 180.0]`.

Phase is `None` when magnitude is below the denominator floor because phase is not meaningful
for a near-zero value.

No formatted engineering string participates in classification. Display formatting is a UI
concern only.

## Analytical RC model

For each RC run:

    omega = 2 * pi * frequency_hz
    x = omega * resistance_ohms * capacitance_farads
    cutoff_frequency_hz = 1 / (2 * pi * resistance_ohms * capacitance_farads)

The expected low-pass transfer function is:

    H_low = 1 / (1 + j*x)

evaluated without generic symbolic parsing as:

    real = 1 / (1 + x*x)
    imag = -x / (1 + x*x)

The expected high-pass transfer function is:

    H_high = j*x / (1 + j*x)

evaluated as:

    real = x*x / (1 + x*x)
    imag = x / (1 + x*x)

The trusted AC source expectation is:

    Vin_expected = 1 + j*0

The expected output voltage is:

    Vout_expected = Vin_expected * H

Each RC run produces comparisons in this exact order:

1. `vin_voltage`;
2. `transfer_function`;
3. `vout_voltage`.

The measured transfer function is `Vout_measured / Vin_measured`. Complex division must use a
bounded scale-aware algorithm and must not directly form an overflow-prone unscaled denominator
square.

When `magnitude(Vin_measured) < denominator_floor`, the transfer comparison is represented with:

- `measured = None`;
- `absolute_error = None`;
- `relative_error = None`;
- status `FAIL`;
- reason code `verification.denominator_too_small`.

The source-voltage and output-voltage comparisons remain available.

## Analytical resistive-divider model

For a resistive divider:

    ratio_expected =
        resistance_bottom_ohms
        / (resistance_top_ohms + resistance_bottom_ohms)

    Vin_expected = input_voltage_volts + j*0
    Vout_expected = input_voltage_volts * ratio_expected + j*0

The single divider run produces comparisons in this exact order:

1. `vin_voltage`;
2. `divider_ratio`;
3. `vout_voltage`.

The measured divider ratio is `Vout_measured / Vin_measured` using the same bounded scale-aware
complex division policy.

When `magnitude(Vin_measured) < denominator_floor`, the ratio comparison is represented with:

- `measured = None`;
- `absolute_error = None`;
- `relative_error = None`;
- status `FAIL`;
- reason code `verification.denominator_too_small`.

The source-voltage and output-voltage comparisons remain available.

## Comparison contract

`VerificationComparison` contains:

- `metric`, one of `vin_voltage`, `transfer_function`, `divider_ratio`, or
  `vout_voltage`;
- `expected`, as `VerificationComplexValue`;
- `measured`, as `VerificationComplexValue` or `None`;
- `absolute_error`, as a finite nonnegative float or `None`;
- `relative_error`, as a finite nonnegative float or `None`;
- `pass_limit`, as a finite positive float;
- `warning_limit`, as a finite positive float;
- `status`, one of `PASS`, `WARN`, or `FAIL`;
- `reason_code`.

Normal comparison reason codes are:

- `verification.within_tolerance`;
- `verification.near_tolerance`;
- `verification.outside_tolerance`.

The denominator failure reason is:

- `verification.denominator_too_small`.

Comparison values and errors are not rounded before classification or serialization.

## Run and overall status

Status severity order is:

    PASS < WARN < FAIL

`VerificationRunResult.status` is the greatest severity among its comparisons.

`SimulationVerificationResults.status` is the greatest severity among all runs.

No run may contain zero comparisons. No verification result may contain zero runs.

Each run also contains an ordered, duplicate-free tuple of its comparison reason codes.

## Immutable result schema

`VerificationTolerancePolicy` contains:

- `absolute_tolerance`;
- `relative_tolerance`;
- `warning_multiplier`;
- `denominator_floor`.

`VerificationRunResult` contains:

- `run_id`;
- `topology`;
- `analysis_kind`;
- `frequency_hz`;
- `cutoff_frequency_hz`, present for RC and `None` for a divider;
- `status`;
- ordered `reason_codes`;
- ordered `comparisons`.

`SimulationVerificationResults` contains:

- `version`;
- `status`;
- `tolerance_policy`;
- ordered `runs`.

All sequence fields are exact immutable tuples after construction.

`to_dict()` returns only built-in JSON-compatible values in stable field order.

`to_json()` uses:

- ASCII-safe output;
- `allow_nan=False`;
- compact separators;
- sorted object keys.

Equal validated inputs must produce byte-identical JSON.

## Error contract

`SimulationVerificationError` contains:

- `code`;
- `path`;
- `message`.

The exception string may include the stable code and path, but web responses must not copy the
exception string.

Required stable error families include:

- `verification.input.malformed`;
- `verification.plan.invalid`;
- `verification.version.unsupported`;
- `verification.results.mismatch`;
- `verification.value.non_finite`;
- `verification.numeric_overflow`.

Paths identify the first deterministic failure, for example:

    ("plan", "parameters", "resistance_ohms")
    ("parsed_results", "runs", 1, "frequency_hz")
    ("parsed_results", "runs", 0, "vin_voltage", "real")

Error messages must be stable, concise, non-secret, and independent of hostile object
representations.

## Web integration

The existing localhost simulation service must call the verifier only after successful raw
parsing:

    plan
    -> assembly
    -> deck
    -> runner
    -> raw parser
    -> deterministic verifier
    -> safe response

A successful response adds:

    "verification_kind": "deterministic_analytical_verification"
    "verification": <SimulationVerificationResults.to_dict()>

The existing plan, trusted deck, schematic, and parsed results remain present.

The notice becomes:

    Deterministic ngspice evidence with analytical verification; not an LLM assertion.

`SimulationVerificationError` maps to a stable safe web error:

- HTTP status: `502`;
- code: `simulation.verification_invalid`;
- message: `The deterministic simulation evidence could not be verified.`;
- path: empty.

The web response must not expose verifier exception strings, internal paths, object
representations, stack traces, raw evidence, child output, executable paths, temporary paths,
environment data, or secrets.

## UI integration

The self-contained page adds a deterministic verification panel after parsed voltage
measurements.

The panel displays:

- overall PASS, WARN, or FAIL;
- fixed tolerance policy;
- one row or card per simulation run;
- cutoff frequency for RC runs;
- each comparison metric;
- expected and measured complex values;
- magnitude and phase when meaningful;
- absolute and relative errors;
- pass and warning limits;
- stable reason code.

PASS, WARN, and FAIL must be communicated by text, not color alone.

Dynamic values must use `textContent` and DOM element creation. Dynamic `innerHTML`, external
assets, external scripts, and external styles remain prohibited.

## Acceptance tests

Core tests must cover:

1. exact low-pass analytical transfer values;
2. exact high-pass analytical transfer values;
3. exact divider ratio and output values;
4. source-voltage verification;
5. output-voltage verification;
6. transfer-function and divider-ratio verification;
7. PASS at and below the pass limit;
8. WARN immediately above the pass limit and at the warning limit;
9. FAIL immediately above the warning limit;
10. near-zero expected values with `relative_error=None`;
11. zero and near-zero measured Vin denominator handling;
12. scale-aware complex division;
13. negative divider input voltage;
14. minimum and maximum valid circuit-plan values;
15. multiple ordered AC runs;
16. mismatched run counts, IDs, topologies, analyses, and frequencies;
17. unsupported versions;
18. exact-type rejection for booleans and numeric subclasses;
19. mutated dataclasses and hostile field objects;
20. non-finite measurement values;
21. arithmetic overflow normalization;
22. immutability;
23. deterministic dictionaries and byte-identical canonical JSON;
24. public exports and function annotations.

Integration tests must cover:

25. RC low-pass plan through real ngspice and verifier;
26. RC high-pass plan through real ngspice and verifier;
27. divider plan through real ngspice and verifier;
28. all default UI examples producing overall PASS;
29. safe API serialization of verification evidence;
30. stable safe verifier-error mapping;
31. UI rendering without dynamic `innerHTML`;
32. omission of raw evidence and process details;
33. complete suite, Ruff, source compilation, wheel package-data verification, and live
    localhost smoke.

Optional real-ngspice tests may skip only when neither approved fixed executable path exists.

## Implementation boundaries

Planned implementation files are limited to:

- `src/ai_electronics_lab/verification/__init__.py`;
- `src/ai_electronics_lab/verification/evidence.py`;
- `tests/verification/test_evidence.py`;
- existing web application and page integration files;
- existing web tests;
- public documentation and decision records.

No new runtime dependency is required.

The implementation must remain unstaged and uncommitted until independent audit and explicit
authorization.

## Explicit exclusions

Version 1.0 does not include:

- an LLM or model provider;
- natural-language explanations;
- user-configurable tolerances;
- probabilistic scoring;
- statistical Monte Carlo analysis;
- transient analysis;
- BJT or nonlinear-device verification;
- arbitrary expressions or symbolic parsers;
- arbitrary SPICE;
- raw-file access;
- filesystem paths;
- executable selection;
- uploads;
- persistence;
- authentication;
- public deployment;
- Docker;
- Cloudflare;
- MCP;
- ADK.
