# System Map runtime manifest

`/system-map` is implemented in `frontend/src/flow/ASystemMap.tsx`; shared React Flow behavior
remains behind `frontend/src/flow/AFlowCanvas.tsx`. The exported `SYSTEM_MAP_V2_MANIFEST` is the
canonical UI manifest for Query V2 and Indexing V2. Its tests require every subsystem to name a
real implementation boundary, canonical architecture document, and nearest scoped AI context.

| `/system-map` tab | Meaning | Main source | Canonical documentation |
| --- | --- | --- | --- |
| Live system | Service topology enriched with backend health and diagnostics | `ASystemMap.tsx`, health API | `deployment.md`, `backend-foundation.md` |
| Indexing V2 | Implemented knowledge-construction and generation-readiness boundaries | `SYSTEM_MAP_V2_MANIFEST.indexing` | `query-v2/knowledge-construction.md` |
| Query V2 | Implemented semantic, planning, engine, evidence, reasoning, and answer boundaries | `SYSTEM_MAP_V2_MANIFEST.query` | `query-v2/query-runtime.md` |
| Background workflows | Durable command, broker, worker, checkpoint, recovery, and SSE topology | `ASystemMap.tsx`, `workflowSchemas.ts` | `../workflows/durable-workflows.md` |

## Query V2 groups

| Group | Implementation boundary | Canonical docs | Scoped context |
| --- | --- | --- | --- |
| Conversation Context | `backend/app/query/context/` | `query-v2/query-runtime.md` | `backend/app/query/context/AGENTS.md` |
| Query Understanding | `backend/app/query/understanding/` | `query-v2/query-runtime.md` | `backend/app/query/understanding/AGENTS.md` |
| Canonical Entity Resolution | `backend/app/query/briefing.py` | `query-v2/query-runtime.md` | query understanding scoped context |
| Governed Vocabulary Validation | `backend/app/query/ir/validation.py`, `backend/app/query/runtime_inputs.py` | `query-v2/query-runtime.md` | query IR scoped context |
| Query IR | `backend/app/query/ir/` | `query-v2/invariants.md` | `backend/app/query/ir/AGENTS.md` |
| Execution Planning | `backend/app/query/planning/` | `query-v2/execution-planning.md` | `backend/app/query/planning/AGENTS.md` |
| StructuredQueryEngine / Canonical Population | `backend/app/engines/structured/` | `query-v2/structured-graph-engines.md` | `backend/app/engines/structured/AGENTS.md` |
| Governed Filter / CountNode | `backend/app/engines/structured/engine.py`, `backend/app/query/planning/planner.py` | `query-v2/structured-graph-engines.md` | structured-engine and planning scoped contexts |
| Knowledge Graph | `backend/app/engines/graph/`, `backend/app/knowledge/graph/` | `query-v2/structured-graph-engines.md` | both scoped `AGENTS.md` files |
| Retrieval | `backend/app/engines/hybrid/`, `backend/app/retrieval/` | `retrieval-boundaries.md` | both scoped `AGENTS.md` files |
| GraphRAG | `backend/app/graphrag/` | `graphrag-boundary.md` | `backend/app/graphrag/AGENTS.md` |
| Final-root Reconciliation | `backend/app/query/orchestration/` | `query-v2/result-evidence-layer.md` | `backend/app/query/orchestration/AGENTS.md` |
| Reasoning & Composition | `backend/app/reasoning/` | `query-v2/reasoning-composition.md` | reasoning/research/composition scoped contexts |
| Answer | `backend/app/chat/execution.py` | `query-answer-pipeline.md` | `backend/AGENTS.md` |

Execution Planning is the explicit parent of Structured Query, Knowledge Graph, Retrieval, and
GraphRAG work. For semantic structured work, only results that implement final logical IR roots
enter reconciliation; intermediate DAG results remain execution dependencies. The governed
LIST/COUNT path fixes workspace + knowledge generation, reads canonical identity cardinality, and
never derives exhaustive COUNT from retrieval top-k. Direct outgoing `person --parent_of--> person`
traversal is generation-bound and graph-authoritative. Exact-day event membership follows
`SemanticUnderstanding(event_date)` -> `EventSetNode` -> exact `TemporalConstraintNode` ->
`graph.event_filter` -> canonical `EngineResult.events` -> reconciliation ->
`ReasoningPackage.events` -> `AnswerEngine`; `event_date` is distinct from `document_date` and is
never retrieval top-k. Persisted final canonical result sets may also be reused as plural,
generation-bound sources for direct relation traversal. GraphRAG remains an extracted knowledge
capability, never canonical truth or a final-answer author. Local, Global, and DRIFT artifact
findings pass their complete source identity through the trusted-provenance bridge into
`EngineResult`, reconciliation, `ReasoningPackage`, and `AnswerEngine`; unresolvable, cross-scope,
or hash-mismatched references fail closed. Temporal ranges/fuzzy/relative dates remain incomplete.
Reasoning & Composition receives a reconciled
`ReasoningPackage`; Answer receives only grounded, partial, or unsupported validated material.

## Indexing V2 groups

| Group | Implementation boundary | Scoped context |
| --- | --- | --- |
| Source Processing | `backend/app/ingestion/` | `backend/AGENTS.md` |
| Document Structure | `backend/app/ingestion/`, `backend/app/knowledge/provenance/` | provenance scoped context |
| Entity / Mention | `backend/app/knowledge/entities/` | entities scoped context |
| Identity | `backend/app/knowledge/entities/` | entities scoped context |
| Relation | `backend/app/knowledge/relations/` | relations scoped context |
| Event | `backend/app/knowledge/events/` | events scoped context |
| Temporal | `backend/app/knowledge/temporal/` | temporal scoped context |
| Claim / Fact | `backend/app/knowledge/claims/` | claims scoped context |
| KG Build | `backend/app/knowledge/graph/` | graph scoped context |
| BM25 | `backend/app/retrieval/indexing.py` | retrieval scoped context |
| Dense / Qdrant | `backend/app/retrieval/qdrant.py` | retrieval scoped context |
| GraphRAG | `backend/app/graphrag/` | GraphRAG scoped context |
| Generation / Readiness | `backend/app/knowledge/generation.py`, `backend/app/workflows/knowledge.py` | knowledge and workflow scoped contexts |

The canonical KG Build and GraphRAG stages are separate projections. BM25, Dense/Qdrant, and
GraphRAG must independently report matching generation and source fingerprints before the
Generation / Readiness gate can activate a candidate.

## Activation status

The manifest describes real implemented boundaries and contracts, but it is not a cutover claim.
Production chat is V2-only after the Phase 13 rebuild, acceptance gates,
and sharp activation. The selected Phase 05A candidate proves one workspace delivery; it does not
prove full-corpus completeness across every workspace.

Review the manifest, its linked docs, and `ASystemMap.test.tsx` together whenever a subsystem
boundary changes. The Live system tab reports current health; transient local debugging failures
must not be encoded as architecture.
