# Cortex platform and navigation context

Cortex is a local, single-user, workspace-based document intelligence application. V1 supports Markdown, text, DOCX, and PDF ingestion; document-grounded chat; hybrid retrieval; optional Microsoft GraphRAG; durable background workflows; and verified property LIST/COUNT queries. It is not web search, multi-user collaboration, external connectors, backup/restore, or current-world knowledge. After root `AGENTS.md`, use this file for platform/navigation, `02-query-data-and-indexing.md` for query/data work, and `03-operations-rules-and-debugging.md` for deployment, invariants, status, or diagnostics.

```text
Browser (React/Vite) → FastAPI → SQLite (authoritative relational state)
                           ↘ Redis → Dramatiq worker
FastAPI/worker → Qdrant (workspace-filtered dense projections)
FastAPI/worker → Neo4j (workspace-scoped extracted/canonical graph layers)
worker → workspace files (source, normalized Markdown, BM25, GraphRAG artifacts)
FastAPI/worker → configured Ollama/OpenAI/Anthropic adapters
```

The backend owns API contracts and command/query persistence. The worker owns long-running side effects. SQLite is relational source-of-record; Neo4j is the Query V2 persistent/queryable knowledge graph; Qdrant and BM25 are retrieval projections. GraphRAG workspace artifacts are extracted producer output, not canonical truth; active V1 Local/Global/DRIFT still reads them until V2 cutover.

Start with root `AGENTS.md`, `.ai/project-map.yaml`, and `docs/ai/index.md`. For query/retrieval/aggregation/citation work read `docs/architecture/CORTEX_RULEBOOK.md`. Main locations: query planning/execution `backend/app/chat/`; retrieval `backend/app/retrieval/`; property aggregation `backend/app/aggregation/property.py`; ingestion `backend/app/ingestion/`; GraphRAG `backend/app/graphrag/`; workflows `backend/app/workflows/`; relational models/migrations `backend/app/models.py` and `backend/alembic/`; frontend system map `frontend/src/flow/ASystemMap.tsx`.

Query V2 target ownership is scaffolded under `backend/app/query/`, `knowledge/`, `engines/`, and
`reasoning/`, each with child scoped context. These are navigation and ownership boundaries until
their implementation phases activate them; the active V1 runtime paths above remain authoritative.

`/knowledge` is the workspace-scoped manual canonical curation route. It lists canonical entities,
exact evidence spans and identity history, and exposes reason-required merge, split, and alias
commands. Automatic canonical population is deferred to Query V2 Phase 05.

Binding product decisions and implementation status are in `codex-prompts/`. Architecture docs live in `docs/architecture/`; tests are under `backend/tests/` and `frontend/src/**/*.test.tsx`; deployment/configuration is under `infrastructure/`.
