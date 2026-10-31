# Retrieval Boundary

## Query V2 ownership

`app/retrieval/` remains the implementation boundary for the V2 Retrieval Engine. It is not copied
under `app/engines/`; typed cross-engine composition belongs to `app/engines/hybrid/`.

LlamaIndex routes Hybrid Search and separate GraphRAG Local, Global, and DRIFT engines.
Hybrid search combines workspace-filtered Qdrant dense retrieval, bm25s sparse retrieval,
fusion, and a local BGE reranker. Embedding configuration changes require dense reindexing;
vectors with incompatible dimensions/configurations may never share an active vector field.

Embedding provider and model selection is durable runtime configuration. Production code resolves
it only through `app.core.embedding_runtime`: database session, `load_runtime_settings`, strict
configuration validation, then the configured adapter. Cortex has no implicit production embedding
model fallback: missing configuration fails closed, produces no adapter or fingerprint, and backend
and worker use the same persisted configuration. Catalog models are selectable options, never runtime
defaults.

Phase 13's production V2 composition uses the same retrieval implementations through stricter
adapters. `V2DenseAdapter` can call only `WorkspaceQdrantStore.search_generation()`, whose filter
requires workspace, knowledge generation, and embedding fingerprint. `V2SparseAdapter` can load
only `GenerationBM25Store` from `knowledge-candidates/<generation>/bm25`. Both projections retain
chunk/document/version/logical-document/content-hash identity and are validated against the
immutable generation source manifest before reconciliation. Neither adapter can reach
`HybridRetrievalRuntime`, workspace-only dense search, or the legacy workspace BM25 artifact.

## Capability boundary

`retrieval.grounded` is ready when the source manifest and at least one generation-bound retrieval
projection are ready. It is independent of `canonical.exhaustive` and `canonical.graph`. Retrieval
never claims corpus completeness and cannot replace a canonical list/count/group/rank/compare,
relation traversal, or property inventory.

A grounded descriptive request that names a person or other entity may use its literal mention as
the dense/BM25 retrieval query when exact canonical identity resolution is absent or collides. It
does not synthesize an ID, choose a candidate, or make the canonical request resolved: the semantic
identity uncertainty remains durable while V2 retrieves and validates generation-bound evidence.
This exception is limited to unstructured descriptive/evidence work. Typed filters, relations,
temporals, LIST/COUNT/GROUP/RANK/COMPARE, and every exhaustive request remain on the canonical
path and fail closed when that path is unavailable.

## Phase 6 implementation boundary

`app/retrieval/qdrant.py` is the only Qdrant adapter. It always creates a
`workspace_id` filter for read/delete operations, stamps it on writes, uses shared
resource-type collections, and derives deterministic UUIDv5 point IDs. The active
embedding configuration is fingerprinted; mismatched dimensions are rejected before an
upsert. Dense chunk reads and writes require that active configuration fingerprint, so a
workspace can never mix vectors from different embedding configurations. A configuration
change marks the workspace `reindex_required`; only a successful full replacement index can
mark the new fingerprint ready. `app/providers/embeddings.py` owns the stable title/heading/content template,
so Unicode—including Turkish text—is passed through unchanged.

The production V2 sparse adapter reads only `knowledge-candidates/<generation>/bm25`. The V1
`HybridRetrievalRuntime` has been removed; the older workspace-owned `bm25_chunks` format is
Historical and is not reached by production V2 chat.

## Ingestion indexing contract

The worker-owned ingestion and dense-reindex paths rebuild retrieval projections from the active
workspace corpus before completing their index checkpoint. `app.retrieval.indexing` persists the
workspace BM25 corpus, embeds active chunks with the configured provider, replaces that workspace's
Qdrant chunk projection, records prepared embedding hashes, and only then marks sparse/dense state
ready with the canonical embedding configuration fingerprint. Rebuild replacement is workspace
filtered, so stale active-version vectors do not accumulate and other workspaces are untouched.
Hybrid fusion uses reciprocal-rank fusion and applies the configured dense, BM25, fusion,
reranker, and final-evidence limits. The local BGE reranker loads only pre-installed model
weights from the Sentence Transformers cache; retrieval falls back to fused evidence with a
partial result if its configured model is unavailable.

The Ollama adapter calls `/api/embed` and exposes a lightweight embedding health check. Qwen3
query/document preparation is kept inside that adapter and preserves Turkish Unicode while
normalizing line endings; retrieval feature code never owns model-specific prefixes.
Embedding calls use the global bounded embedding timeout so a local model outage becomes a
visible, retryable workflow failure instead of leaving an ingestion run indefinitely running.

Document lookup remains a grounded retrieval use case. It may group validated evidence by document,
but it is not an exhaustive corpus inventory.

An incompatible embedding configuration creates one idempotent `dense_reindex` workflow request.
The new configuration cannot become active until that full replacement workflow marks its dense
index ready, so old vectors cannot silently serve a changed model or formatting policy.

Indexing embeds `embedding_batch_size` texts per request with up to `embedding_concurrency`
requests in flight; each request retries at smaller sizes independently and vectors are joined in
input order. Ollama embedding requests pass `embedding_keep_alive` so the model stays loaded between
batches. V2 query retrieval reads `dense_top_k` dense and `bm25_top_k` sparse candidates and keeps
at most `fusion_candidate_limit` fused, manifest-bound results.

Phase 10 coverage verifies configuration-fingerprint isolation, dimension rejection, adaptive
batch recovery, and Turkish plus cross-lingual retrieval smoke cases against the workspace-safe
Qdrant boundary.
