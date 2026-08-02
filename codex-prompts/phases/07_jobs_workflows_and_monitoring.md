# Phase 7 — Jobs, Workflows, and Monitoring

## Goal

Implement durable background execution, workflow state, SSE progress, cancellation, retry, concurrency, locks, and React Flow live monitoring.

## Checklist

- [ ] Implement LlamaIndex Workflows for ingestion.
- [ ] Implement LlamaIndex Workflows for reindexing.
- [ ] Implement workflow definitions as versioned code.
- [ ] Persist workflow runs and step runs.
- [ ] Persist query runs separately.
- [ ] Implement workflow events.
- [ ] Implement Dramatiq execution.
- [ ] Implement Redis queue/broker.
- [ ] Implement REST commands for create, cancel, retry, and inspect.
- [ ] Implement SSE job stream.
- [ ] Implement reconnect and state restoration.
- [ ] Implement safe cancellation.
- [ ] Implement retry from failed step.
- [ ] Enforce idempotent steps.
- [ ] Implement workspace lock types.
- [ ] Implement stage-specific concurrency limits from Settings.
- [ ] Implement retention cleanup from Settings.
- [ ] Implement global background progress aggregation.
- [ ] Implement React Flow workflow dialog.
- [ ] Implement grouped workflow nodes.
- [ ] Implement node details panel.
- [ ] Implement technical error details dialog.
- [ ] Redact secrets in traceback details.
- [ ] Add navigation-survival tests.
- [ ] Update `IMPLEMENTATION_STATUS.md`.

## Acceptance criteria

- [ ] Jobs continue after leaving the page.
- [ ] Returning to the page shows current progress.
- [ ] SSE reconnect restores state.
- [ ] Retry resumes at the failed step.
- [ ] Unsafe concurrent workspace operations are blocked.

## Additional checklist

- [ ] Detect stale running jobs on startup.
- [ ] Mark stale jobs interrupted or resume from safe checkpoints.
- [ ] Display recovery actions in the process UI.
- [ ] Implement graceful worker shutdown.
- [ ] Implement idempotent document deletion workflow.
- [ ] Implement idempotent workspace deletion workflow.
- [ ] Implement repair/reconciliation jobs for partial cleanup.
- [ ] Implement periodic orphan reconciliation.
- [ ] Add crash/restart recovery tests.
- [ ] Add partial-cleanup recovery tests.
