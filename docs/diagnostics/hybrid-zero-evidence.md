# HybridRetriever zero-evidence diagnostic

Date: 2026-08-10

## Executive finding

The affected workspace has active relational chunks but no dense or sparse retrieval index.
Migration `0013_bm25_workspace_resource` adds only a `workspace_resources` row; it never builds
an `evidence.json`/bm25s corpus. The ingestion workflow marks its `index` checkpoint complete
without writing Qdrant vectors or a BM25 index. Additionally, the API Docker target omits the
`retrieval` dependency group, so `bm25s` is unavailable in the process that serves synchronous
chat. This is an index/backfill and API dependency problem, not a router, workspace filter, RRF,
reranker, or final-limit problem.

## Runtime trace

Observed stored assistant-message trace for `Hasan Tahsin Merter hakkında neler biliyoruz?`:

| Stage | Observed value |
| --- | --- |
| route | `hybrid` |
| dense | `executed=false`, `candidate_count=0`, `error=qdrant_unavailable:ValueError` |
| BM25 | `executed=false`, `candidate_count=0`, `error=bm25_unavailable:ModuleNotFoundError` |
| fusion | `candidate_count=0` |
| reranker | not executed; input/output `0/0` |
| final evidence | `0` |

`HybridRetrievalRuntime._embed_query()` completed sufficiently to call dense search. Qdrant then
raises because `WorkspaceQdrantStore.search("chunks", ...)` requires
`context.index_state.embedding_config_hash`, which is `None`.

## Live database state

Workspace: `d582ffe9-c272-45c5-b072-134e577bc1f2` (`merter-arsiv`).

| Item | Count/state |
| --- | --- |
| active documents | 13 |
| active document versions | 13 |
| active chunks | 19 |
| dense state | `reindex_required` |
| sparse state | `reindex_required` |
| active embedding hash | `None` |

Four active chunks contain the exact literal `Hasan Tahsin Merter`. The central specimen is
chunk `1d4b3f73-4ee2-457a-a2eb-4e0e6a8cf7f4`, document
`d3208ef3-fdd6-460a-88ba-78b54bdd8fc1`, version
`f24a73e9-e1a6-43b0-bb74-5e23f0bd2fa2`; its text starts `Hasan Tahsin Merter Simitaş 2. Blok`.

## Qdrant state

Configured collection: `cortex_chunks`. The running Qdrant instance has only GraphRAG collections
(`cortex_graphrag_entities`, `cortex_graphrag_reports`, `cortex_graphrag_text_units`).
`cortex_chunks` does not exist, so total chunk points, workspace points, active-hash points, and
workspace-plus-hash points are all zero. There are no payloads to inspect and no hash mismatch:
there is no indexed hash at all.

## BM25 state

The workspace has a `bm25_chunks` resource pointing to
`workspaces/d582ffe9-c272-45c5-b072-134e577bc1f2/bm25`, but that directory has no
`evidence.json`, no bm25s files, and therefore no corpus/chunk IDs. `WorkspaceBM25Index.load()`
cannot load it. The production API image also reports `bm25s None` and
`sentence_transformers None`, because `backend/Dockerfile` builds `runtime` from `query-deps`
rather than `worker-deps`.

## Indexing-path evidence

`api/uploads.py` persists chunks and queues an `ingestion` run. `workflows/service.py.execute_run`
only advances durable checkpoints; it has no call site for `WorkspaceBM25Index.save`, embedding,
`WorkspaceQdrantStore.upsert`, or `mark_dense_index_ready`. Repository search confirms no runtime
call site constructs a BM25 index or writes chunk vectors. Existing completed ingestion runs are
therefore relational ingestion only, not retrieval indexing.

## Root cause classification

- **C / K:** Qdrant has no chunk points because ingestion never populated dense retrieval.
- **A / D / K:** the BM25 resource row exists but its corpus is empty/absent; there is no backfill.
- **G:** the API image cannot load BM25 because it excludes the retrieval dependency group.

Workspace IDs are consistent in the database/resource row; filter isolation, RRF, reranking, and
`final_evidence_top_k` cannot remove candidates because neither branch yields candidates.

## Required corrective path

Implement a worker-owned, idempotent workspace retrieval rebuild that snapshots active chunks,
builds and atomically persists the workspace BM25 corpus, embeds chunks with the configured
provider, replaces only that workspace's Qdrant chunk points, records the resulting configuration
hash, and marks dense/sparse state ready only after success. Route ingestion and existing
`dense_reindex` runs through it, then enqueue one rebuild for the affected workspace. Include the
retrieval dependency group in the API image (or move synchronous hybrid retrieval to the retrieval
capable worker); retaining the present synchronous API architecture requires the former.

No query-time SQLite fallback or weakened Qdrant hash filter is appropriate.

## Remaining limitations

This diagnosis does not add COUNT aggregation, LIST ALL aggregation, entity resolution, planner
redesign, or Hybrid–GraphRAG fusion.
