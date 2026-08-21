# Query Engine Context

Read the root, `backend/AGENTS.md`, Query V2 runtime contract, and invariants. Use `structured/`,
`graph/`, or `hybrid/` for new engine coordination. Existing Retrieval Engine implementation stays
in `app/retrieval/`; existing Microsoft GraphRAG implementation stays in `app/graphrag/`. Do not
create duplicate `engines/retrieval` or `engines/graphrag` packages.

All engines consume typed plan inputs and emit typed results to Result & Evidence. They never
author or persist the final assistant answer.
