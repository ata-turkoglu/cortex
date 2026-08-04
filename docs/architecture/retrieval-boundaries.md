# Retrieval Boundary

LlamaIndex routes Hybrid Search and separate GraphRAG Local, Global, and DRIFT engines.
Hybrid search combines workspace-filtered Qdrant dense retrieval, bm25s sparse retrieval,
fusion, and a local BGE reranker. Embedding configuration changes require dense reindexing;
vectors with incompatible dimensions/configurations may never share an active vector field.

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

Sparse indexes are per-workspace bm25s corpora and are never shared. The corpus and its
evidence metadata persist beneath the workspace cache path and reject cross-workspace loads.
Hybrid fusion uses reciprocal-rank fusion and applies the configured dense, BM25, fusion,
reranker, and final-evidence limits. The local BGE reranker loads only pre-installed model
weights from the Sentence Transformers cache; retrieval falls back to fused evidence with a
partial result if its configured model is unavailable.

The Ollama adapter calls `/api/embed` and exposes a lightweight embedding health check. Qwen3
query/document preparation is kept inside that adapter and preserves Turkish Unicode while
normalizing line endings; retrieval feature code never owns model-specific prefixes.

An incompatible embedding configuration creates one idempotent `dense_reindex` workflow request.
The new configuration cannot become active until that full replacement workflow marks its dense
index ready, so old vectors cannot silently serve a changed model or formatting policy.

Phase 10 coverage verifies configuration-fingerprint isolation, dimension rejection, adaptive
batch recovery, and Turkish plus cross-lingual retrieval smoke cases against the workspace-safe
Qdrant boundary.
