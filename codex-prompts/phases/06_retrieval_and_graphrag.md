# Phase 6 — Retrieval and GraphRAG

## Goal

Implement Qdrant indexing, bm25s indexing, hybrid retrieval, local reranking, Microsoft GraphRAG indexing/query adapters, NetworkX, and evidence normalization.

## Checklist

- [ ] Create shared Qdrant collection strategy.
- [ ] Create required payload indexes.
- [ ] Enforce `workspace_id` filters in every Qdrant operation.
- [ ] Use deterministic point IDs.
- [ ] Implement dense indexing.
- [ ] Implement bm25s indexing.
- [ ] Implement parent/neighbor/heading retrieval.
- [ ] Implement hybrid fusion.
- [ ] Integrate local BGE reranker.
- [ ] Implement configurable retrieval and rerank limits.
- [ ] Integrate Microsoft GraphRAG per workspace.
- [ ] Create isolated GraphRAG root directories.
- [ ] Preserve GraphRAG knowledge-model outputs.
- [ ] Implement GraphRAG Local query adapter.
- [ ] Implement GraphRAG Global query adapter.
- [ ] Implement GraphRAG DRIFT query adapter.
- [ ] Integrate GraphRAG query engines into LlamaIndex.
- [ ] Implement NetworkX secondary graph generation.
- [ ] Implement deferred GraphRAG updates.
- [ ] Implement configurable pending-document trigger threshold.
- [ ] Implement stale graph behavior and fallback.
- [ ] Implement common `Evidence` model.
- [ ] Implement grounded, partial, and unsupported answer states.
- [ ] Add retrieval isolation tests.
- [ ] Add integration tests for route engines.
- [ ] Update `IMPLEMENTATION_STATUS.md`.

## Acceptance criteria

- [ ] No Qdrant search can run without workspace isolation.
- [ ] Hybrid Search works before GraphRAG finishes.
- [ ] Local, Global, and DRIFT remain distinct.
- [ ] Evidence from all engines can be rendered consistently.
- [ ] NetworkX is rebuildable from canonical graph outputs.

## Additional checklist

- [ ] Create a dedicated GraphRAG–Qdrant adapter module.
- [ ] Define adapter interfaces and schemas.
- [ ] Add integration tests for GraphRAG entities, reports, and text units in Qdrant.
- [ ] Add integration tests for Local, Global, and DRIFT through the adapter.
- [ ] Add explicit workspace-isolation tests for GraphRAG vectors.
- [ ] Document upstream compatibility assumptions and limitations.
- [ ] Add retrieval performance benchmark fixtures.

## Additional checklist — cost-controlled defaults

- [ ] Use `qwen3-embedding:0.6b` as the initial embedding default.
- [ ] Implement GraphRAG automatic-update Off by default.
- [ ] Implement manual and threshold-based GraphRAG update modes.
- [ ] Implement maximum-documents and token/cost warning controls.
- [ ] Implement eligible Batch API paths for GraphRAG indexing.
- [ ] Store per-stage GraphRAG token and cost reports.

## Additional checklist — multilingual embedding adapter

- [ ] Create a dedicated embedding adapter interface.
- [ ] Implement `qwen3-embedding:0.6b` Ollama adapter.
- [ ] Centralize query/document formatting in the adapter.
- [ ] Preserve Turkish and multilingual Unicode correctly.
- [ ] Add title/heading context to chunk embedding text through a deterministic template.
- [ ] Store prepared embedding text hashes.
- [ ] Validate Qdrant vector dimensions before upsert.
- [ ] Prevent mixed embedding configurations in the active vector field.
- [ ] Trigger full dense reindex when embedding configuration changes.
- [ ] Implement adaptive embedding batch-size fallback.
- [ ] Add Turkish and cross-lingual retrieval smoke tests.
- [ ] Add optional `bge-m3:567m` compatibility test.
