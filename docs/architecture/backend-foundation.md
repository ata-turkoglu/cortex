# Backend Foundation

FastAPI OpenAPI is the API contract. SQLite uses WAL, foreign keys, a busy timeout,
bounded lock retry, and short transactions. LLM, embedding, network, and parsing calls do
not execute inside open transactions. Secrets never live as plaintext in SQLite or API
responses.

Uploads validate size, extension and MIME type; normalize filenames; prevent traversal;
use unique storage names and checksums; and return structured errors for unsupported,
corrupt, or encrypted files. Uploaded content is never executed.

An uploaded file is a source container. During DOCX normalization, Word heading levels are
reasserted in Markdown so every Word Heading 2 becomes exactly `##`. Markdown level-2 headings
are the only logical-document boundary signal; archive-code prefixes are never interpreted by
the splitter. Each `##` section creates a first-class `logical_documents` row before chunking,
using the heading text as its code and title and retaining its type, original source name, page
range, and normalized segment.
Chunks reference both the source container/version and their logical document; chunk adjacency
never crosses a logical-document boundary. Explicit DOCX page breaks are retained as page-range
metadata, while DOCX files without fixed page breaks leave page values unset.

V1 does not watch arbitrary external folders. Files enter only through upload or replacement
flows; a later re-upload is the mechanism for detecting changed source content. Duplicate
protection applies only to active document versions, so a completed soft-delete does not prevent
the same source content from being uploaded again.

Startup identifies stale running work; jobs become interrupted or resume from a safe
checkpoint. Deletions are idempotent workflows, and partial cleanup schedules reconciliation
across SQLite, Qdrant, bm25s, GraphRAG, NetworkX, uploads, normalized files, and caches.

Retrieval configuration is global in V1. Changing an embedding configuration creates one
durable dense-reindex request and prevents incompatible dense vectors from serving results until
the replacement index is ready. GraphRAG input, index execution, and output mirroring are split
so network/model work never runs while a SQLite transaction is open.
# Backend transaction boundaries

Database sessions are used only to snapshot or persist state. Upload validation commits its
database snapshot before Docling/file work; chat/provider, GraphRAG, Qdrant, and external
deletion cleanup run through worker-owned adapters after the session is closed. A failed
external deletion queues a durable reconciliation workflow rather than extending the original
transaction.

## Validation hardening

Alembic prepends the backend root to its import path, so the same fresh-database migration
command works from the local CLI and the container runtime. All FastAPI validation and handled
HTTP errors use the Cortex error envelope and preserve the response correlation ID; unexpected
errors remain sanitized server errors.
