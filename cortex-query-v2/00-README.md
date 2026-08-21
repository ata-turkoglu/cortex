# Cortex Query Architecture V2 — Implementation Pack

This package breaks Cortex Query Architecture V2 into implementable phases.

## Primary goal

Evolve Cortex from an intent/route-led RAG orchestrator into a workspace intelligence system with conversation-aware semantic planning, typed Logical Query IR, execution planning, Neo4j-backed Microsoft GraphRAG, a canonical knowledge graph, structured queries, hybrid retrieval, exhaustive aggregation, and long-form research/composition.

## Binding decisions

- Remove `intent` from V2 execution.
- Conversation Context and Execution Planning are first-class subsystems.
- Use an LLM-backed Semantic Planner with configurable simple/standard/complex tiers.
- Query IR is versioned, typed, and a composable DAG; ambiguity may yield candidate plans.
- Multi-engine execution is core; no engine authors or persists a final answer.
- Engines return typed results and evidence through the Result & Evidence Layer.
- Neo4j is the canonical graph behind a Cortex adapter; GraphRAG is Neo4j-backed.
- Raw/extracted and canonical layers are logically separate in one database; GraphRAG extraction is not canonical truth.
- Canonical IDs are stable and opaque. Identity is evidence-based, conservative, and reversible.
- Preserve original mentions and `user_curated > validated > extracted` precedence.
- Every assertion requires provenance. Claims progress `ExtractedClaim → SupportedClaim → VerifiedFact`; conflicts are retained.
- Preserve original temporal text, precision, and uncertainty.
- Corpus completeness requires all mandatory projections of one generation to be ready.
- Extract entities, relations, events, temporals, and claims during indexing; quality precedes cost.
- Local/Global/DRIFT are capabilities, not intents. Reasoning & Composition is separate and durable.
- Conversation context is local; canonical knowledge is workspace-global.
- Use a full V2 rebuild and sharp cutover. `/system-map` is the runtime architecture manifest.
- Each first-class subsystem has matching boundaries, docs, and AGENTS/CLAUDE context.
- V2 evaluation is precision-oriented.

## Implementation order

1. `01-v2-architecture-contract.md`
2. `02-repository-and-ai-navigation.md`
3. `03-neo4j-graphrag-foundation.md`
4. `04-knowledge-model-and-provenance.md`
5. `05-indexing-v2-knowledge-construction.md`
   - Delivery checklist: `05a-knowledge-reindex-delivery.md`
6. `06-conversation-context-and-query-understanding.md`
7. `07-logical-query-ir.md`
8. `08-execution-planning.md`
9. `09-engine-result-and-evidence-layer.md`
10. `10-structured-and-graph-query-engines.md`
11. `11-reasoning-and-composition.md`
12. `12-system-map-v2.md`
13. `13-full-reindex-and-cutover.md`
14. `14-evaluation-and-acceptance.md`
15. `15-final-integration-audit.md`

Every phase inspects the existing repository, updates affected tests/docs/System Map/AI context, closes acceptance criteria before proceeding, and preserves V1 safety invariants.
