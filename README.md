# Cortex

Cortex is a local, single-user, workspace-based knowledge platform. Its V1 architecture
is specified by the versioned build pack in [`codex-prompts/`](codex-prompts/README.md).

## Development baseline

- Node.js 24.x, enabled through Corepack, with `pnpm@10.4.1`
- Python 3.11.x and uv
- Docker Desktop/WSL2 on Windows 11

Enable the JavaScript package manager with `corepack enable`, then use `corepack pnpm`.
Python runtime and development dependencies are declared in `backend/pyproject.toml` and
resolved by the committed `backend/uv.lock`. No floating dependency or Docker image
versions are permitted.

## Repository navigation

Start with [`AGENTS.md`](AGENTS.md) for AI-assisted work and
[`docs/ai/index.md`](docs/ai/index.md) for module routing. Runtime data belongs under
`data/` and is intentionally not versioned. `codex-prompts/IMPLEMENTATION_STATUS.md`
is the authoritative implementation tracker.

## Validation commands

```powershell
python scripts/ai-context/generate-adapters.py
python scripts/ai-context/validate-context.py
python scripts/ai-context/check-context-freshness.py
python scripts/license-report.py
```

Create the backend environment and install pinned dependencies with uv:

```powershell
cd backend
uv venv --python 3.11
uv sync --dev --group graphrag
uv run pre-commit run --all-files
```
