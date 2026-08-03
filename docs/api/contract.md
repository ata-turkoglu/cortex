# API Contract

FastAPI OpenAPI is canonical. All REST and SSE request/response models use Pydantic; the
frontend consumes generated TypeScript client types rather than manually duplicated DTOs.
Errors use `code`, `message`, `correlation_id`, `details_available`, and optional sanitized
`details`. Contract or schema changes require regenerating the client and updating this
document and its tests.

Workspace CRUD is exposed at `/api/v1/workspaces`. Creation atomically seeds resource and
index-state records. Deletion is a soft delete; cross-store cleanup is deferred to the
idempotent deletion workflow.

Workflow commands are exposed under `/api/v1/workflows`: `POST /` creates a durable run,
`GET /` and `GET /{id}` restore state, `POST /{id}/cancel` requests safe-boundary cancellation,
and `POST /{id}/retry` resumes from the failed step. `GET /{id}/events` is an SSE stream with
event IDs for reconnect. Workflow responses include persisted steps and recovery state.
`GET /{id}/events/history` exposes the persisted, already-sanitized event history for process
diagnostics; it does not return source document content or unredacted exceptions.

`DELETE /api/v1/workspaces/{workspace_id}` queues a workspace-deletion workflow after the
workspace is marked deleting. `DELETE /api/v1/workspaces/{workspace_id}/documents/{document_id}`
returns `202` with its durable workflow run ID.

Chat is scoped beneath `/api/v1/workspaces/{workspace_id}`. Conversations, messages, and
query-debug lookups are all filtered by that workspace. `POST /conversations/{id}/messages`
accepts `automatic`, `document_search`, or `deep_analysis`, persists route/debug state in a
query run, and returns an evidence-backed assistant message. Citations carry document,
document-version, and chunk IDs; unsupported answers contain no citations. `GET /query-runs/{id}`
returns routes, reason, confidence, answer state, latency, and persisted token/cost counters.
`PATCH /conversations/{conversation_id}/messages/{message_id}` only permits editing a user
message in its owning workspace/conversation. `GET /sources/{chunk_id}` returns source content
and document-version metadata only when the chunk belongs to the requested workspace.

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

`GET /health` returns both a service map and component list. The system map renders these
live states; an unavailable optional provider is shown as unavailable rather than healthy.

`POST /settings/providers/{provider}/validate` stores a supplied credential in the OS
credential store and records only safe validation state. `POST /settings/embedding/health`
tests the configured Ollama embedding adapter and reports its model and vector dimension.
`POST /settings/setup/complete` records completion of the global first-run wizard.
