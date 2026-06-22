#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

uv sync --extra dev --frozen
uv run ruff check .
uv run pytest -q
uv run python -c "import ai_electronics_lab; print('package_import=ok')"
