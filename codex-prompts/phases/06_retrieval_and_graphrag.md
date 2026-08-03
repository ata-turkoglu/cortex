# Phase 6 — Retrieval and GraphRAG

## Goal

Implement Qdrant indexing, bm25s indexing, hybrid retrieval, local reranking, Microsoft GraphRAG indexing/query adapters, NetworkX, and evidence normalization.

## Checklist

- [x] Create shared Qdrant collection strategy.
- [x] Create required payload indexes.
- [x] Enforce `workspace_id` filters in every Qdrant operation.
- [x] Use deterministic point IDs.
- [x] Implement dense indexing.
- [x] Implement bm25s indexing.
- [x] Implement parent/neighbor/heading retrieval.
- [x] Implement hybrid fusion.
- [x] Integrate local BGE reranker.
- [x] Implement configurable retrieval and rerank limits.
- [x] Integrate Microsoft GraphRAG per workspace.
- [x] Create isolated GraphRAG root directories.
- [x] Preserve GraphRAG knowledge-model outputs.
- [x] Implement GraphRAG Local query adapter.
- [x] Implement GraphRAG Global query adapter.
- [x] Implement GraphRAG DRIFT query adapter.
- [x] Integrate GraphRAG query engines into LlamaIndex.
- [x] Implement NetworkX secondary graph generation.
- [x] Implement deferred GraphRAG updates.
- [x] Implement configurable pending-document trigger threshold.
- [x] Implement stale graph behavior and fallback.
- [x] Implement common `Evidence` model.
- [x] Implement grounded, partial, and unsupported answer states.
- [x] Add retrieval isolation tests.
- [x] Add integration tests for route engines.
- [x] Update `IMPLEMENTATION_STATUS.md`.

## Acceptance criteria

- [x] No Qdrant search can run without workspace isolation.
- [x] Hybrid Search works before GraphRAG finishes.
- [x] Local, Global, and DRIFT remain distinct.
- [x] Evidence from all engines can be rendered consistently.
- [x] NetworkX is rebuildable from canonical graph outputs.

## Additional checklist

- [x] Create a dedicated GraphRAG–Qdrant adapter module.
- [x] Define adapter interfaces and schemas.
- [x] Add integration tests for GraphRAG entities, reports, and text units in Qdrant.
- [x] Add integration tests for Local, Global, and DRIFT through the adapter.
- [x] Add explicit workspace-isolation tests for GraphRAG vectors.
- [x] Document upstream compatibility assumptions and limitations.
- [x] Add retrieval performance benchmark fixtures.

## Additional checklist — cost-controlled defaults

- [x] Use `qwen3-embedding:0.6b` as the initial embedding default.
- [x] Implement GraphRAG automatic-update Off by default.
- [x] Implement manual and threshold-based GraphRAG update modes.
- [x] Implement maximum-documents and token/cost warning controls.
- [x] Implement eligible Batch API paths for GraphRAG indexing.
- [x] Store per-stage GraphRAG token and cost reports.

## Additional checklist — multilingual embedding adapter

- [x] Create a dedicated embedding adapter interface.
- [x] Implement `qwen3-embedding:0.6b` Ollama adapter.
- [x] Centralize query/document formatting in the adapter.
- [x] Preserve Turkish and multilingual Unicode correctly.
- [x] Add title/heading context to chunk embedding text through a deterministic template.
- [x] Store prepared embedding text hashes.
- [x] Validate Qdrant vector dimensions before upsert.
- [x] Prevent mixed embedding configurations in the active vector field.
- [x] Trigger full dense reindex when embedding configuration changes.
- [x] Implement adaptive embedding batch-size fallback.
- [x] Add Turkish and cross-lingual retrieval smoke tests.
- [x] Add optional `bge-m3:567m` compatibility test.
