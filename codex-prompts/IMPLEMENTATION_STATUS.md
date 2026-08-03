# Cortex Implementation Status

Codex must keep this file updated.

## Overall

- [x] Phase 1 — Repository and AI context
- [x] Phase 2 — Frontend foundation
- [x] Phase 3 — Backend foundation
- [x] Phase 4 — Database and workspace
- [x] Phase 5 — Document ingestion
- [x] Phase 6 — Retrieval and GraphRAG
- [x] Phase 7 — Jobs, workflows, and monitoring (user-approved operational deferrals)
- [x] Phase 8 — Chat and query
- [ ] Phase 9 — Settings and system map
- [ ] Phase 10 — Validation and hardening

## Current phase

- Phase: Phase 8 — Chat and query
- Status: Complete
- Started: 2026-08-02
- Last updated: 2026-08-03

## Completed work

- Created the Git-backed Cortex monorepo skeleton and runtime-data ignore policy.
- Added canonical/scoped AI instructions, project map, adapter generator, context validation, and freshness checks.
- Added initial architecture, API, workflow, frontend, dependency, licensing, linting, and pre-commit documentation/configuration.
- Installed pinned JavaScript and Python development tooling in ignored local dependency directories.
- Started Phase 2: created the Vite/React/TypeScript shell, pinned frontend dependency graph, Tailwind and PrimeReact setup, route placeholders, UI adapters, icon registry, platform layout, appearance store, and generated-API boundary.
- Started Phase 3: added FastAPI `/api/v1` application, correlation IDs, standard error envelope, health service map, SQLite WAL/foreign-key configuration, secret-store abstraction, model defaults, and initial Docker Compose topology.
- Started Phase 4: added workspace resource/state records, WorkspaceContext, workspace CRUD/soft-delete endpoints, and the relational schema migration.
- Started Phase 5: added secure workspace uploads, document versioning and deduplication,
  Docling normalization, folder assignment, metadata provenance, chunking, and ingestion-run persistence.
- Started Phase 6: added isolated Qdrant, hybrid-retrieval, embedding, and GraphRAG adapter
  boundaries; deterministic vector IDs; common evidence/answer-state models; GraphRAG artifact
  and rebuildable NetworkX support; retrieval migration and focused adapter tests.
- Completed Phase 6's persistent per-workspace bm25s boundary, configurable hybrid-retrieval
  limits, and local-only BGE reranker adapter. Hybrid Search now remains available while a
  workspace graph is absent or stale.
- Added the worker-owned Microsoft GraphRAG CLI adapter for workspace-isolated index execution
  and distinct Local, Global, and DRIFT queries. The native GraphRAG workspace output remains
  canonical; Qdrant and NetworkX continue as separately rebuildable projections.
- Wrapped each GraphRAG route as a separate LlamaIndex `CustomQueryEngine`, preserving normalized
  evidence as workspace-scoped source nodes for the future router.
- Added explicit stale-graph signaling when an upstream query fails, allowing a future router to
  fall back safely to Hybrid Search without representing stale output as grounded evidence.
- Added embedding-configuration fingerprints that include model, digest, dimensions,
  normalization, and text-template version. Dense Qdrant reads/writes are configuration-filtered;
  a changed configuration records a full-reindex requirement and blocks incompatible dense search.
- Added a testable Ollama `/api/embed` health check and a dedicated Qwen3 query/document
  preparation adapter that preserves Turkish Unicode and normalizes line endings.
- Added a workspace-isolated GraphRAG input materializer for active normalized document versions;
  the future deferred-update worker can use its manifest without mixing workspace inputs.
- Added GraphRAG workspace initialization through the supported CLI, producing the workspace's
  own `settings.yaml` before worker-owned input materialization and index execution.
- Completed the deferred GraphRAG update stages, including transaction-safe input snapshotting,
  opt-in eligible Batch API stage planning, NetworkX rebuilding, and canonical-output mirroring
  into workspace-isolated Qdrant collections. Added durable, idempotent dense-reindex requests
  plus Turkish/cross-lingual and BGE-M3 adapter smoke coverage.
