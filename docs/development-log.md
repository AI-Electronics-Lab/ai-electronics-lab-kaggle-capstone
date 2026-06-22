# Development log

## Initial extraction phase

- Created an isolated, user-owned private reference snapshot.
- Verified the snapshot against the selected production `origin/main` commit.
- Removed all Git remotes from the private reference snapshot.
- Confirmed production-only untracked files were not copied.
- Audited repository structure and static dependencies.
- Reviewed the three required topology knowledge files.
- Chose an allowlist-based extraction and compact local architecture.

## Deterministic core extraction

- Approved 26 source and focused-test files through the direct-copy allowlist.
- Verified every imported file against the private SHA-256 manifest.
- Confirmed zero critical findings in the pre-import content scan.
- Ran the isolated baseline test suite successfully before copying.
- Imported only the approved deterministic core and focused tests.
- Kept private Git history and production infrastructure outside this repository.

## Reproducible Python project foundation

- Added an installable `pyproject.toml` using the standard `src` package layout.
- Replaced repository-relative test imports with installed-package imports.
- Added a locked uv development environment.
- Added local verification for linting, tests, and package imports.
- Added GitHub Actions CI using the same locked environment.
- Deferred global line-length reformatting so this infrastructure change remains reviewable.

## Canonical CircuitPlan contract

- Specified the version 1.0 planner-to-deterministic-code boundary for the three initial topologies.
- Added an immutable standard-library contract with defensive copying, deterministic serialization,
  structured validation errors, and a raising validation helper.
- Added focused coverage for valid plans and deterministic rejection boundaries.

## Deterministic RC high-pass topology

- Added the series-capacitor, shunt-resistor RC high-pass topology block and registry descriptor.
- Added deterministic graph validation and SPICE connectivity coverage without extending schematic
  rendering or adding plan adaptation and simulation behavior.

## Deterministic resistive-divider topology

- Added the passive upper-resistor, lower-resistor divider topology and registry descriptor.
- Recorded source-independent divider ratio and Thevenin resistance metrics in deterministic graph
  metadata.
- Added DC-only graph validation and passive SPICE connectivity coverage without adding a voltage
  source, plan adaptation, or schematic changes.

## Deterministic CircuitPlan adapter

- Added validation-before-dispatch conversion from the canonical `CircuitPlan` to the three trusted
  topology builders using fixed input, output, and ground nodes.
- Preserved canonical plan data as inert provenance metadata while deferring sources, requested
  sweep construction, analysis execution, and divider input voltage to a later assembly layer.

## Deterministic simulation assembly

- Added validation-first assembly of trusted passive topology IR with exactly one fixed-policy
  voltage source and a typed, non-executable analysis request.
- Preserved canonical plan provenance and requested frequencies while keeping assumptions inert and
  deferring bounded analysis-directive rendering, simulator execution, and result handling to later
  layers.

## Bounded simulation-deck rendering

- Added defensive validation for manually constructed assemblies before executable analysis text is
  emitted.
- Expanded exact requested AC frequencies into bounded independent single-point decks and DC intent
  into one operating-point deck.
- Reused deterministic component rendering while preserving inert metadata and allowing only the
  generated analysis directive plus the final `.end`.
