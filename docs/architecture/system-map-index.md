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
| Query IR | `backend/app/query/ir/` | `query-v2/invariants.md` | `backend/app/query/ir/AGENTS.md` |
| Execution Planning | `backend/app/query/planning/` | `query-v2/execution-planning.md` | `backend/app/query/planning/AGENTS.md` |
| Structured Query | `backend/app/engines/structured/` | `query-v2/structured-graph-engines.md` | `backend/app/engines/structured/AGENTS.md` |
| Knowledge Graph | `backend/app/engines/graph/`, `backend/app/knowledge/graph/` | `query-v2/structured-graph-engines.md` | both scoped `AGENTS.md` files |
| Retrieval | `backend/app/engines/hybrid/`, `backend/app/retrieval/` | `retrieval-boundaries.md` | both scoped `AGENTS.md` files |
| GraphRAG | `backend/app/graphrag/` | `graphrag-boundary.md` | `backend/app/graphrag/AGENTS.md` |
| Result & Evidence | `backend/app/query/orchestration/` | `query-v2/result-evidence-layer.md` | `backend/app/query/orchestration/AGENTS.md` |
| Reasoning & Composition | `backend/app/reasoning/` | `query-v2/reasoning-composition.md` | reasoning/research/composition scoped contexts |
| Answer | `backend/app/chat/execution.py` | `query-answer-pipeline.md` | `backend/AGENTS.md` |

Execution Planning is the explicit parent of Structured Query, Knowledge Graph, Retrieval, and
GraphRAG work. Every engine returns typed output to Result & Evidence. GraphRAG remains an extracted
knowledge capability, never canonical truth or a final-answer author. Reasoning & Composition
receives a reconciled `ReasoningPackage`; Answer receives only grounded, partial, or unsupported
validated material.

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
V1 chat remains the active entrypoint until Phase 13 completes the full rebuild, acceptance gates,
and sharp activation. The selected Phase 05A candidate proves one workspace delivery; it does not
prove full-corpus completeness across every workspace.

Review the manifest, its linked docs, and `ASystemMap.test.tsx` together whenever a subsystem
boundary changes. The Live system tab reports current health; transient local debugging failures
must not be encoded as architecture.
