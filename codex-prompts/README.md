# Cortex Codex Build Pack

This package contains the implementation prompts for building **Cortex**, a local, single-user knowledge workspace platform.

## How to use

1. Extract this package into the root of the repository you want Codex to build.
2. Open `MASTER_PROMPT.md` in VS Code.
3. Give that file to Codex and instruct it to execute the phases in order.
4. Codex must update every checkbox from `[ ]` to `[x]` only after the item is actually completed and validated.
5. Codex must keep `IMPLEMENTATION_STATUS.md` current throughout the work.
6. Codex must not skip phases, silently change architecture decisions, or mark incomplete work as complete.

## Recommended execution order

1. `MASTER_PROMPT.md`
2. `phases/01_repository_and_ai_context.md`
3. `phases/02_frontend_foundation.md`
4. `phases/03_backend_foundation.md`
5. `phases/04_database_and_workspace.md`
6. `phases/05_document_ingestion.md`
7. `phases/06_retrieval_and_graphrag.md`
8. `phases/07_jobs_workflows_and_monitoring.md`
9. `phases/08_chat_and_query.md`
10. `phases/09_settings_and_system_map.md`
11. `phases/10_validation_and_hardening.md`

## Important

The architecture decisions in `docs/DECISIONS.md` are binding for V1.
Future-version ideas are listed in `docs/FUTURE_BACKLOG.md` and must not be implemented unless explicitly requested.

## Added in v2 of this build pack

- Exact dependency and Docker version pinning
- Complete V1 page inventory
- Standard API error contract
- OpenAPI-generated TypeScript client
- SQLite WAL/concurrency policy
- Upload and path-security requirements
- Dedicated GraphRAG–Qdrant adapter boundary
- 5,000-file performance targets
- Explicit no-file-watcher V1 behavior
- Graceful shutdown and startup recovery
- Deletion reconciliation and orphan cleanup
- Third-party license tracking

## Added in v3

- Cost-controlled OpenAI production defaults
- `gpt-5.6-luna` default model profile
- `text-embedding-3-small` default embeddings
- Ollama as optional experimental/offline provider
- First-run setup wizard
- OS-backed secret-store abstraction
- Token and cost tracking
- Daily/monthly soft budgets
- Batch API guidance for offline workloads
- GraphRAG cost controls
- Windows 11/Docker Desktop/WSL2 compatibility requirements
- Shared Ollama connectivity with the existing KnowledgeOS Docker stack
- Evaluation fixture schema
- Vitest, Testing Library, Playwright, and pytest strategy

## Added in v4

- Ollama `qwen3-embedding:0.6b` as the multilingual local embedding default
- Optional `bge-m3:567m` multilingual alternative
- Embedding adapter boundary
- Turkish and cross-lingual retrieval checks
- Embedding dimension/configuration invariants
- Mandatory dense reindex after embedding changes
- Adaptive local embedding batch behavior
