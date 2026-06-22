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
