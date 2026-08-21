# Query V2 structured and knowledge graph engines

Status: **Phase 10 implemented behind the inactive V2 boundary**.

Both engines consume typed Phase 08 steps and emit Phase 09 `EngineResult` values. Neither engine
authors final prose, persists assistant messages, or calls the V1 chat runtime.

## Structured Query Engine

`StructuredQueryEngine` executes deterministic operators over a detached `CanonicalPopulation`.
Implemented operators cover exhaustive enumeration, filter, join, distinct, group, count and
distinct count, minimum/maximum/sum/average, rank/top-N, sort, limit, projection, temporal filter,
existence, and population comparison. Every output retains its contributing exact evidence.

`load_canonical_population` obtains a workspace/generation-bound snapshot through a typed canonical
population reader. The Neo4j implementation first counts the entire active canonical population,
then reads at most the configured safe bound. If the population exceeds that bound, an entity has
no exact evidence, or unresolved candidates remain, the snapshot is marked
`not_safely_enumerable`. Results expose `confirmed_count`, the observed candidate count,
`unresolved_candidate_ids`, and partial state; they never substitute top-k retrieval or an
approximate total.

## Knowledge Graph Engine

`KnowledgeGraphEngine` accesses Neo4j only through `CanonicalGraphReader`, implemented by the
Cortex-owned `Neo4jGraphAdapter`. It supports canonical entity lookup, bounded directed/either
relation traversal through ten hops, event participation, temporal event constraints, provenance
traversal, and supported-claim conflict inspection. Unresolved identities return unsupported;
multiple candidates remain explicit ambiguity.

Canonical relation persistence now materializes fixed `CORTEX_CANONICAL_RELATION` edges with
workspace, generation, relation ID/type, and conflict state. Events materialize participant edges;
temporal artifacts materialize event-time links. Dynamic domain relation names remain properties,
not interpolated Cypher relationship types. All query patterns constrain workspace, canonical
layer, generation, bounded hops, and bounded result counts. Relation, event, temporal, identity,
and conflict output carries exact document/version/logical-document/chunk/span evidence into
`EngineResult`.

## Activation boundary

These engines are not connected to query orchestration or V1 chat. Phase 05A still lacks a complete
production reindex/readiness delivery and no real end-to-end V2 engine plan has been accepted. This
phase therefore makes no indexing cutover, readiness UI, live corpus-completeness, or production
query claim. The current-state `/system-map` remains unchanged until the explicit cutover phase.
