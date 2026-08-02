# Backend Context

Read root `AGENTS.md` first. This area will contain FastAPI, Pydantic v2, SQLAlchemy, and
Alembic code. Pydantic models define the REST/SSE contract, SQLite uses WAL with short
transactions, and no network/model call may run inside a database transaction.
