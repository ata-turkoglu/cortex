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
| Query Architecture V2 discovery | `docs/architecture/discovery/query-v2/01-query-runtime.md` | `02-data-indexing-and-knowledge.md`, `03-architecture-boundaries-and-v2-decisions.md` (descriptive investigation; not binding architecture) |
| Production Query V2 runtime | `backend/app/query/production_chat.py` | `docs/architecture/query-v2/query-runtime.md`, then the smallest `backend/app/query/` owner |
| System Map V2 manifest | `frontend/AGENTS.md` | `docs/architecture/system-map-index.md`, `frontend/src/flow/ASystemMap.tsx` |
| V2 conversation/query planning | `backend/app/query/AGENTS.md` | choose `context`, `understanding`, `ir`, `planning`, or `orchestration` child context |
| V2 physical execution planning | `backend/app/query/planning/AGENTS.md` | `docs/architecture/query-v2/execution-planning.md` |
| V2 result and evidence convergence | `backend/app/query/orchestration/AGENTS.md` | `docs/architecture/query-v2/result-evidence-layer.md` |
| V2 canonical knowledge | `backend/app/knowledge/AGENTS.md` | choose `graph`, `entities`, `relations`, `events`, `temporal`, `claims`, or `provenance` child context |
| V2 Neo4j graph storage | `backend/app/knowledge/graph/AGENTS.md` | `docs/architecture/query-v2/knowledge-construction.md`, `docs/architecture/graphrag-boundary.md` |
| V2 execution engines | `backend/app/engines/AGENTS.md` | `structured`, `graph`, or `hybrid`; retrieval/GraphRAG retain their existing contexts |
| V2 structured and graph engines | `backend/app/engines/structured/AGENTS.md` | `backend/app/engines/graph/AGENTS.md`, `docs/architecture/query-v2/structured-graph-engines.md` |
| V2 research/composition | `backend/app/reasoning/AGENTS.md` | choose `research` or `composition` child context |

Production V2 capability status: `retrieval.grounded` is ready; `graphrag.grounded` is partial and
readiness-dependent; SQLite `canonical.structured` is queryable when its projection is operational
and exposes query-scoped `COMPLETE`/`PARTIAL`/`UNAVAILABLE` metadata; `canonical.graph` is not
production accepted.
Historical V1 discovery notes and compatibility code must not be used as the primary query path.

Never scan runtime data, package caches, virtual environments, generated API clients,
indexes, uploads, model files, or logs without a task-specific need.
