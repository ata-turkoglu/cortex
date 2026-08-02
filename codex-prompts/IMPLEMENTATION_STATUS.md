# Cortex Implementation Status

Codex must keep this file updated.

## Overall

- [x] Phase 1 — Repository and AI context
- [x] Phase 2 — Frontend foundation
- [x] Phase 3 — Backend foundation
- [x] Phase 4 — Database and workspace
- [x] Phase 5 — Document ingestion
- [ ] Phase 6 — Retrieval and GraphRAG
- [ ] Phase 7 — Jobs, workflows, and monitoring
- [ ] Phase 8 — Chat and query
- [ ] Phase 9 — Settings and system map
- [ ] Phase 10 — Validation and hardening

## Current phase

- Phase: Phase 5 — Document ingestion
- Status: Complete
- Started: 2026-08-02
- Last updated: 2026-08-02

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

## In progress

- No active work in Phase 5. Deferred execution, provider integration, and hardening work is
  tracked in Phases 7, 9, and 10.

- Deferred by user decision: production OpenAI/Anthropic request adapters and automatic provider-reported token counting. See `docs/FUTURE_BACKLOG.md`.

## Blocking issues

- None yet.

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

## High-risk boundary status

- [ ] GraphRAG–Qdrant adapter validated
- [ ] SQLite concurrency validated
- [ ] OpenAPI client generation validated
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
