# Durable Workflows

LlamaIndex Workflows define ingestion, querying, reindexing, deletion, and maintenance;
Dramatiq and Redis execute background work while SQLite persists state. REST commands jobs
and SSE publishes progress. Workspace locks protect unsafe graph, reindex, and delete
operations. Workflow definitions are versioned in code and not user-editable in V1.

Phase 7 persists queued/running/completed workflow runs, individual step checkpoints, and
append-only events in SQLite. Dramatiq runs the durable state machine through Redis; a Redis
outage leaves commands queued for a later retry rather than losing their state. The workflow
API creates, inspects, cancels, and retries runs; its SSE endpoint accepts the last event ID
for reconnect. Index, graph, and deletion operations acquire a workspace-scoped lock. Startup
marks stale running runs `interrupted` with recovery state `restart_detected`.

Stage limits are global V1 settings: ingestion, dense reindex, GraphRAG reindex, and deletion
have independent worker concurrency caps. A run that exceeds its cap remains queued and emits a
`blocked` event. Completed runs are soft-deleted by the retention actor after the configured
number of days.

Document and workspace deletion commands create durable delete workflows. At their cleanup
checkpoint they idempotently tombstone the workspace-owned relational document, version, and
chunk rows. Cross-store file/vector cleanup and reconciliation remain dedicated follow-up
steps. A failed deletion queues a durable `reconcile` repair run; the backend maintenance
loop also queues one workspace-scoped orphan-reconciliation run per active workspace daily.
The persisted scan/repair checkpoints make recovery visible before external-store adapters act.

Workflow failure details are limited to a concise exception summary. Credential-like values for
API keys, tokens, passwords, and authorization headers are redacted before they are persisted
or emitted over SSE.

`app.workflows.llamaindex.IngestionWorkflow` owns the Docling-normalized Markdown to
LlamaIndex `Document` handoff and preserves workspace/version metadata. `ReindexWorkflow`
validates that reindex requests carry an explicit workspace and embedding configuration
fingerprint before specialized worker adapters run.

Query runs use separate `query_runs` and `query_step_runs` records rather than background
workflow tables. Phase 8 can therefore persist route, retrieval, and synthesis progress without
changing the job-monitoring lifecycle.

Chat query runs persist selector decision, confidence, fallback explanation, answer state,
latency, and token/cost fields. When a GraphRAG route cannot produce normalized
workspace-scoped evidence, the query falls back to Hybrid Search and records that fallback
rather than presenting ungrounded output.

`app.chat.router` owns the LlamaIndex `QueryEngineTool` catalog and the descriptions for
Hybrid, GraphRAG Local, Global, and DRIFT paths. It restricts selection to V1-approved route
sets; until provider execution is configured, the deterministic selector is the non-network
fallback for this same catalog.

After the API commits the evidence-backed response, `execute_query_synthesis` may run in the
worker. It reads a short query/evidence snapshot, performs the configured OpenAI Responses API
call outside a database transaction, and opens a separate short transaction to persist answer
text and token counters. Redis failure leaves the original grounded response intact.

The summary worker only runs after the configured conversation-memory window is exceeded. It
uses the assigned Conversation Summary model and writes the compact summary back to the
workspace-scoped conversation for subsequent provider synthesis.

Phase 10 regression coverage verifies cancellation, retry, stale-run recovery, stage blocking,
retention cleanup, deletion repair scheduling, and idempotent orphan reconciliation using the
durable SQLite state machine.
