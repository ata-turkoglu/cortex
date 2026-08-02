# AI Context Index

Use this index instead of scanning the repository broadly. Start at root `AGENTS.md`, then
select the smallest matching path in `.ai/project-map.yaml` and read its scoped context.

| Need                       | Read first                        | Supporting documentation                    |
| -------------------------- | --------------------------------- | ------------------------------------------- |
| UI, routes, adapters       | `frontend/AGENTS.md`              | `docs/frontend/README.md`                   |
| API, persistence, services | `backend/AGENTS.md`               | `docs/api/contract.md`                      |
| Hybrid retrieval           | `backend/app/retrieval/AGENTS.md` | `docs/architecture/retrieval-boundaries.md` |
| Microsoft GraphRAG         | `backend/app/graphrag/AGENTS.md`  | `docs/architecture/graphrag-boundary.md`    |
| Jobs and SSE               | `backend/app/workflows/AGENTS.md` | `docs/workflows/durable-workflows.md`       |
| Docker and host services   | `infrastructure/AGENTS.md`        | `docs/architecture/deployment.md`           |

Never scan runtime data, package caches, virtual environments, generated API clients,
indexes, uploads, model files, or logs without a task-specific need.
