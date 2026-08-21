# Phase 13 — Full V2 Reindex & Sharp Cutover

## Goal

Move workspaces to V2 knowledge/index architecture through a full rebuild, without long-lived V1/V2 dual execution.

```text
schema/config migration → Neo4j ready → V2 generation → source reprocessing → entity/mention
→ identity → relation/event/temporal/claim → canonical KG → BM25 → dense → GraphRAG
→ completeness → evaluation → activate V2
```

Reindexing preserves user-curated merges/splits/aliases/knowledge. Keep the prior active generation until successful activation; never activate a failed partial generation. Test full rebuild, same-generation readiness, failure safety, curation persistence, and sharp cutover.
