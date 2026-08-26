# Cortex query, data, and indexing context

Production `POST /chat` is V2-only: it persists the turn and `QueryRun`, snapshots one immutable
`GenerationScope`, loads detached conversation/readiness inputs, plans typed semantic understanding
and Logical IR, executes the physical V2 DAG, validates trusted evidence, reconciles final logical
roots, renders through `AnswerEngine`, and persists the assistant result and citations. There is no
V1 or workspace-only retrieval fallback.

Dense Qdrant reads bind workspace, generation, and embedding configuration; sparse BM25 reads only
the matching generation artifact. `retrieval.grounded` is ready. GraphRAG Local/Global/DRIFT enters
V2 only as provenance-bearing artifact findings through the trusted bridge, remains partial and
readiness-dependent, and never supplies native CLI prose as the final answer. `canonical.exhaustive`
and `canonical.graph` are not production accepted: surname list/count, GROUP/RANK/COMPARE,
traversal, ownership inventory, and exact-date canonical events must fail closed rather than use
retrieval as an exhaustive substitute.

`workspaces` is root scope. Documents/versions model lifecycle; logical documents/chunks are retrieval units; conversations/messages/query runs preserve chat; workflow runs/steps/events preserve durable jobs; index and GraphRAG states record readiness. `WorkspaceContext` resolves database resource mappings, workspace files/cache, graph root, and active state.

Every workspace-scoped database record carries `workspace_id`; Qdrant reads/deletes require its payload filter. BM25, uploads, normalized documents, GraphRAG files, and caches are workspace-owned. Workspace A evidence must never affect Workspace B answers.

Indexing persists chunks, builds BM25, embeds active chunks, replaces only that workspace's Qdrant projection, and marks readiness. GraphRAG reindex v2 also synchronizes provenance-bearing extracted artifacts to the same workspace/generation in Neo4j before Qdrant mirroring; canonical Neo4j knowledge is logically separate and cannot be removed by extraction replacement. Active embedding configuration hash includes provider/model/dimensions/normalization/template; a change requires full dense reindex. Useful diagnostics are retrieval component counts, `evidence_selection`, embedding state, and workspace identity.

Canonical Entity/Mention/alias lifecycle, identity resolution, properties, relations, and exhaustive
population semantics are blocked. Neo4j is currently involved in canonical structured projection,
but is not proven durable canonical authority. Do not use this file to claim lifecycle, merge/split,
or structured acceptance; see `docs/architecture/V1_CLEANUP_REVIEW.md` for retained compatibility
paths and the V2 architecture documents for capability boundaries.

Query V2 conversation intelligence is active in production. Durable
`conversation_contexts` are isolated by workspace and conversation and combine with bounded message
history only in detached planner snapshots. The schema-constrained semantic planner has configurable
simple/standard/complex tiers, no V2 `intent`, explicit ambiguity/unresolved states, typed temporal
roles, and deterministic follow-up entity/temporal carry-over. It never writes conversation
assumptions into canonical knowledge.

Query V2 uses `LogicalQueryIR` version `1.0` as a typed composable DAG. It supports all target
operator families, ambiguity candidate plans, temporal meaning,
coverage, output projection, evidence requirements, and schema-governed custom capabilities. The
validator enforces workspace scope, declared resources/fields/relations, DAG and type integrity,
upstream projection lineage, and exhaustive same-generation/exact-provenance requirements. Semantic
lowering refuses underspecified operations instead of guessing, and the IR contains no provider,
route, storage query, physical engine, or V2 `intent`.

Historical property-only aggregation is not the current V2 structured model. A chunk remains
evidence rather than a verified property record; canonical structured claims await separate
acceptance.
