# Fresh-clone reproducibility evidence

## Evidence record

- Audit date: `2026-06-24T17:10:27Z`
- Evaluated commit: `ae678731879a9d9a9c799c3d51d60f443fab7170`
- Operating system: `Ubuntu 24.04.4 LTS`
- Python: `Python 3.11.15`
- uv: `uv 0.11.21 (x86_64-unknown-linux-gnu)`
- Git: `git version 2.43.0`
- ngspice executable: `/usr/bin/ngspice`
- ngspice version: `ngspice-42`
- ngspice version source: `ngspice --version`
- Planner model configured for the audit: `openai/gpt-oss-120b:free`

The audit used a new temporary directory and a public HTTPS clone of the repository. It did not reuse
the canonical repository virtual environment or working tree.

## Commands exercised

The reproducibility path was:

    git clone https://github.com/AI-Electronics-Lab/ai-electronics-lab-kaggle-capstone.git
    cd ai-electronics-lab-kaggle-capstone
    git checkout --detach ae678731879a9d9a9c799c3d51d60f443fab7170
    uv sync --extra dev --extra adk --frozen
    uv run ruff check .
    uv run pytest -q
    uv run python -c "import ai_electronics_lab; print('package_import=ok')"
    uv run --env-file .env uvicorn ai_electronics_lab.web.app:app \
      --host 127.0.0.1 \
      --port 18801 \
      --no-server-header \
      --no-access-log \
      --log-level warning

The ignored `.env` file was created with mode `0600` using only the allowlisted local
`OPENROUTER_*` settings. The source path and secret value were not recorded or published.

The supported live request was equivalent to:

    curl \
      --header "Content-Type: application/json" \
      --data '{"prompt":"Design a resistive voltage divider with a 12 volt input, a 10000 ohm top resistor, and a 5000 ohm bottom resistor."}' \
      http://127.0.0.1:18801/api/orchestrate

## Results

| Check | Result |
| --- | --- |
| Public fresh clone | PASS |
| Detached checkout of named commit | PASS |
| Frozen dependency installation | PASS |
| Ruff | PASS |
| Automated tests | 634 passed, 5 deprecation warnings |
| Package import smoke | PASS |
| Ignored `.env` with mode `0600` | PASS |
| Localhost application startup | PASS |
| Supported live prompt HTTP result | 200 |
| Orchestration status | PASS |
| Planned topology | `resistive_divider` |
| Planned analysis | `dc` |
| Deterministic verification | PASS |
| Stage trace | 12 events |
| First stage | `request.received` |
| Final stage | `request.completed` |
| API-key disclosure check | PASS |
| Fresh-clone tracked worktree | clean |

The readiness loop observed one initial localhost connection refusal while Uvicorn was starting. A
later readiness probe succeeded, the live request returned HTTP 200, and the server shut down
normally after the audit.

The first version-summary parser captured the ngspice banner separator rather than the version text.
The version shown above was re-read from the same approved ngspice executable using the recorded
version source.

## Security handling

The public evidence does not contain:

- the real `.env` file;
- the OpenRouter API key;
- raw provider output;
- raw ngspice process output;
- temporary clone paths;
- server logs;
- the complete orchestration response;
- private production traces.

Only non-sensitive environment versions, commands, and result summaries are recorded.

## Interpretation and limitations

This audit demonstrates that the named public commit can be cloned into a new temporary directory,
installed from the frozen lockfile, linted, tested, started on localhost, and used for one live
supported resistive-divider request.

It does not yet provide final submission screenshots or one live run for every supported topology.
It does not prove future commits remain reproducible, guarantee OpenRouter availability, or establish
safe public hosting. A new audit is required after materially changing dependencies, startup
instructions, runtime boundaries, or the release candidate commit.
