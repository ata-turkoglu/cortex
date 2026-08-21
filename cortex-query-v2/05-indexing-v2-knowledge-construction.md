# Phase 05 — Indexing V2 / Knowledge Construction

## Goal

Extend indexing into the complete knowledge-construction pipeline.

```text
source → parse → normalize → logical documents → chunks → metadata → entity/mention → identity
→ relation → event → temporal → claim → support/validation → canonical KG → BM25 → dense/Qdrant
→ GraphRAG → generation readiness
```

## Rules

- Extract entities, relations, events, temporals, and claims at indexing time.
- Prefer quality over cost; API-quality models are allowed.
- Every knowledge item carries provenance; retain original temporal text.
- Reindexing cannot overwrite user-curated knowledge.

## Readiness and acceptance

One generation needs ready source/relational, entity/mention, identity, relation, event, temporal, claim/fact, canonical graph, BM25, dense/Qdrant, and GraphRAG stages. Mandatory failure means the workspace is not corpus-complete. Test end-to-end indexing, mismatch, failure safety, curation preservation, and workspace isolation.
