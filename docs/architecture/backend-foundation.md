# Backend Foundation

FastAPI OpenAPI is the API contract. SQLite uses WAL, foreign keys, a busy timeout,
bounded lock retry, and short transactions. LLM, embedding, network, and parsing calls do
not execute inside open transactions. Secrets never live as plaintext in SQLite or API
responses.

Uploads validate size, extension and MIME type; normalize filenames; prevent traversal;
use unique storage names and checksums; and return structured errors for unsupported,
corrupt, or encrypted files. Uploaded content is never executed.

Startup identifies stale running work; jobs become interrupted or resume from a safe
checkpoint. Deletions are idempotent workflows, and partial cleanup schedules reconciliation
across SQLite, Qdrant, bm25s, GraphRAG, NetworkX, uploads, normalized files, and caches.
