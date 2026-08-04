# Phase 10 — Validation and Hardening

## Goal

Verify correctness, isolation, resilience, performance, and architecture compliance.

## Checklist

- [x] Create end-to-end Docker Compose test.
- [x] Verify fresh database migration.
- [x] Verify workspace isolation in SQLite.
- [x] Verify workspace isolation in Qdrant.
- [x] Verify workspace isolation in conversations.
- [x] Verify ingestion for all supported formats.
  - Include corrupt and encrypted/password-protected PDF and DOCX fixtures with structured-error assertions.
- [x] Verify duplicate and version behavior.
- [x] Verify background processing across navigation.
- [x] Verify SSE reconnect.
- [x] Verify cancellation.
- [x] Verify retry from failed step.
- [x] Verify GraphRAG deferred update.
- [x] Verify Hybrid Search fallback.
- [x] Verify Local, Global, and DRIFT routes.
- [x] Verify citations and technical details.
- [x] Verify traceback redaction.
- [x] Verify no direct PrimeReact imports outside UI layer.
- [x] Verify no direct lucide-react imports outside icon layer.
- [x] Verify React Flow abstractions.
- [x] Verify settings-driven thresholds.
- [x] Verify AI context validation scripts.
- [x] Create evaluation fixtures and baseline tests.
- [x] Run frontend lint/type/test/build.
- [x] Run backend lint/type/test.
- [x] Run integration tests.
- [x] Document all commands.
- [x] Resolve all blocking issues.
- [x] Mark all implementation-status phases complete.
- [x] Update `IMPLEMENTATION_STATUS.md`.

## Acceptance criteria

- [x] All checkboxes in all phases are complete.
- [x] No blocking issue remains.
- [x] Docker Compose starts successfully.
- [x] Core workflows work end to end.
- [x] Architecture decisions are documented and enforced.

## Additional checklist

- [x] Verify exact dependency and Docker version pinning.
- [x] Verify generated frontend API client matches current OpenAPI schema.
- [x] Verify standard error envelope across endpoints.
- [x] Verify SQLite WAL, foreign keys, busy timeout, and retry behavior.
- [x] Verify upload-size, extension, MIME, path-traversal, corrupt-file, and encrypted-file handling.
- [x] Verify GraphRAG–Qdrant adapter isolation and query behavior.
- [x] Run 5,000-file scale-oriented benchmark or representative synthetic benchmark.
- [x] Verify server-side pagination and list virtualization.
- [x] Verify crash recovery after forced backend/worker restart.
- [x] Verify graceful shutdown.
- [x] Verify partial deletion cleanup and orphan reconciliation.
- [x] Verify license checks and `THIRD_PARTY_NOTICES.md`.
- [x] Document measured performance baselines.

## Additional checklist — final model and environment validation

- [x] Verify all default OpenAI assignments use `gpt-5.6-luna`.
- [x] Verify default embedding is `qwen3-embedding:0.6b`.
- [x] Verify no Ollama chat model is required for initial setup.
- [x] Verify API keys are not stored in plaintext SQLite.
- [x] Verify API keys are redacted from logs, traces, SSE, and support details.
- [x] Verify Batch API use for eligible configured jobs.
- [x] Verify token and estimated-cost accounting.
- [x] Verify soft-budget warnings and pause behavior.
- [x] Verify GraphRAG automation is Off by default.
- [x] Verify Windows paths with spaces and Turkish characters.
- [x] Verify `host.docker.internal` Ollama detection.
- [x] Verify Vitest, Testing Library, Playwright, pytest, integration, and contract tests.
- [x] Validate evaluation fixture schema and starter fixtures.

## Additional checklist — embedding validation

- [x] Verify `qwen3-embedding:0.6b` is the default embedding model.
- [x] Verify the application does not confuse it with the Qwen3 chat model.
- [x] Verify Turkish semantic retrieval.
- [x] Verify cross-lingual retrieval.
- [x] Verify embedding dimension mismatch is blocked.
- [x] Verify embedding model/configuration changes mark workspaces outdated.
- [x] Verify full dense reindex completes safely.
- [x] Verify no mixed vector configuration remains active.
- [x] Verify adaptive batches recover from memory/time-out failures.
