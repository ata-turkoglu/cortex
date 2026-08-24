# Query V2 structured and knowledge graph engines

Status: **Structured and canonical graph engine steps are dispatched by live V2 chat through the
generation-bound physical-plan registry.**

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

### Governed canonical entity properties

Canonical identity is stable; queryable knowledge about that identity is stored as a separate,
generation-scoped `CortexEntityProperty` projection. Each resolved property has a closed vocabulary
definition, typed value, authority, generation, and a `SUPPORTED_BY` link to exact evidence. The
initial governed definition is `person.surname` (`string`, equality only). It is populated only by
an explicit extraction-stage `entity_properties` assertion whose value is its exact source span;
the runtime never derives it from `display_name`.

When multiple distinct values are proposed for one entity/property in a generation, no resolved
property is projected. Structured filtering therefore cannot fabricate a value from a conflict.
`CanonicalPopulationQueryView` exposes only resolved governed properties and joins their evidence
to the entity record. Population reads use generation-scoped mention evidence rather than the
mutable entity-node generation field, preserving historical generation isolation.

### LIST/COUNT authority and identity cardinality

The production governed LIST/COUNT path fixes `workspace_id` and `knowledge_generation_id` before
loading the canonical population. It filters resolved governed values and returns canonical entity
identities for LIST or a `CountNode` aggregate for COUNT. A canonical entity is counted once even
when multiple mentions resolve to it or it has multiple aliases. Mentions and aliases remain
provenance-bearing identity artifacts; they are not population rows.

The canonical population is the sole authoritative source for exhaustive COUNT. Dense/sparse
retrieval top-k, evidence and citation lists, and AnswerEngine rendering cannot supply or alter
that count. Invalid entity-type/property combinations fail during governed vocabulary validation,
before a structured read; no retrieval fallback or arbitrary Neo4j property read is allowed.

### Governed GROUP/RANK/COMPARE

The initial production analytic vocabulary is limited to `person.surname`. GROUP creates
canonical surname groups and their canonical-entity counts. RANK orders those groups by the
authoritative canonical count, then by normalized group key for a deterministic tie. COMPARE reads
two governed surname-filtered populations from the same workspace and generation and returns both
counts independently. Missing or conflicted/withheld property values are excluded rather than
forming synthetic groups. These operators use `StructuredQueryEngine` only; retrieval top-k,
mentions, aliases, citation counts, and AnswerEngine rendering have no authority over their values.

## Knowledge Graph Engine

### Production-ready exact-day event membership

For a natural-language exact date such as `12.06.1974 tarihinde ne oldu?`, semantic
understanding normalizes the dotted Turkish day to `1974-06-12`, assigns the semantic role
`event_date`, and lowers it to `EventSetNode -> TemporalConstraintNode`. Physical planning selects
`graph.event_filter`; the canonical graph adapter reads only `OCCURRED_AT` links for that exact
workspace and generation. The resulting canonical events enter `EngineResult.events`, are
reconciled into `ReasoningPackage.events`, and are rendered by `AnswerEngine`.

`event_date` is not `document_date`: a document dated on the requested day does not make an event
whose own date differs a member of the result. Exact-day event membership is graph-authoritative,
not a dense/sparse retrieval top-k approximation, and an empty exact-date graph result is a
truthful empty event population. Impossible calendar days fail semantic validation before graph,
retrieval, or structured execution. Date ranges, fuzzy/relative dates, and other temporal work
remain unavailable.

### Production-ready direct relation traversal

The first governed relation vocabulary entry is outgoing `person --parent_of--> person`. A direct
natural-language children query resolves its parent to an opaque canonical ID through the
generation-scoped identity catalogue, lowers to `TraverseNode(relation="parent_of",
direction="outgoing", target="person")`, and executes only through `KnowledgeGraphEngine`.
`query_canonical_paths` filters every relation edge by workspace and generation and obtains exact
supporting evidence through the canonical artifact boundary. The graph result contains target
canonical entities and relation paths in the shared `EngineResult`; `AnswerEngine` renders only the
reconciled package. Dense/sparse retrieval is not authoritative for relation membership.

The canonical entity node's mutable generation field is not used for historical identity loading:
the generation identity catalogue is selected through mention evidence for the requested generation.
This preserves direct relation traversal across G1/G2 property and relation state.

For a persisted plural conversation referent, the source `ResolveNode` contains the final canonical
entity IDs from the prior `ReasoningPackage`, bound to the same workspace and generation. The graph
engine traverses every source ID; it does not re-resolve names or inspect answer prose.

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

## Live-runtime boundary

The active V2 chat service creates each engine from the immutable workspace/generation scope,
executes dependency-ordered structured and graph steps, and reconciles their `EngineResult` values
with retrieval output. A document `structured.enumerate` scan remains a non-material retrieval
prerequisite. GraphRAG Local, Global, and DRIFT are separately registered and only contribute
normalized artifact findings after their complete chunk identity resolves against the selected
generation's `TrustedSource` snapshot. Missing, cross-scope, unknown, or hash-mismatched identity
fails closed; Microsoft GraphRAG's native answer output is not a V2 answer path.
