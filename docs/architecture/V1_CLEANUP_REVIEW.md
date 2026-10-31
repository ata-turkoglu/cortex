# V1 Cleanup Review

This record lists what was removed from the historical V1 chat stack, why removal was safe, and
what remains. Production chat is V2-only through `backend/app/query/production_chat.py`.

## Removed (2026-10-31)

| Removed | Former responsibility |
| --- | --- |
| `backend/app/chat/service.py`, `router.py`, `query_plan.py`, `evidence_selection.py` | V1 route selection, `QueryPlan`, LlamaIndex router, evidence selection, answer rendering |
| `backend/app/chat/execution.py` (synthesis parts) | V1 provider synthesis and citation finalization |
| `backend/app/aggregation/property.py` | V1 property-only exhaustive aggregation |
| `backend/app/retrieval/runtime.py`, `backend/app/retrieval/document_lookup.py` | Workspace-only `HybridRetrievalRuntime` and V1 document-list shaping |
| `backend/app/workflows/graphrag_query.py` | V1 worker-owned native GraphRAG final answer and hybrid fallback |
| `execute_graphrag_query`, `execute_query_synthesis` worker actors | V1 background answer jobs |
| `graphrag_query_fallback_to_hybrid`, `graphrag_query_wait_seconds` settings | V1 GraphRAG chat policy |
| `backend/app/evaluation/runner.py` and `--historical-v1` | Synthetic V1 benchmark over V1 `ask()` |
| V1-only tests (`test_chat.py`, `test_chat_router.py`, `test_citations.py`, `test_entity_document_lookup.py`, `test_evaluation_runner.py`, `test_evidence_selection.py`, `test_property_aggregation.py`, `test_query_plan.py`, the runtime case in `test_retrieval.py`) | Coverage of the removed code |

Why removal was safe:

- No production module imported any of them; their only callers were each other, the
  `--historical-v1` CLI flag, and their own tests.
- Nothing enqueued the two removed worker actors.
- Persisted runtime settings that still contain the removed keys stay loadable: only names in
  `PERSISTED_FIELDS` are applied, and the next settings save rewrites the row without them.

## Moved

`summarize_conversation_with_openai` moved from `app/chat/execution.py` to
`app/query/conversation_summary.py`. The `summarize_conversation` worker actor and its behavior
are unchanged. Conversation title, backfill, and soft-delete coverage moved to
`tests/test_conversation_service.py`.

## Retained

`backend/alembic/versions/0010_logical_documents.py` (MIGRATION_ONLY): applied migration history
is durable compatibility data; retain permanently.

`backend/app/workflows/llamaindex.py` is not imported by production code but is independent of
the V1 chat stack and keeps its own tests. `backend/app/graphrag/llamaindex.py` was removed later
with the other GraphRAG prose-answer paths (see `graphrag-boundary.md`).
