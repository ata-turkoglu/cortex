# Retrieval Boundary

LlamaIndex routes Hybrid Search and separate GraphRAG Local, Global, and DRIFT engines.
Hybrid search combines workspace-filtered Qdrant dense retrieval, bm25s sparse retrieval,
fusion, and a local BGE reranker. Embedding configuration changes require dense reindexing;
vectors with incompatible dimensions/configurations may never share an active vector field.

## Structured query execution

Chat creates a validated compositional query plan before Hybrid Search. The plan records the
operation, entity mentions/resolution confidence, date constraints, and whether a request needs
exhaustive retrieval, aggregation, or deduplication. Entity resolution reads only active chunks
from the requested workspace; resolved names provide bounded additional HybridRetriever queries,
then an operation-aware deterministic selector favors resolved full names, descriptive context, and
document-diverse evidence while penalizing numeric/OCR shorthand, stubs, and evidence without the
resolved entity. It does not
alter dense, BM25, fusion, or reranker scoring. Explicit exhaustive property LIST/COUNT requests
use a separate workspace-scoped aggregation boundary that processes active relational candidates;
it does not change Hybrid Search, Qdrant, BM25, or GraphRAG ranking/indexing.

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
evidence metadata persist beneath the workspace-owned `bm25_chunks` resource path and reject
cross-workspace loads. `HybridRetrievalRuntime` is the chat-facing composition boundary: it loads
that index, creates the configured query embedding, binds `WorkspaceQdrantStore` to the active
workspace/configuration hash, and calls `HybridRetriever.search()`.

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

Entity/document-list questions are planned as `entity_document_lookup` with `needs_list=true`.
Their hybrid candidates are grouped by `document_id`, and
returned as unique document matches that retain ordered matching chunks. Answer context is formed
as document blocks with document code, title, page, original source, and document type; synthesis
emits one concise row and one citation per document instead of passage dumps.
Here `document_id` is the logical-document ID when a source container was split; evidence also
retains `source_document_id` and `source_original`. Retrieval therefore labels a hit `B-2/i`
rather than `MERTER B.docx`, while source inspection can still navigate back to the DOCX.

An incompatible embedding configuration creates one idempotent `dense_reindex` workflow request.
The new configuration cannot become active until that full replacement workflow marks its dense
index ready, so old vectors cannot silently serve a changed model or formatting policy.

Phase 10 coverage verifies configuration-fingerprint isolation, dimension rejection, adaptive
batch recovery, and Turkish plus cross-lingual retrieval smoke cases against the workspace-safe
Qdrant boundary.
