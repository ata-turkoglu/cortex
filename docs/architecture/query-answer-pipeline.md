# Query and Answer Pipeline

## Current production path

Production chat is V2-only:

```text
POST /api/v1/workspaces/{workspace}/conversations/{conversation}/messages
→ app.api.chat.query
→ query.production_chat.execute_v2_chat
→ persisted embedding configuration + V2RuntimeContextLoader
→ ConversationContext + QueryRuntimeActivation + GenerationScope
→ SemanticPlannerAdapter → SemanticUnderstanding
→ LogicalQueryIR validation/lowering → physical planner/readiness
→ engine registry → reconciliation → ReasoningPackage → AnswerEngine
→ Message + QueryRun persistence
```

The production endpoint has no V1 route selection, `QueryPlan`, `HybridRetrievalRuntime`,
workspace-only BM25, or final-answer fallback.

## Capability families

| Family | Current status | Inputs | Output boundary |
| --- | --- | --- | --- |
| `retrieval.grounded` | READY | immutable source manifest; generation-bound dense and/or BM25 projection | exact evidence validated against the manifest |
| `graphrag.grounded` | PARTIAL | source manifest; generation GraphRAG artifacts | typed findings through the trusted-source bridge |
| `canonical.exhaustive` | NOT PRODUCTION ACCEPTED | canonical population/projection completeness | structured list/count/group/rank/compare |
| `canonical.graph` | NOT PRODUCTION ACCEPTED | canonical relation/event projection | traversal and canonical event results |

Canonical readiness must not conceptually define all V2 readiness. A canonical capability that is
unavailable must fail closed; it must not cause a grounded retrieval request to become a V1 request.

## Retrieval and evidence

`retrieval.grounded` binds workspace ID, generation ID, and embedding configuration hash before
reading Qdrant. Sparse retrieval loads only the selected generation's BM25 artifact. Dense and
sparse candidates are fused, converted to typed `EngineResult` output, and reconciled only against
the immutable generation source manifest. Unsupported answers contain no citations.

## GraphRAG

Local, Global, and DRIFT are distinct generation-artifact capabilities. Their native prose is never
the final answer: the V2 bridge requires complete source identity and a manifest-matching content
hash before a finding can reach reconciliation. This path is readiness-dependent and not yet
production-accepted end to end.

## Canonical capability boundary

Structured and graph engines use the Neo4j adapter, but canonical Entity/Mention/alias lifecycle,
identity resolution, properties, relations, and exhaustive population semantics are currently
blocked. Neo4j must not be documented as fully proven durable canonical authority. Historical V1
property aggregation is not a current structured-query authority.

## Final rendering and persistence

Reconciliation creates the sole `ReasoningPackage` consumed by `AnswerEngine`. The runtime persists
the final content, validated citations, generation trace, and query state. The generic answer
renderer remains partial; it must not be treated as a raw engine-result bypass.

## Historical / V1

`backend/app/chat/`, `backend/app/aggregation/property.py`, and the workspace retrieval runtime are
not part of the production V2 request path. Some remain for historical evaluation or worker
compatibility; see [`V1_CLEANUP_REVIEW.md`](V1_CLEANUP_REVIEW.md).