- Started Phase 7: added versioned durable workflow definitions, SQLite run/step/event state,
  workspace locks, Dramatiq execution/restart recovery, REST commands, an SSE event stream,
  a React Flow-backed process view, EventSource reconnect/state restoration, stage concurrency
  caps, retention cleanup, idempotent relational deletion checkpoints, and secret redaction in
  persisted workflow errors. Added tested LlamaIndex ingestion and reindex workflow definitions
  that isolate the normalized-document and workspace-scoped reindex handoffs, plus separate
  durable query-run and query-step records for the chat phase. The process UI now supports
  selecting runs, grouped step details, recovery actions, and a sanitized technical-error dialog
  backed by event history. Global shell progress is restored independently of the processes page.

- Completed Phase 8: added an actual LlamaIndex RouterQueryEngine builder with a constrained
  selector, worker-owned OpenAI Responses synthesis and conversation summary calls, inference
  labels, memory-window summaries, source-details dialog, message pagination, soft-budget
  pausing, token/cost recording, query-latency capture, and generated OpenAPI Chat types.

## In progress


- No Phase 8 work remains. Phase 9 is next.
  summarization, LlamaIndex Router integration, message editing, source-detail navigation,
  cost-budget enforcement, generated-client regeneration, and large-history pagination remain.

- Phase 7 now has the foundational durable executor and monitoring surface. It still needs
  specialized ingestion/reindex/deletion step adapters, true EventSource reconnect handling,
  retention/concurrency controls, and end-to-end crash/cleanup coverage before completion.

- Deferred by user decision: production OpenAI/Anthropic request adapters and automatic provider-reported token counting. See `docs/FUTURE_BACKLOG.md`.

## Blocking issues

- No Phase 6 blocker remains. A real GraphRAG run still needs a configured provider/model and a
  worker-owned runtime flow; it must not be invoked from an API/database transaction.

## Validation history

