# Cortex Implementation Status

Codex must keep this file updated.

## Overall

- [x] Phase 1 — Repository and AI context
- [x] Phase 2 — Frontend foundation
- [x] Phase 3 — Backend foundation
- [x] Phase 4 — Database and workspace
- [x] Phase 5 — Document ingestion
- [x] Phase 6 — Retrieval and GraphRAG
- [x] Phase 7 — Jobs, workflows, and monitoring
- [x] Phase 8 — Chat and query
- [x] Phase 9 — Settings and system map
- [x] Phase 10 — Validation and hardening

## Current phase

- Phase: Structured query understanding follow-up
- Status: Complete; focused validation passed.
- Active validation target: None
- Started: 2026-08-02
- Last updated: 2026-08-08

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
- Added entity-document lookup planning and synthesis: Turkish/English document-list questions
  now set `entity_document_lookup` and `needs_list`, exact entity matches are prioritized, chunks
  are grouped into unique document results with identity metadata, and answers emit one concise
  row and citation per document.
- Updated the System Map query flow with the document-list intent decision and unique-document
  grouping branch. The Processes page remains unchanged because the feature uses the existing
  persisted `route`, `retrieve`, and `synthesize` query steps.
- Completed the multi-document DOCX ingestion audit and correction. DOCX Word Heading 2 styles
  are normalized to Markdown `##`, and the splitter uses only those headings—never archive-code
  prefixes—to create first-class logical documents with code/title/type/source/page metadata;
  chunks cannot cross logical boundaries; GraphRAG materializes one input per logical document
  and resolves entity
  provenance through text units; retrieval returns logical codes; and a workspace-scoped
  ingestion diagnostics endpoint exposes the source-to-retrieval trace. Ingestion workflow v3
  and the System Map/Processes flows include the logical-document checkpoint.
- Completed the worker-owned GraphRAG query protocol. The API persists and submits a durable
  QueryRun through Redis/Dramatiq, while the GraphRAG-capable worker resolves persisted selected
  settings, executes Local/Global/DRIFT outside a SQLite write transaction, and records the final
  native answer, evidence, trace, and stage usage. Bounded API waits fail safely without allowing
  a late worker result to overwrite a terminal timeout; GraphRAG final answers bypass synthesis.
- Updated the System Map with the durable GraphRAG query boundary, explicit-fallback path,
  optional default-off claims, algorithmic community detection, and user-selected community report
  generation.
- Wired ordinary `hybrid` chat routes and the opt-in GraphRAG fallback to the real
  workspace-scoped `HybridRetriever` runtime (configured embeddings, Qdrant, persisted BM25,
  RRF, optional local reranker, evidence limits, citations, and sanitized retrieval trace data).

## In progress

- No active implementation phase.
- Completed structured query planning, workspace-evidence entity resolution, bounded resolved-name
  retrieval expansion, operation-aware evidence selection, synchronous OpenAI hybrid synthesis,
  and query-plan debug output. COUNT/LIST answers explicitly retain aggregation/completeness
  uncertainty until their deferred execution layers exist.
- Deferred by user decision: production OpenAI/Anthropic request adapters and automatic provider-reported token counting. See `docs/FUTURE_BACKLOG.md`.

## Blocking issues

- No implementation blocking issue remains. A live GraphRAG run requires user-provisioned
  provider credentials and model configuration; this is an operational prerequisite, not a
  code or deployment blocker.

## Validation history

