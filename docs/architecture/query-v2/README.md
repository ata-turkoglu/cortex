# Cortex Query Architecture V2

Status: **binding target architecture; not the active production runtime**.

The active V1 runtime remains documented in
[`../query-answer-pipeline.md`](../query-answer-pipeline.md). The discovery notes under
[`../discovery/query-v2/`](../discovery/query-v2/) describe the code as inspected on
2026-08-16; they are evidence for this design, not an architecture contract.

V2 turns Cortex from a route-oriented RAG orchestrator into a conversation-aware workspace
intelligence system. It separates semantic interpretation from physical execution, uses a
versioned logical query DAG, composes typed results from multiple engines, and makes provenance
and corpus-completeness explicit. The cutover is a full rebuild followed by one sharp activation;
V1 and V2 do not become long-lived parallel query runtimes.

## Canonical documents

- [`invariants.md`](invariants.md) defines rules every V2 subsystem must preserve.
- [`query-runtime.md`](query-runtime.md) defines Conversation Context through Answer Engine.
- [`execution-planning.md`](execution-planning.md) defines the implemented Phase 08 physical DAG,
  capability readiness, optimization, and failure-policy contract.
- [`result-evidence-layer.md`](result-evidence-layer.md) defines the implemented Phase 09 engine
  result, exact-span reconciliation, completeness, and reasoning-package contract.
- [`structured-graph-engines.md`](structured-graph-engines.md) defines the implemented Phase 10
  deterministic canonical-population and Cortex-adapter graph execution boundaries.
- [`reasoning-composition.md`](reasoning-composition.md) defines Phase 11 durable multi-query
  research, cross-source reasoning, grounded section drafting, and internal provenance.
- [`knowledge-construction.md`](knowledge-construction.md) defines the canonical knowledge model,
  Neo4j boundary, indexing stages, provenance, and generation readiness.
- [`repository-boundaries.md`](repository-boundaries.md) maps first-class subsystem ownership to
  repository paths and records the V1-compatible migration boundary.
- [`../system-map-index.md`](../system-map-index.md) maps every Phase 12 React Flow group to its
  implementation boundary, canonical documentation, and scoped AI context.

The staged implementation pack in [`../../../cortex-query-v2/00-README.md`](../../../cortex-query-v2/00-README.md)
controls delivery order. Binding V1 safety and product decisions in
[`../../../codex-prompts/docs/DECISIONS.md`](../../../codex-prompts/docs/DECISIONS.md) remain in
force unless this V2 contract explicitly supersedes them at cutover.

## First-class subsystem map

| Subsystem | Owns | Must not own |
| --- | --- | --- |
| Conversation Context | conversation-local references, resolved focus, assumptions, bounded history | canonical workspace knowledge |
| Query Understanding | schema-constrained semantic interpretations and ambiguity | physical engines or routes |
| Logical Query IR | versioned, typed, composable user meaning | provider calls or storage-specific queries |
| Execution Planning | capability/readiness-based physical DAG and failure policy | final answer text |
| Structured Query Engine | deterministic enumeration, filtering, grouping, ranking, aggregation | top-k approximation presented as exhaustive |
| Knowledge Graph Engine | canonical traversal, multi-hop, temporal and provenance queries | direct Neo4j driver leakage |
| Retrieval Engine | workspace-filtered dense, sparse, fusion, reranking, evidence retrieval | corpus-completeness claims |
| GraphRAG Engine | Local, Global, and DRIFT findings from extracted/community views | canonical truth or final answers |
| Result & Evidence Layer | normalization, reconciliation, provenance/completeness validation, citations | unsupported fact invention |
| Reasoning & Composition | cross-result reasoning and durable research/composition | bypassing evidence validation |
| Answer Engine | final user-facing response and answer state | engine execution or source mutation |
| Indexing V2 / Knowledge Construction | provenance-bearing knowledge extraction, validation, projections, readiness | overwriting user curation |

## Activation and documentation policy

Until sharp cutover, V2 documents describe the target and V1 chat remains the active query
entrypoint. `/system-map` now manifests the implemented V2 subsystem topology and its inactive
activation boundary; it does not claim that requests execute through that topology. Each
implementation phase must update its owning code, tests, architecture document, scoped AI
navigation, and runtime manifest when a represented boundary changes. A partial V2 generation is
never activated or described as corpus-complete.
