# V1 Cleanup Review

This record distinguishes production V2 ownership from code retained for historical evaluation,
worker compatibility, migrations, or unresolved compatibility decisions. It is not an approval to
route production chat through any listed module.

## backend/app/chat/service.py

Status: UNCERTAIN

Possible legacy responsibility:
V1 route selection, workspace-only hybrid retrieval, property aggregation, and final-answer
rendering.

Current references:
`app.evaluation.runner` imports `ask` and `create_conversation`; `app.workflows.graphrag_query`
imports internal answer/retrieval helpers for its historical worker fallback.

Why removal is not proven safe:
The historical evaluation runner and worker fallback remain importable and have tests. Rewriting or
retiring them is outside this cleanup.

Decision required:
Decide whether to retire the historical evaluation runner and V1 GraphRAG worker path, then replace
their dependencies with explicitly supported V2 test/workflow boundaries.

## backend/app/chat/router.py and backend/app/chat/query_plan.py

Status: UNCERTAIN

Possible legacy responsibility:
V1 `QueryPlan`, deterministic route selection, and LlamaIndex router compatibility.

Current references:
`app.chat.service` and historical chat/router tests.

Why removal is not proven safe:
They are reachable through the retained historical evaluation and worker-compatible V1 service, not
through production `POST /chat`.

Decision required:
Retire or port the historical runner before removal.

## backend/app/chat/execution.py

Status: KEEP_SHARED

Possible legacy responsibility:
V1 synthesis implementation.

Current references:
Worker actors import `synthesize_with_openai` and `summarize_conversation_with_openai`; production
V2 chat also queues the conversation-summary actor.

Why removal is not proven safe:
Conversation summarization remains an active background concern. It must be moved to a neutral
conversation boundary before this module can be deleted.

Decision required:
None for this cleanup; retain as shared compatibility code.

## backend/app/workflows/graphrag_query.py

Status: UNCERTAIN

Possible legacy responsibility:
Worker-owned native GraphRAG final-answer path and opt-in fallback to V1 hybrid retrieval.

Current references:
Worker actor and historical chat tests.

Why removal is not proven safe:
The worker and settings schema still expose this path. It is not reachable from V2 `POST /chat`, but
removing it changes background behavior and persisted settings compatibility.

Decision required:
Explicitly deprecate the worker command/settings and migrate existing persisted configuration.

## backend/app/retrieval/runtime.py and backend/app/aggregation/property.py

Status: UNCERTAIN

Possible legacy responsibility:
Workspace-only retrieval runtime and property-only exhaustive aggregation.

Current references:
Historical V1 service, evaluation runner, and GraphRAG fallback.

Why removal is not proven safe:
They are not V2 production dependencies, but retained callers remain. Stable V2 generation-bound
retrieval adapters must not be altered as part of deleting these modules.

Decision required:
Retire callers first; then delete the wrappers in a separately validated change.

## backend/alembic/versions/0010_logical_documents.py

Status: MIGRATION_ONLY

Possible legacy responsibility:
Backfills legacy logical-document identifiers for persisted workspaces.

Current references:
Alembic migration history.

Why removal is not proven safe:
Applied migration history is durable compatibility data.

Decision required:
None; retain permanently.