| Date | Phase | Command | Result |
| 2026-08-14 | Structured query understanding | `ruff check --no-cache app/chat app/api/chat.py tests/test_chat.py tests/test_query_plan.py`, focused pytest, context validation, and `git diff --check` | Passed (11 focused tests; existing upstream Pydantic warning) |
| ---- | ----- | ------- | ------ |
| 2026-08-10 | Retrieval wiring | `uv run ruff check ...`, `uv run pytest -q tests/test_chat.py tests/test_retrieval.py -p no:cacheprovider`, and Alembic upgrade (from `backend`) | Passed (25 focused tests; warnings only) |
| 2026-08-08 | 8 | `uv run ruff check app tests alembic` and `uv run pytest -q -p no:cacheprovider` (from `backend`) | Passed (106 tests; upstream/local-adapter warnings only) |
| 2026-08-08 | 8 | `python scripts/ai-context/validate-context.py` and `git diff --check` | Passed |
| 2026-08-08 | 8 | `corepack pnpm test -- ASystemMap.test.tsx`, `corepack pnpm build`, and `corepack pnpm lint` (from `frontend`) | Passed (6 tests; bundle-size advisory only) |
| 2026-08-08 | 5-8 | `uv run ruff check app tests alembic`, `uv run pytest -q -p no:cacheprovider`, in-memory Alembic upgrade, and `uv lock --check --offline` (from `backend`) | Passed (112 tests; upstream/local-adapter warnings only) |
| 2026-08-08 | 2 | `corepack pnpm test`, `corepack pnpm build`, and `corepack pnpm lint` (from `frontend`) | Passed (6 tests; bundle-size advisory only) |
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
| 2026-08-04 | 10 | `uv run ruff check app tests alembic` and `uv run pytest -q -p no:cacheprovider` (from `backend`) | Passed (93 tests; upstream/local-adapter warnings only) |
| 2026-08-04 | 10 | Fresh in-memory SQLite Alembic migration | Passed |
| 2026-08-04 | 10 | Frontend unit/build/lint/Playwright suite | Passed (6 unit tests, 2 E2E tests; bundle-size advisory only) |
| 2026-08-04 | 10 | Live Compose health, GraphRAG image-boundary, OpenAPI client, context, and license checks | Passed; backend/SQLite/Redis/Qdrant/worker healthy; GraphRAG worker-only |
| 2026-08-03 | 10 | `uv run ruff check app tests alembic && uv run pytest -q -p no:cacheprovider` (from `backend`) | Passed (77 tests; upstream/local-adapter warnings only) |
| 2026-08-03 | 10 | `CORTEX_DATABASE_URL=sqlite:///:memory: uv run alembic -c alembic.ini upgrade head` (from `backend`) | Passed |
| 2026-08-03 | 10 | `corepack pnpm test && corepack pnpm build && corepack pnpm lint` (from `frontend`) | Passed (5 tests; bundle-size advisory only) |
| 2026-08-03 | 10 | `docker compose -f infrastructure/docker-compose.yml up -d --no-build` and live health checks | Passed; frontend HTTP 200 and backend/SQLite/Redis/Qdrant/worker healthy |
| 2026-08-03 | 10 | `docker compose -f infrastructure/docker-compose.yml restart worker` | Passed; worker restarted and backend remained healthy |
| 2026-08-03 | 9 | `uv run pytest -q tests/test_settings.py tests/test_uploads.py tests/test_metadata.py tests/test_health.py tests/test_migrations.py` (from `backend`) | Passed (13 tests) |
| 2026-08-03 | 9 | `uv run ruff check app/core/config.py app/core/settings_service.py app/api/settings.py app/api/health.py app/chat/execution.py tests/test_settings.py` (from `backend`) | Passed |
| 2026-08-03 | 9 | `corepack pnpm build && corepack pnpm lint` (from `frontend`) | Passed (bundle-size advisory only) |
| 2026-08-03 | 7 | context validation and freshness checks | Passed |
| 2026-08-03 | 7 | focused workflow, LlamaIndex, API, and migration validation | Passed (9 tests; upstream Pydantic warnings only) |
| 2026-08-03 | 7 | `corepack pnpm build && corepack pnpm lint` (from `frontend`) | Passed (bundle-size advisory only) |

## High-risk boundary status

- [x] GraphRAG–Qdrant adapter validated
- [x] SQLite concurrency validated
- [x] OpenAPI client generation validated
- [x] Crash recovery validated
- [x] Upload security validated
- [x] Orphan reconciliation validated
- [x] 5,000-file performance baseline documented
- [x] Third-party license notices complete

## Setup, model, and cost-control status

- [x] First-run setup wizard complete
- [x] Secure secret storage complete
- [x] Default model profile seeded
- [x] OpenAI cost accounting complete
- [x] Budget controls complete
- [x] GraphRAG cost controls complete
- [x] Windows compatibility validated
- [x] Evaluation fixture schema validated

## Multilingual embedding status

- [x] qwen3-embedding:0.6b default configured
- [x] Ollama embedding health check complete
- [x] Turkish retrieval smoke tests complete
- [x] Cross-lingual retrieval smoke tests complete
- [x] Embedding configuration migration/reindex validated
- [x] Qdrant dimension safeguards validated