| Date | Phase | Command | Result |
| ---- | ----- | ------- | ------ |
| 2026-08-02 | 1 | `python scripts/ai-context/generate-adapters.py` | Passed |
| 2026-08-02 | 1 | `python scripts/ai-context/validate-context.py` | Passed |
| 2026-08-02 | 1 | `python scripts/ai-context/check-context-freshness.py` | Passed |
| 2026-08-02 | 1 | `pre-commit run --all-files` | Passed |
| 2026-08-02 | 1 | `python scripts/license-report.py` | Passed; generated declared-dependency inventory |
| 2026-08-02 | 2 | `corepack pnpm --dir frontend build` | Passed |
| 2026-08-02 | 2 | `corepack pnpm --dir frontend test` | Passed (1 test) |
| 2026-08-02 | 2 | `corepack pnpm --dir frontend lint` | Passed |
| 2026-08-02 | 2 | adapter-boundary search | Passed; no feature-level PrimeReact, lucide-react, or React Flow imports |
| 2026-08-02 | 3 | `python -m pytest tests -q` (from `backend`) | Passed (1 test) |
| 2026-08-02 | 3 | `alembic -c alembic.ini upgrade head` (from `backend`) | Passed |
| 2026-08-02 | 3 | `ruff check app tests alembic` (from `backend`) | Passed |
| 2026-08-02 | 3 | `python -m pytest tests -q` (from `backend`) | Passed (3 tests) |
| 2026-08-02 | 3 | `docker compose -f infrastructure/docker-compose.yml config` | Passed |
| 2026-08-02 | 3 | `GET /api/v1/health` via Docker Compose | Passed; backend, SQLite, Redis, Qdrant, Ollama, and worker healthy |
| 2026-08-02 | 3 | `corepack pnpm api:generate` | Passed; generated OpenAPI TypeScript schema |
| 2026-08-02 | 4 | `python -m pytest tests -q -p no:cacheprovider` (from `backend`) | Passed (9 tests) |
| 2026-08-02 | 4 | Alembic upgrade from empty SQLite and from revision `0002_usage_records` | Passed; prior data preserved |
| 2026-08-02 | 6 | `python -m pytest tests -q -p no:cacheprovider` (from `backend`) | Passed (38 tests) |
| 2026-08-02 | 6 | `CORTEX_DATABASE_URL=sqlite:///:memory: alembic -c alembic.ini upgrade head` | Passed; revision `0007_graphrag_stage_reports` applies |
| 2026-08-02 | 6 | `CORTEX_DATABASE_URL=sqlite:///:memory: alembic -c alembic.ini upgrade head` | Passed; revision `0006_retrieval_embedding_state` applies |
| 2026-08-02 | 6 | `python scripts/ai-context/validate-context.py` | Passed |
| 2026-08-03 | 6 | `uv run ruff check app/retrieval app/core/config.py tests/test_retrieval.py` (from `backend`) | Passed |
| 2026-08-03 | 6 | `uv run pytest -q tests/test_retrieval.py` (from `backend`) | Passed (9 tests) |
| 2026-08-03 | 6 | `uv run ruff check app/graphrag tests/test_graphrag_adapter.py` (from `backend`) | Passed |
| 2026-08-03 | 6 | `uv run pytest -q tests/test_graphrag_adapter.py tests/test_graphrag_qdrant.py tests/test_graphrag_updates.py` (from `backend`) | Passed (6 tests) |
| 2026-08-03 | 6 | `uv run pytest -q -p no:cacheprovider` (from `backend`) | Passed (44 tests; local Qdrant payload-index warning only) |
| 2026-08-03 | 6 | `CORTEX_DATABASE_URL=sqlite:///:memory: uv run alembic -c alembic.ini upgrade head` (from `backend`) | Passed |
| 2026-08-03 | 6 | `uv run pytest -q tests/test_graphrag_adapter.py` (from `backend`) | Passed (5 tests; upstream Pydantic warning only) |
| 2026-08-03 | 6 | `uv run pytest -q tests/test_graphrag_adapter.py` (from `backend`) | Passed (6 tests; upstream Pydantic warning only) |
| 2026-08-03 | 6 | `uv run pytest -q tests/test_retrieval.py` (from `backend`) | Passed (12 tests; local Qdrant payload-index warning only) |
| 2026-08-03 | 6 | `uv run pytest -q tests/test_embeddings.py` (from `backend`) | Passed (4 tests) |
| 2026-08-03 | 6 | `uv run pytest -q -p no:cacheprovider` (from `backend`) | Passed (51 tests; upstream Pydantic and local-Qdrant warnings only) |
| 2026-08-03 | 6 | `uv run pytest -q tests/test_graphrag_adapter.py` (from `backend`) | Passed (7 tests; upstream Pydantic warning only) |
| 2026-08-03 | 6 | `uv lock --check --no-cache; uv run pytest -q -p no:cacheprovider; CORTEX_DATABASE_URL=sqlite:///:memory: uv run alembic -c alembic.ini upgrade head` (from `backend`) | Passed (56 tests; warnings only) |
| 2026-08-03 | 6 | `uv run python scripts/ai-context/validate-context.py; uv run python scripts/ai-context/check-context-freshness.py` | Passed |
| 2026-08-03 | 7 | focused workflow lint/tests and in-memory Alembic upgrade | Passed (4 tests) |
| 2026-08-03 | 7 | `corepack pnpm build && corepack pnpm lint` (from `frontend`) | Passed (bundle-size advisory only) |
| 2026-08-03 | 7 | context validation and freshness checks | Passed |
| 2026-08-03 | 7 | focused workflow, LlamaIndex, API, and migration validation | Passed (9 tests; upstream Pydantic warnings only) |
| 2026-08-03 | 7 | `corepack pnpm build && corepack pnpm lint` (from `frontend`) | Passed (bundle-size advisory only) |

## High-risk boundary status

- [x] GraphRAG–Qdrant adapter validated
- [ ] SQLite concurrency validated
- [x] OpenAPI client generation validated
- [ ] Crash recovery validated
- [x] Upload security validated
- [ ] Orphan reconciliation validated
- [ ] 5,000-file performance baseline documented
- [ ] Third-party license notices complete

## Setup, model, and cost-control status

- [ ] First-run setup wizard complete
- [ ] Secure secret storage complete
- [ ] Default model profile seeded
- [ ] OpenAI cost accounting complete
- [ ] Budget controls complete
- [ ] GraphRAG cost controls complete
- [ ] Windows compatibility validated
- [ ] Evaluation fixture schema validated

## Multilingual embedding status

- [ ] qwen3-embedding:0.6b default configured
- [ ] Ollama embedding health check complete
- [ ] Turkish retrieval smoke tests complete
- [ ] Cross-lingual retrieval smoke tests complete
- [ ] Embedding configuration migration/reindex validated
- [ ] Qdrant dimension safeguards validated
