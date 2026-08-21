# Durable Workflows

LlamaIndex Workflows define ingestion, querying, reindexing, deletion, and maintenance;
Dramatiq and Redis execute background work while SQLite persists state. REST commands jobs
and SSE publishes progress. Workspace locks protect unsafe graph, reindex, and delete
operations. Workflow definitions are versioned in code and not user-editable in V1.

Phase 7 persists queued/running/completed workflow runs, individual step checkpoints, and
append-only events in SQLite. The REST API commits a newly created or retried run before
publishing its Dramatiq message, so worker connections can immediately claim it. Dramatiq runs
the durable state machine through Redis; a Redis outage leaves commands queued for a later retry
rather than losing their state. The workflow API creates, inspects, cancels, and retries runs;
its SSE endpoint accepts the last event ID for reconnect. Index, graph, and deletion operations
acquire a workspace-scoped lock. Each worker applies persisted global settings before it resolves
providers or models, so the user-selected embedding and GraphRAG assignments apply equally to
API and worker execution. Startup
marks stale running runs `interrupted` with recovery state `restart_detected`.

Every post-commit dispatch also publishes one delayed idempotent fallback delivery. This covers a
transient consumer gap after Redis accepts the first message: the worker claims only runs still
in `queued` state, so a run already claimed by the first delivery is skipped safely.

Retry resumes from the failed checkpoint when one exists. If an external indexing adapter fails
before recording its first checkpoint, retry instead starts from the first incomplete step.

Stage limits are global V1 settings: ingestion, dense reindex, GraphRAG reindex, and deletion
have independent worker concurrency caps. A run that exceeds its cap remains queued and emits a
`blocked` event. When an ingestion run completes, the worker re-publishes the oldest queued
ingestion runs up to that limit, so a queued batch advances as slots open. Ingestion also holds
the workspace-scoped `index` lock: two workspaces can use the global capacity, but one workspace
is rebuilt by only one ingestion run at a time. Completed runs are soft-deleted by the retention
actor after the configured number of days.

A GraphRAG reindex performs real worker-owned work, outside a SQLite transaction: it snapshots
the workspace documents, materializes GraphRAG inputs, runs GraphRAG extraction and the NetworkX
projection, atomically synchronizes the workspace/generation extracted layer to Neo4j at the
`neo4j_sync` checkpoint, then mirrors entity/report/text-unit artifacts to Qdrant. Each stage writes
its checkpoint only after that stage completes; failures—including Neo4j unavailability—leave the
graph state `stale` and the workflow `failed` rather than reporting a synthetic completion.

Upload ingestion v3 commits its workflow run and initial checkpoints (`parse`, `normalize`,
logical-document detection, `chunk`, and `index`) before dispatching to Dramatiq. Logical-document
detection is completed synchronously before chunks are written, while the durable step model keeps
the same safe transaction boundary. A worker therefore never observes a queued
run without its durable state; queued runs created by an earlier version are backfilled before
execution.

For DOCX input, normalization preserves Word heading levels and makes every Word Heading 2 an
exact Markdown `##` heading. Logical-document detection splits only on these level-2 headings;
heading text is opaque and no archive-code prefix is recognized. Metadata is persisted for each
logical document before its independent chunk set is created.

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
Entity-document lookup remains inside those same `route`, `retrieve`, and `synthesize` query
steps: intent detection occurs during route, unique-document grouping during retrieve, and the
concise document table during synthesize. It does not add a Processes-page workflow schema.

Chat query runs persist selector decision, confidence, fallback explanation, answer state,
latency, and token/cost fields. When a GraphRAG route cannot produce normalized
workspace-scoped evidence, the query falls back to Hybrid Search and records that fallback
rather than presenting ungrounded output.

GraphRAG fallback is now an explicit global policy and defaults off. Selected native Local,
Global, and DRIFT routes retain GraphRAG's final answer and bypass the normal synthesis actor.

GraphRAG chat uses the durable query-run record as its worker job protocol. The API commits that
record before submitting its ID to the existing Redis/Dramatiq worker, then polls bounded shared
SQLite state for the final result. The worker owns the Microsoft GraphRAG dependency and CLI;
the API image remains lightweight and dependency-safe.

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

Query V2 `knowledge_reindex` uses a specialized generation-aware Dramatiq executor. It retains one
durable run context, resumes the same candidate and completed per-chunk extraction artifacts,
mirrors all eleven workflow/generation checkpoints, and releases its index lock on every terminal
path. Activation is atomic only after source, typed knowledge, canonical graph, BM25, Qdrant, and
GraphRAG report matching readiness.

Phase 11 adds `research_runs` and `composition_runs` as independent durable state machines. A
research run checkpoints goal decomposition, multiple Query IR/physical-plan slots, reconciled
evidence packages, cross-source claims, and validation. A composition run checkpoints its outline,
each section, consistency state, and sentence-level evidence map. Planner/composer calls receive
detached snapshots between short SQLite transactions, and retries skip persisted sections.
