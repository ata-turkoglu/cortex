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
| `canonical.structured` | READY when SQLite projection is operational | generation-bound SQLite canonical projection | structured list/count/group/rank/compare with result completeness |
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

Structured list/count/group/rank/compare reads use the SQLite canonical authority. Generation
canonical health is separate from exact-result completeness: a `PARTIAL` generation can return a
`COMPLETE` result for an unaffected governed population, or a `PARTIAL` result with known rows,
blocker count, affected dimensions, and exact evidence references. Unresolved evidence never
becomes a synthetic canonical row; retrieval is never an exhaustive fallback. Canonical graph
operations remain separately unavailable. Historical V1 property aggregation is not a current
structured-query authority.

## Final rendering and persistence

Reconciliation creates the sole `ReasoningPackage` consumed by `AnswerEngine`. The runtime persists
the final content, validated citations, generation trace, query-scoped completeness, and query
state. Chat renders a compact Complete/Partial/Unavailable disclosure with blocker evidence.

The normal answer field is a concise, user-facing synthesis only. Retrieval rows may retain evidence
text, fusion rank, dense/sparse ranks, scores, chunk identity, and engine provenance for
reconciliation and Technical Trace, but `AnswerEngine` must never serialize those fields into answer
prose. It selects a bounded set of claimable citations for normal source cards; full provenance stays
in persisted technical metadata. Typed fail-closed reasons are rendered centrally as concise Turkish
messages, with no provider diagnostics or internal reason codes in the answer text.

## Historical / V1

`backend/app/chat/`, `backend/app/aggregation/property.py`, and the workspace retrieval runtime are
not part of the production V2 request path. Some remain for historical evaluation or worker
compatibility; see [`V1_CLEANUP_REVIEW.md`](V1_CLEANUP_REVIEW.md).
