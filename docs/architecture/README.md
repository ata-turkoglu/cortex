# Architecture Rules

Cortex is a local, single-user, workspace-based application. Binding product decisions remain
in `codex-prompts/docs/DECISIONS.md`; this directory records their implementation-facing
interpretation. A public interface, schema, module ownership, folder layout, or runtime
workflow change must update the appropriate document here in the same change.

See `backend-foundation.md`, `deployment.md`, `retrieval-boundaries.md`,
`graphrag-boundary.md`, and `evaluation.md` before implementing their respective areas.

[`CANONICAL_CORE_V2.md`](CANONICAL_CORE_V2.md) is the proposed, implementation-ready minimal
canonical authority/readiness design for the first exhaustive Person/property capability. It does
not represent implemented or production-accepted canonical functionality.

Query Architecture V2 under [`query-v2/`](query-v2/README.md) is the active production runtime.
`POST /chat` enters `backend/app/query/production_chat.py`; it does not call the historical V1
orchestration in `backend/app/chat/`. `/system-map` is the current V2 topology and must show the
separate readiness of `retrieval.grounded`, `graphrag.grounded`, `canonical.exhaustive`, and
`canonical.graph`.

The V2 retrieval path is production-accepted. Canonical structured and graph capabilities remain
blocked pending separate acceptance; Neo4j must not be described as fully proven durable canonical
authority. See [`V1_CLEANUP_REVIEW.md`](V1_CLEANUP_REVIEW.md) for preserved legacy/compatibility code.
