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

Production query execution enters through `app/api/chat.py` and `app/query/production_chat.py`.
`app/retrieval/` and `app/graphrag/` remain active V2 adapter boundaries. `app/chat/` and
`app/aggregation/` contain historical or compatibility code; do not route production V2 requests
through them or delete them without proving that workers, evaluation, and persisted compatibility
do not require them.
