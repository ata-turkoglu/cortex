# Phase 10 — Validation and Hardening

## Goal

Verify correctness, isolation, resilience, performance, and architecture compliance.

## Checklist

- [ ] Create end-to-end Docker Compose test.
- [ ] Verify fresh database migration.
- [ ] Verify workspace isolation in SQLite.
- [ ] Verify workspace isolation in Qdrant.
- [ ] Verify workspace isolation in conversations.
- [ ] Verify ingestion for all supported formats.
- [ ] Verify duplicate and version behavior.
- [ ] Verify background processing across navigation.
- [ ] Verify SSE reconnect.
- [ ] Verify cancellation.
- [ ] Verify retry from failed step.
- [ ] Verify GraphRAG deferred update.
- [ ] Verify Hybrid Search fallback.
- [ ] Verify Local, Global, and DRIFT routes.
- [ ] Verify citations and technical details.
- [ ] Verify traceback redaction.
- [ ] Verify no direct PrimeReact imports outside UI layer.
- [ ] Verify no direct lucide-react imports outside icon layer.
- [ ] Verify React Flow abstractions.
- [ ] Verify settings-driven thresholds.
- [ ] Verify AI context validation scripts.
- [ ] Create evaluation fixtures and baseline tests.
- [ ] Run frontend lint/type/test/build.
- [ ] Run backend lint/type/test.
- [ ] Run integration tests.
- [ ] Document all commands.
- [ ] Resolve all blocking issues.
- [ ] Mark all implementation-status phases complete.
- [ ] Update `IMPLEMENTATION_STATUS.md`.

## Acceptance criteria

- [ ] All checkboxes in all phases are complete.
- [ ] No blocking issue remains.
- [ ] Docker Compose starts successfully.
- [ ] Core workflows work end to end.
- [ ] Architecture decisions are documented and enforced.

## Additional checklist

- [ ] Verify exact dependency and Docker version pinning.
- [ ] Verify generated frontend API client matches current OpenAPI schema.
- [ ] Verify standard error envelope across endpoints.
- [ ] Verify SQLite WAL, foreign keys, busy timeout, and retry behavior.
- [ ] Verify upload-size, extension, MIME, path-traversal, corrupt-file, and encrypted-file handling.
- [ ] Verify GraphRAG–Qdrant adapter isolation and query behavior.
- [ ] Run 5,000-file scale-oriented benchmark or representative synthetic benchmark.
- [ ] Verify server-side pagination and list virtualization.
- [ ] Verify crash recovery after forced backend/worker restart.
- [ ] Verify graceful shutdown.
- [ ] Verify partial deletion cleanup and orphan reconciliation.
- [ ] Verify license checks and `THIRD_PARTY_NOTICES.md`.
- [ ] Document measured performance baselines.

## Additional checklist — final model and environment validation

- [ ] Verify all default OpenAI assignments use `gpt-5.6-luna`.
- [ ] Verify default embedding is `qwen3-embedding:0.6b`.
- [ ] Verify no Ollama chat model is required for initial setup.
- [ ] Verify API keys are not stored in plaintext SQLite.
- [ ] Verify API keys are redacted from logs, traces, SSE, and support details.
- [ ] Verify Batch API use for eligible configured jobs.
- [ ] Verify token and estimated-cost accounting.
- [ ] Verify soft-budget warnings and pause behavior.
- [ ] Verify GraphRAG automation is Off by default.
- [ ] Verify Windows paths with spaces and Turkish characters.
- [ ] Verify `host.docker.internal` Ollama detection.
- [ ] Verify Vitest, Testing Library, Playwright, pytest, integration, and contract tests.
- [ ] Validate evaluation fixture schema and starter fixtures.

## Additional checklist — embedding validation

- [ ] Verify `qwen3-embedding:0.6b` is the default embedding model.
- [ ] Verify the application does not confuse it with the Qwen3 chat model.
- [ ] Verify Turkish semantic retrieval.
- [ ] Verify cross-lingual retrieval.
- [ ] Verify embedding dimension mismatch is blocked.
- [ ] Verify embedding model/configuration changes mark workspaces outdated.
- [ ] Verify full dense reindex completes safely.
- [ ] Verify no mixed vector configuration remains active.
- [ ] Verify adaptive batches recover from memory/time-out failures.
