# Canonical Knowledge Context

Read the root, `backend/AGENTS.md`, Query V2 invariants, and knowledge-construction contract. Choose
the smallest child boundary: `graph/`, `entities/`, `relations/`, `events/`, `temporal/`, `claims/`,
or `provenance/`. All knowledge is workspace-scoped, generation-aware, and provenance-bearing.

Use stable opaque IDs and preserve `user_curated > validated > extracted`. GraphRAG extraction is a
producer, not canonical truth; reindexing must not overwrite user curation.
