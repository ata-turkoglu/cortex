# Cortex query, data, and indexing context

Production `POST /chat` is V2-only: it persists the turn and `QueryRun`, snapshots one immutable
`GenerationScope`, loads detached conversation/readiness inputs, plans typed semantic understanding
and Logical IR, executes the physical V2 DAG, validates trusted evidence, reconciles final logical
roots, renders through `AnswerEngine`, and persists the assistant result and citations. There is no
V1 or workspace-only retrieval fallback.

Dense Qdrant reads bind workspace, generation, and embedding configuration; sparse BM25 reads only
the matching generation artifact. Governed LIST/COUNT/GROUP/RANK/COMPARE use exhaustive
generation-bound canonical populations, relation and exact-date event queries use the canonical
graph, and conversation referents use persisted canonical IDs. GraphRAG Local/Global/DRIFT enters
V2 only as provenance-bearing artifact findings through the trusted bridge; native CLI prose is
never a final V2 answer. `community_context` is explicitly unavailable.

`workspaces` is root scope. Documents/versions model lifecycle; logical documents/chunks are retrieval units; conversations/messages/query runs preserve chat; workflow runs/steps/events preserve durable jobs; index and GraphRAG states record readiness. `WorkspaceContext` resolves database resource mappings, workspace files/cache, graph root, and active state.

Every workspace-scoped database record carries `workspace_id`; Qdrant reads/deletes require its payload filter. BM25, uploads, normalized documents, GraphRAG files, and caches are workspace-owned. Workspace A evidence must never affect Workspace B answers.

Indexing persists chunks, builds BM25, embeds active chunks, replaces only that workspace's Qdrant projection, and marks readiness. GraphRAG reindex v2 also synchronizes provenance-bearing extracted artifacts to the same workspace/generation in Neo4j before Qdrant mirroring; canonical Neo4j knowledge is logically separate and cannot be removed by extraction replacement. Active embedding configuration hash includes provider/model/dimensions/normalization/template; a change requires full dense reindex. Useful diagnostics are retrieval component counts, `evidence_selection`, embedding state, and workspace identity.

Query V2 Phase 04 implements canonical UUID identities, original mentions, aliases, conservative
resolution, reversible merge/split history, exact source lineage, typed relations/events/temporal
expressions, evidence-gated claims/facts, and explicit conflicts. Neo4j canonical writes preserve
`user_curated > validated > extracted`. The `/knowledge` workspace API and UI support manual
merge/split/alias curation and evidence inspection. Phase 05, not Phase 04, wires automatic
corpus-wide construction and extracted-to-canonical promotion into indexing.

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

Property LIST/COUNT scans workspace candidates directly, extracts deterministic claims, validates labeled cadastral fields and local ownership/share context, binds the resolved entity, deduplicates property identity, retains provenance, and reports candidate/processed counts/completion. A chunk is evidence, not a verified property record; co-occurrence is not ownership evidence.
