# API Contract

FastAPI OpenAPI is canonical. All REST and SSE request/response models use Pydantic; the
frontend consumes generated TypeScript client types rather than manually duplicated DTOs.
Errors use `code`, `message`, `correlation_id`, `details_available`, and optional sanitized
`details`. Contract or schema changes require regenerating the client and updating this
document and its tests.

Workspace CRUD is exposed at `/api/v1/workspaces`. Creation atomically seeds resource and
index-state records. Deletion is a soft delete; cross-store cleanup is deferred to the
idempotent deletion workflow.

`GET /api/v1/overview` provides aggregate dashboard counts and recent documents without
exposing source contents. Workspace-scoped catalogue views use
`GET /workspaces/{workspace_id}/overview`, `GET /workspaces/{workspace_id}/documents`, and
`GET /workspaces/{workspace_id}/documents/{document_id}`. The detail endpoint returns the
normalized source only for its owning workspace. When its normalized file is unavailable,
it returns the same persisted logical-document Markdown in ordinal order; document deletion
remains the existing durable workflow command.

Workflow commands are exposed under `/api/v1/workflows`: `POST /` creates a durable run,
`GET /` and `GET /{id}` restore state, `POST /{id}/cancel` requests safe-boundary cancellation,
and `POST /{id}/retry` resumes from the failed step or re-dispatches an unchanged queued run
after a transient broker/worker failure. `GET /{id}/events` is an SSE stream with
event IDs for reconnect. Workflow responses include persisted steps and recovery state.
`GET /{id}/events/history` exposes the persisted, already-sanitized event history for process
diagnostics; it does not return source document content or unredacted exceptions.
`DELETE /history` soft-deletes all terminal workflow runs for the process-history cleanup action;
active queued, running, and cancelling runs are preserved. The response contains the number of
hidden runs.
Workflow responses include the ingestion source filename when the run belongs to a document
version, so operational screens can identify the affected file. Document list/detail responses
also include the latest ingestion state for the active version (`queued`, `running`, `completed`,
`failed`, and other terminal states).

`DELETE /api/v1/workspaces/{workspace_id}` queues a workspace-deletion workflow after the
workspace is marked deleting. `DELETE /api/v1/workspaces/{workspace_id}/documents/{document_id}`
returns `202` with its durable workflow run ID.

Chat is scoped beneath `/api/v1/workspaces/{workspace_id}`. Conversations can be soft-deleted
with `DELETE /conversations/{id}` within their owning workspace. Conversations, messages, and
query-debug lookups are all filtered by that workspace. `POST /conversations/{id}/messages`
accepts `automatic`, `document_search`, or `deep_analysis`, persists route/debug state in a
query run, and returns an evidence-backed assistant message. Citations carry document,
document-version, and chunk IDs; unsupported answers contain no citations. `GET /query-runs/{id}`
returns routes, reason, confidence, answer state, latency, persisted token/cost counters, and
safe debug fields for the validated query plan and expanded retrieval queries. It never returns
provider secrets or hidden reasoning. Normal Hybrid Search responds with the direct evidence
fallback and, when OpenAI is configured, synchronously replaces it with grounded synthesis after
the evidence snapshot is committed.
`PATCH /conversations/{conversation_id}/messages/{message_id}` only permits editing a user
message in its owning workspace/conversation. `GET /sources/{chunk_id}` returns source content
and document-version metadata only when the chunk belongs to the requested workspace.

Document-list language in Turkish or English is planned as `entity_document_lookup`; its answer
contains one row and one citation per unique document, plus page and document type when available.

`GET /workspaces/{workspace_id}/ingestion-diagnostics/{source_document_id}` returns the active
source DOCX, its logical documents, inherited chunk/page metadata, matching GraphRAG entity and
text-unit nodes, and—when `query` is supplied—the logical documents returned by retrieval. The
diagnostic is read-only and workspace-scoped.

`GET /workspaces/{workspace_id}/graph` returns a bounded, read-only projection of that
workspace's canonical GraphRAG entity and relationship artifacts for the graph explorer. It
never reads another workspace's graph root and limits the response to 150 entities and 300
relationships.

The generated frontend OpenAPI schema includes the Chat request, conversation, message,
citation, and query-debug models. Chat feature code consumes those generated component types
through the Cortex API-client boundary.

`GET /settings/budgets` exposes safe query defaults: Query Expansion and automatic
quality escalation are disabled unless global configuration explicitly enables them.

`GET /settings` and `PUT /settings` expose the persistent, global-only operational
configuration. Secrets and connection locations remain environment/credential-store owned.
Updates are Pydantic validated and model assignments are checked against provider
capabilities. Changing chunking or embedding settings marks every workspace index as
`reindex_required` and its GraphRAG projection as `stale`.
GraphRAG exposes separate local Ollama or OpenAI API provider/model assignments for extraction,
claims, community reports, and Local, Global, and DRIFT query methods. Entity and relationship
extraction share Microsoft GraphRAG's single upstream `extract_graph` stage. Changing any of
these assignments marks the GraphRAG projection stale without invalidating dense or sparse
retrieval indexes.

`GET /health` returns both a service map and component list. The system map renders these
live states; an unavailable optional provider is shown as unavailable rather than healthy.

`POST /settings/providers/{provider}/validate` stores a supplied credential in the OS
credential store and records only safe validation state. In Docker, when the host OS
credential store is unavailable, credentials are encrypted in the mounted `/data/secrets`
fallback store; environment variables remain supported for non-interactive deployments.
`GET /settings/providers` queries the configured OpenAI credential against `/v1/models` and
exposes only the accessible chat and embedding model IDs to the settings UI.
`POST /settings/embedding/health`
tests the configured Ollama embedding adapter and reports its model and vector dimension.
`POST /settings/setup/complete` records completion of the global first-run wizard.
`POST /settings/ollama/models/pull` starts an explicitly user-requested Ollama download and
returns an operation ID; `GET /settings/ollama/models/pull/{operation_id}` reports its streamed
progress. Cortex never pulls a model automatically.
`GET /settings/ollama/catalog` exposes selectable entries from the official Ollama library,
with a small local fallback catalogue when the library is unavailable.
