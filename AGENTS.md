# Cortex AI Development Context

Read this file before changing Cortex. The binding V1 product and architecture decisions
are in `codex-prompts/MASTER_PROMPT.md` and `codex-prompts/docs/DECISIONS.md`; do not
silently deviate from them. Use `.ai/project-map.yaml` and `docs/ai/index.md` to find the
smallest relevant module before searching files.

## Working rules

- Keep `codex-prompts/IMPLEMENTATION_STATUS.md` truthful: mark work complete only after
  implementation and validation.
- Update the owning architecture, workflow, API, or frontend document whenever a public
  contract, schema, module boundary, folder layout, or operational behavior changes.
- Pin every application dependency and Docker image to an exact version. Regenerate the
  lockfile when dependencies change; never hand-edit a generated lockfile.
- Do not inspect or add `data/`, caches, generated clients, build outputs, dependencies,
  model files, indexes, uploads, or logs unless the current task explicitly needs them.
- Follow the nearest scoped `AGENTS.md` after entering a module. Scoped instructions add
  to this file and do not replace it.
- Run the relevant context validation and focused tests before completing a phase.

## Navigation

| Area                  | First context file                |
| --------------------- | --------------------------------- |
| User interface        | `frontend/AGENTS.md`              |
| Backend platform      | `backend/AGENTS.md`               |
| Retrieval             | `backend/app/retrieval/AGENTS.md` |
| GraphRAG              | `backend/app/graphrag/AGENTS.md`  |
| Jobs and workflows    | `backend/app/workflows/AGENTS.md` |
| Docker and operations | `infrastructure/AGENTS.md`        |

Generate thin tool adapters with `python scripts/ai-context/generate-adapters.py` and
validate the system with `python scripts/ai-context/validate-context.py`.
