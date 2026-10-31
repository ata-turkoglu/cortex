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
sparse retrieval use the user's text plus the display names of conversation-resolved follow-up
referents, so a pronoun-only follow-up still retrieves evidence for its resolved entity; the
persisted `retrieval_queries` metadata records that exact text. Dense and
sparse candidates are fused, converted to typed `EngineResult` output, and reconciled only against
the immutable generation source manifest. Unsupported answers contain no citations.

## GraphRAG

Local, Global, and DRIFT are distinct generation-artifact capabilities. Their native prose is never
the final answer: the V2 bridge requires complete source identity and a manifest-matching content
hash before a finding can reach reconciliation. Native entities and community reports are traced to
their Cortex chunks through GraphRAG's text units and `<chunk_id>.md` input documents (see
[`graphrag-boundary.md`](graphrag-boundary.md)). By default findings are selected by lexical overlap
with the question. With `graphrag_smart_search_enabled` (default off), GraphRAG's own selection
step chooses them: Local by entity-embedding similarity (no model call), Global by dynamic community
selection with the Global model, and DRIFT by one primer call with the DRIFT model. GraphRAG's
answer-writing step never runs. Any selection failure falls back to lexical selection. This path is readiness-dependent and not yet
production-accepted end to end.

## Canonical capability boundary

Structured list/count/group/rank/compare reads use the SQLite canonical authority. Generation
canonical health is separate from exact-result completeness: a `PARTIAL` generation can return a
`COMPLETE` result for an unaffected governed population, or a `PARTIAL` result with known rows,
blocker count, affected dimensions, and exact evidence references. Unresolved evidence never
becomes a synthetic canonical row; retrieval is never an exhaustive fallback. Canonical graph
operations remain separately unavailable. Query-scoped completeness is evaluated only when a final
result step comes from the structured engine; grounded retrieval answers have no canonical
population, never inherit unrelated identity blockers, and never report a top-k hit count as a
known count. Historical V1 property aggregation is not a current
structured-query authority.

## Final rendering and persistence

Reconciliation creates the sole `ReasoningPackage` consumed by `AnswerEngine`. The runtime persists
the final content, validated citations, generation trace, query-scoped completeness, and query
state. Chat renders a compact Complete/Partial/Unavailable disclosure with blocker evidence.
Read transactions are closed before planner and embedding provider calls. A failure while
persisting the result takes the same failure path as an execution error, so a committed user turn
never leaves its `QueryRun` in `running`. If a concurrent turn has already advanced the conversation
context revision, the validated answer is kept and only this turn's context update is skipped.

The normal answer field is a concise, user-facing synthesis only. Retrieval rows may retain evidence
text, fusion rank, dense/sparse ranks, scores, chunk identity, and engine provenance for
reconciliation and Technical Trace, but `AnswerEngine` must never serialize those fields into answer
prose. Retrieval excerpts use the cited source sentence that best matches the query terms. When
`answer_synthesis_enabled` is on, eligible grounded retrieval answers are rewritten by the opt-in
grounded synthesis step inside the Answer Engine; see
[`query-v2/answer-synthesis-proposal.md`](query-v2/answer-synthesis-proposal.md).
It selects a bounded set of claimable citations for normal source cards; full provenance stays
in persisted technical metadata. Typed fail-closed reasons are rendered centrally as concise Turkish
messages, with no provider diagnostics or internal reason codes in the answer text.

## Historical / V1

The V1 chat orchestration (`backend/app/chat/`), `backend/app/aggregation/property.py`, the
workspace hybrid retrieval runtime, and the V1 GraphRAG chat worker have been removed; see
[`V1_CLEANUP_REVIEW.md`](V1_CLEANUP_REVIEW.md).
