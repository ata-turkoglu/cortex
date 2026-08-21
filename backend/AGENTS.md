# Backend Context

Read root `AGENTS.md` first. This area will contain FastAPI, Pydantic v2, SQLAlchemy, and
Alembic code. Pydantic models define the REST/SSE contract, SQLite uses WAL with short
transactions, and no network/model call may run inside a database transaction.

For Query Architecture V2, enter the smallest owning boundary before reading code:

- `app/query/` — conversation context, semantic understanding, logical IR, planning, orchestration
- `app/knowledge/` — canonical entities, relations, events, temporal data, claims, provenance
- `app/engines/` — structured/graph/hybrid coordination; existing retrieval and GraphRAG adapters
  remain in `app/retrieval/` and `app/graphrag/`
- `app/reasoning/` — durable research and composition

These directories are target ownership boundaries until their implementation phases activate them.
The V1 runtime remains under `app/chat/`, `app/aggregation/`, `app/retrieval/`, and `app/graphrag/`;
do not duplicate those implementations during migration.
