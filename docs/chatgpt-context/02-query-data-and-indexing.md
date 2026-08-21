# Cortex query, data, and indexing context

Chat persists a query run, creates a deterministic `QueryPlan`, resolves entities from requested-workspace chunks, and selects a route. Normal QA uses `HybridRetrievalRuntime`: workspace-filtered Qdrant dense retrieval plus workspace BM25 sparse retrieval → RRF → optional local BGE reranker → operation-aware evidence selection → concise synthesis/fallback → citation validation/pruning → final source payload. The copied-span guard can request one stricter OpenAI regeneration.

`identify`, `describe`, `timeline`, `generic_qa`, and `lookup_documents` are normal evidence routes. Document lookup groups hits by logical document. `list`/`count` reach aggregation only when explicit exhaustive property semantics are parsed; describe is never an inventory. GraphRAG Local/Global/DRIFT runs as a separate durable worker query; its native result is final and hybrid fallback is explicitly configured.

`workspaces` is root scope. Documents/versions model lifecycle; logical documents/chunks are retrieval units; conversations/messages/query runs preserve chat; workflow runs/steps/events preserve durable jobs; index and GraphRAG states record readiness. `WorkspaceContext` resolves database resource mappings, workspace files/cache, graph root, and active state.

Every workspace-scoped database record carries `workspace_id`; Qdrant reads/deletes require its payload filter. BM25, uploads, normalized documents, GraphRAG files, and caches are workspace-owned. Workspace A evidence must never affect Workspace B answers.

Indexing persists chunks, builds BM25, embeds active chunks, replaces only that workspace's Qdrant projection, and marks readiness. GraphRAG reindex v2 also synchronizes provenance-bearing extracted artifacts to the same workspace/generation in Neo4j before Qdrant mirroring; canonical Neo4j knowledge is logically separate and cannot be removed by extraction replacement. Active embedding configuration hash includes provider/model/dimensions/normalization/template; a change requires full dense reindex. Useful diagnostics are retrieval component counts, `evidence_selection`, embedding state, and workspace identity.

Query V2 Phase 04 implements canonical UUID identities, original mentions, aliases, conservative
resolution, reversible merge/split history, exact source lineage, typed relations/events/temporal
expressions, evidence-gated claims/facts, and explicit conflicts. Neo4j canonical writes preserve
`user_curated > validated > extracted`. The `/knowledge` workspace API and UI support manual
merge/split/alias curation and evidence inspection. Phase 05, not Phase 04, wires automatic
corpus-wide construction and extracted-to-canonical promotion into indexing.

Query V2 Phase 06 implements a separate, inactive conversation-intelligence boundary. Durable
`conversation_contexts` are isolated by workspace and conversation and combine with bounded message
history only in detached planner snapshots. The schema-constrained semantic planner has configurable
simple/standard/complex tiers, no V2 `intent`, explicit ambiguity/unresolved states, typed temporal
roles, and deterministic follow-up entity/temporal carry-over. It is not wired into V1 chat before
sharp cutover and it never writes conversation assumptions into canonical knowledge.

Query V2 Phase 07 implements `LogicalQueryIR` version `1.0` as a typed composable DAG, still inactive
for V1 chat. It supports all target operator families, ambiguity candidate plans, temporal meaning,
coverage, output projection, evidence requirements, and schema-governed custom capabilities. The
validator enforces workspace scope, declared resources/fields/relations, DAG and type integrity,
upstream projection lineage, and exhaustive same-generation/exact-provenance requirements. Semantic
lowering refuses underspecified operations instead of guessing, and the IR contains no provider,
route, storage query, physical engine, or V2 `intent`.

Property LIST/COUNT scans workspace candidates directly, extracts deterministic claims, validates labeled cadastral fields and local ownership/share context, binds the resolved entity, deduplicates property identity, retains provenance, and reports candidate/processed counts/completion. A chunk is evidence, not a verified property record; co-occurrence is not ownership evidence.
