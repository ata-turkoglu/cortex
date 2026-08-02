# Durable Workflows

LlamaIndex Workflows define ingestion, querying, reindexing, deletion, and maintenance;
Dramatiq and Redis execute background work while SQLite persists state. REST commands jobs
and SSE publishes progress. Workspace locks protect unsafe graph, reindex, and delete
operations. Workflow definitions are versioned in code and not user-editable in V1.
