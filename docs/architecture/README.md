# Architecture Rules

Cortex is a local, single-user, workspace-based application. Binding V1 decisions remain
in `codex-prompts/docs/DECISIONS.md`; this directory records their implementation-facing
interpretation. A public interface, schema, module ownership, folder layout, or runtime
workflow change must update the appropriate document here in the same change.

See `backend-foundation.md`, `deployment.md`, `retrieval-boundaries.md`,
`graphrag-boundary.md`, and `evaluation.md` before implementing their respective areas.

Query Architecture V2 is a binding **target** contract under [`query-v2/`](query-v2/README.md).
It is intentionally separate from the active V1 chat runtime documented in
[`query-answer-pipeline.md`](query-answer-pipeline.md). Phase 12 makes `/system-map` the manifest
of implemented V2 subsystem boundaries and contracts, while Phase 13 still owns full-generation
acceptance and sharp runtime cutover.

Phase 06 conversation-context persistence and schema-constrained semantic understanding are
implemented under `backend/app/query/` but are not connected to the active V1 chat entrypoint.
Accordingly, these boundaries appear in `/system-map` without claiming that V2 chat is active.
Phase 07 adds the versioned typed Logical Query IR, semantic lowering, governed workspace vocabulary,
and fail-closed DAG/type/coverage/evidence validation under the same inactive boundary. Physical
engine selection remains a later phase, so this also does not change the current System Map.
