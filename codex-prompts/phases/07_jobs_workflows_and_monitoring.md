# Phase 7 — Jobs, Workflows, and Monitoring

## Goal

Implement durable background execution, workflow state, SSE progress, cancellation, retry, concurrency, locks, and React Flow live monitoring.

## Checklist

- [x] Implement LlamaIndex Workflows for ingestion.
  - Include the Docling-to-LlamaIndex document/node handoff and document lifecycle transitions.
- [x] Implement LlamaIndex Workflows for reindexing.
- [x] Implement workflow definitions as versioned code.
- [x] Persist workflow runs and step runs.
- [x] Persist query runs separately.
- [x] Implement workflow events.
- [x] Implement Dramatiq execution.
- [x] Implement Redis queue/broker.
- [x] Implement REST commands for create, cancel, retry, and inspect.
- [x] Implement SSE job stream.
- [x] Implement reconnect and state restoration.
- [x] Implement safe cancellation.
- [x] Implement retry from failed step.
- [x] Enforce idempotent steps.
  - Ensure ingestion resumes safely from a persisted parsing, normalization, chunking, or indexing checkpoint.
- [x] Implement workspace lock types.
- [x] Implement stage-specific concurrency limits from Settings.
- [x] Implement retention cleanup from Settings.
- [x] Implement global background progress aggregation.
- [x] Implement React Flow workflow view.
- [x] Implement grouped workflow nodes.
- [x] Implement node details panel.
- [x] Implement technical error details dialog.
  - Surface sanitized parsing failures without exposing source content or secrets.
- [x] Redact secrets in traceback details.
- [x] Add navigation-survival tests.
- [x] Update `IMPLEMENTATION_STATUS.md`.

## Acceptance criteria

- [x] Jobs continue after leaving the page.
- [x] Returning to the page shows current progress.
- [x] SSE reconnect restores state.
- [x] Retry resumes at the failed step.
- [x] Unsafe concurrent workspace operations are blocked.

## Additional checklist

- [x] Detect stale running jobs on startup.
- [x] Mark stale jobs interrupted or resume from safe checkpoints.
- [x] Display recovery actions in the process UI.
- [ ] Implement graceful worker shutdown.
  - Deferred to `docs/FUTURE_BACKLOG.md`: needs a real Redis/Dramatiq process termination test.
- [x] Implement idempotent document deletion workflow.
- [x] Implement idempotent workspace deletion workflow.
- [ ] Implement repair/reconciliation jobs for partial cleanup.
  - Deferred to `docs/FUTURE_BACKLOG.md`: requires live Qdrant, GraphRAG, and host-file stores.
- [ ] Implement periodic orphan reconciliation.
  - Deferred to `docs/FUTURE_BACKLOG.md`: scheduler ownership/cadence is operationally undefined.
- [x] Add crash/restart recovery tests.
- [ ] Add partial-cleanup recovery tests.
  - Deferred to `docs/FUTURE_BACKLOG.md`: requires the live cross-store failure fixture above.
