# Workflow Context

Read root and backend instructions first. Durable workflow state lives in SQLite and jobs
run through Dramatiq/Redis. Steps are idempotent, cancellation occurs only at safe
boundaries, and restart recovery must make interrupted work visible.
