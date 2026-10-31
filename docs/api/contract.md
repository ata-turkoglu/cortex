# API Contract

## Production V2 chat

Production chat retains the existing external response schema while executing V2 only. A chat
request requires a validated workspace runtime activation, snapshots its exact workspace,
generation, and embedding configuration once, and returns grounded citations only after immutable
manifest validation. Unsupported responses contain no citations; production never falls back to
V1 orchestration.

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
accepts `automatic`, `document_search`, or `deep_analysis` for compatibility; Query V2 plans from
the question alone, so the value does not change execution and the chat UI always sends
`automatic`. The endpoint persists route/debug state in a query run, and returns an evidence-backed assistant message. Citations carry document,
document-version, and chunk IDs; unsupported answers contain no citations. `GET /query-runs/{id}`
returns routes, reason, confidence, answer state, latency, persisted token/cost counters, and
safe debug fields for the validated query plan and expanded retrieval queries. It never returns
provider secrets or hidden reasoning. Production V2 retrieval performs generation-bound dense and sparse reads, RRF fusion, trusted-source
reconciliation, and AnswerEngine rendering. Structured list/count/group/rank/compare plans run
against the SQLite canonical projection when it is operational and report query-scoped
completeness; canonical-graph plans are rejected fail-closed, and GraphRAG plans run only when their
generation artifacts are ready (see `docs/architecture/query-answer-pipeline.md`).
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

Query V2 canonical curation is workspace-scoped under
`/workspaces/{workspace_id}/knowledge`. `GET /entities`,
`GET /readiness`,
`GET /entities/{entity_id}/evidence`, and `GET /identity-history` expose canonical identities,
their exact source spans, and lossless decision history. Alias add/remove, entity merge, and entity
split are explicit POST commands. Every mutation requires a user reason; merge/split carry selected
evidence IDs, split must partition every active mention exactly once, and alias removal creates a
tombstone rather than deleting history. These endpoints operate only on the Neo4j canonical layer;
they do not promote GraphRAG extracted artifacts automatically.

The separate SQLite identity-review endpoints are under `/identity-curation`. The unresolved queue
is prioritised to population-affecting evidence, but a reviewed decision may target any exact
workspace-scoped Person mention with an automatic decision. `LINK_TO_EXISTING` requires an explicit
opaque canonical Person ID; `KEEP_UNRESOLVED` has no target. Both actions are append-only,
evidence-location keyed, and take effect when a fresh candidate generation processes the same
evidence; they never create a name-based global alias rule or mutate the active generation in place.
The readiness response lists active, building, failed, and superseded generations with their
workflow run, source fingerprint, failure summary, and all mandatory stage fingerprints/metrics.

The generated frontend OpenAPI schema includes Chat and canonical-knowledge curation models.
Feature code consumes those generated component types through the Cortex API-client boundary.

`GET /settings/budgets` reports daily and monthly soft-budget consumption from recorded usage
events (`spent_usd`, `budget_usd`, `percent`, `state`, `unpriced_calls`); enforcement is
`warn_only` (see `docs/architecture/usage-accounting.md`). `PUT /settings` rejects a conversation
summary assignment other than OpenAI, enabling `answer_synthesis_enabled` with a non-OpenAI
answer provider, and an `embedding_concurrency` outside 1–8. Unknown settings keys are ignored.

`GET /settings` and `PUT /settings` expose the persistent, global-only operational
configuration. Secrets and connection locations remain environment/credential-store owned.
Updates are Pydantic validated and model assignments are checked against provider
capabilities. Changing chunking or embedding settings marks every workspace index as
`reindex_required` and its GraphRAG projection as `stale`.
Query V2 adds global simple, standard, and complex semantic-planner provider/model assignments,
a bounded repair count, an escalation switch, and a confidence threshold. These settings configure the active V2 semantic planner; they do not introduce a V1 fallback.
Each planner tier is validated independently on save. The current production adapter requires a
configured OpenAI model listed as chat-capable because it uses the Responses strict JSON-Schema
contract; unsupported provider/model pairs are rejected with a tier-specific `422` response.
GET /api/v1/workspaces/{workspace_id}/knowledge/cutover returns the workspace's sole live runtime
version/generation pointer, source/evaluation/curation fingerprints, activation time, and bounded
immutable attempt history. POST /api/v1/workspaces/{workspace_id}/knowledge/cutover accepts only a
candidate generation ID; it derives corpus, Neo4j-curation, configuration, manifest, dense-scope,
and generation-owned BM25 checks on the server. It never accepts a client-authored readiness payload
and atomically records a rejected or activated attempt.
GraphRAG exposes separate local Ollama or OpenAI API provider/model assignments for extraction,
claims, community reports, and Local, Global, and DRIFT query methods. Entity and relationship
extraction share Microsoft GraphRAG's single upstream `extract_graph` stage. Changing any of
these assignments marks the GraphRAG projection stale without invalidating dense or sparse
retrieval indexes.

`GET /health` returns both a service map and component list, including authenticated Neo4j
connectivity. The system map renders these live states; an unavailable optional provider is shown
as unavailable rather than healthy, while missing/unreachable Neo4j degrades the V2 service map.

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
