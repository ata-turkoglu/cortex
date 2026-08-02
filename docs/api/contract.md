# API Contract

FastAPI OpenAPI is canonical. All REST and SSE request/response models use Pydantic; the
frontend consumes generated TypeScript client types rather than manually duplicated DTOs.
Errors use `code`, `message`, `correlation_id`, `details_available`, and optional sanitized
`details`. Contract or schema changes require regenerating the client and updating this
document and its tests.

Workspace CRUD is exposed at `/api/v1/workspaces`. Creation atomically seeds resource and
index-state records. Deletion is a soft delete; cross-store cleanup is deferred to the
idempotent deletion workflow.
