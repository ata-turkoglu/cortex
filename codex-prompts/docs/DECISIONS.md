# Cortex V1 Architecture Decisions

This file is binding for V1.

## Product

- Cortex is local, single-user, and workspace-based.
- No authentication or multi-user permissions in V1.
- No workspace setting overrides in V1.
- No backup/restore in V1.
- No web search in V1.
- No external connectors in V1.

## Workspace and database

- One SQLite database.
- `workspaces` is the root entity.
- All workspace-scoped tables reference `workspace_id`.
- A custom `WorkspaceContext` resolves:
  - workspace record,
  - Qdrant resource mappings,
  - graph namespace/path,
  - cache namespace/path,
  - upload and normalized-document paths,
  - active job and index state.
- Resource mappings are stored through `workspace_resources` or equivalent normalized tables.
- Do not hard-code resource names in feature services.

## Qdrant

- Use shared collections by resource type.
- Every point has `workspace_id`.
- Every query and delete operation must include a workspace filter.
- Create payload indexes for frequently filtered fields such as:
  - `workspace_id`
  - `document_id`
  - `document_version_id`
  - `folder_id`
  - selected metadata fields
- Use deterministic point IDs.
- Active indexes are updated in place.
- If embedding dimensions change, use a safe same-collection migration strategy and disable inconsistent search during reindexing.

## Graph

- Microsoft GraphRAG is used for graph indexing and Local, Global, and DRIFT query engines.
- The GraphRAG knowledge model is canonical.
- NetworkX is secondary and used for visualization, traversal, and analysis.
- Each workspace has an isolated GraphRAG root directory.
- Cortex chunks and GraphRAG text units are separate in V1.
- GraphRAG updates may be deferred and batched.
- The pending-document threshold is configurable in Settings.
- Hybrid Search becomes available before GraphRAG indexing finishes.
- Stale graph behavior follows Settings and safe fallback rules.

## Retrieval

- LlamaIndex is the primary RAG/query framework.
- LlamaIndex Workflows are used instead of deprecated QueryPipeline patterns.
- LlamaIndex Router selects:
  - Hybrid Search
  - GraphRAG Local
  - GraphRAG Global
  - GraphRAG DRIFT
  - approved multi-route combinations
- GraphRAG is integrated as independent query engines/tools, not flattened into a basic retriever.
- Hybrid Search uses:
  - Qdrant dense retrieval
  - bm25s sparse retrieval
  - fusion
  - local BGE reranker
- Evidence is normalized into a common Cortex evidence model.
- Answers support grounded, partial, and unsupported states.
- Factual claims require citations.
- Document-grounded inference must be labeled.

## Models

- LLM providers:
  - Ollama
  - OpenAI
  - Anthropic
- Embedding providers:
  - Ollama
  - OpenAI
- Local reranker only.
- Every LLM-using layer has an independent provider/model assignment.
- Model capabilities are validated before assignment.
- Secrets are stored securely and never returned in plaintext.
- Global settings control all workspaces in V1.

## Workflows and jobs

- LlamaIndex Workflows define ingestion, query, reindex, and maintenance flows.
- Dramatiq + Redis execute background jobs.
- SQLite stores durable workflow state.
- REST creates, cancels, retries, and reads jobs.
- SSE publishes live progress.
- Safe cancellation occurs after an atomic step or batch.
- Retry continues from the failed step.
- Steps must be idempotent.
- Query runs are stored separately from long-running workflow runs.
- Stage-specific concurrency limits are configurable.
- Workspace locks prevent unsafe concurrent graph/reindex/delete operations.
- Workflow definitions are versioned in code, not user-editable in V1.

## UI

- React + Vite + TypeScript.
- Tailwind + PrimeReact + lucide-react.
- React Flow for system and process maps.
- All main UI primitives use Cortex abstractions.
- PrimeReact does not leak into feature modules.
- lucide-react does not leak outside icon abstraction.
- System map and live process map are separate views.
- Layout is Sidebar + Header + Content.
- Sidebar is collapsed by default.
- Header shows active background work.
- Theme and appearance are configurable from Settings.

## Errors

- Show a concise user-facing error.
- Provide a button to reveal sanitized technical details.
- Technical details may include traceback, correlation ID, error code, workflow step, model/provider, job ID, and retry count.
- Redact secrets and authorization data.

## Document lifecycle

- Store original source files.
- Store normalized Markdown separately.
- Supported V1 formats:
  - Markdown
  - plain text
  - DOCX
  - PDF
- Use Docling for parsing.
- Documents and document versions are separate.
- Duplicate detection uses file and normalized-content hashes.
- Soft delete by default.
- Citations reference document versions.

## Docker

- Docker Compose services:
  - frontend
  - backend
  - worker
  - redis
  - qdrant
- SQLite and data directories are host-mounted.
- Ollama may remain on the host.
- The existing Ollama runtime is owned by the KnowledgeOS Compose stack at
  `D:\Merter\KnowledgeOS` and is shared by both projects.
- Cortex connects to it with `http://host.docker.internal:11434` from Docker
  Desktop, or `http://localhost:11434` when running directly on the host.
- Cortex backend and worker must receive the same `OLLAMA_BASE_URL`.
- Do not define a second Ollama container, duplicate model files, or share the
  `ollama-data` volume between separate Ollama containers.
- If a future root Compose file combines both projects, use one Ollama service
  and `OLLAMA_BASE_URL=http://ollama:11434`.

## Dependency and version policy

- All dependencies and Docker images are pinned to exact versions.
- Floating versions and `latest` tags are prohibited.
- Upgrades require test, integration, and evaluation runs.
- Index runs record relevant dependency/model/configuration versions.

## API contract and frontend client

- FastAPI OpenAPI is the canonical API contract.
- Frontend request/response types are generated from OpenAPI.
- Manual duplication of API DTOs in feature code is prohibited.
- All API errors use a consistent Cortex error envelope.

## SQLite concurrency

- SQLite uses WAL mode.
- Foreign-key enforcement is enabled.
- Busy timeout and bounded lock retries are configured.
- Transactions remain short.
- Network/model operations never run inside open database transactions.

## File security

- Upload limits and allowed formats are configurable.
- Extension and MIME/content validation are both required.
- Paths and filenames are normalized safely.
- Path traversal is blocked.
- Corrupt, encrypted, password-protected, and unsupported files return structured errors.
- Uploaded content is never executed.

## GraphRAG–Qdrant integration

- Implement through a dedicated adapter module.
- Treat adapter compatibility as a separately tested boundary.
- Keep GraphRAG vector resource types separated.
- Validate workspace isolation and Local/Global/DRIFT behavior.

## Performance and scale

- Target approximately 5,000 files.
- Use server-side pagination and virtualization for large data sets.
- Operational batch and concurrency values come from Settings.
- Record benchmark results for ingestion, retrieval, GraphRAG, memory, and storage.

## Source file updates

- V1 has no external file watcher.
- File changes enter through Cortex upload/update flows.
- Re-upload and replace operations use hashes and document versioning.

## Crash recovery

- Startup detects stale running jobs.
- Jobs become interrupted or resume from a safe checkpoint.
- Graceful shutdown prevents unsafe partial state.
- Recovery state is visible in UI.

## Deletion and reconciliation

- Deletion is an idempotent workflow.
- Partial cleanup creates a reconciliation job.
- Periodic orphan reconciliation checks all stores.

## Licensing

- Maintain `THIRD_PARTY_NOTICES.md`.
- Add dependency-license validation where practical.

## Default model and cost profile

- The target machine cannot rely on `qwen3:4b` for production-quality Cortex tasks.
- OpenAI is the default production provider.
- `gpt-5.6-luna` is the default model for routing, metadata, summaries, GraphRAG extraction/summarization, and answer generation.
- `qwen3-embedding:0.6b` through Ollama is the default embedding model.
- The BGE reranker remains local.
- More expensive models are opt-in and never selected silently.
- Query expansion and automatic GraphRAG updates are disabled by default.
- Batch processing is preferred for eligible non-interactive LLM workloads.
- Token usage and estimated costs are persisted and shown to the user.

## First-run setup

- A setup wizard validates services, provider credentials, embeddings, model assignments, and cost controls.
- Ollama is optional.
- Setup can be reopened later.

## Secret storage

- API keys are not stored as plaintext in SQLite.
- Use an OS credential-store abstraction where supported.
- Environment variables are supported for development and Docker.
- Secrets are never returned by APIs and are redacted everywhere.

## Ollama

- Cortex lists installed models but does not download or delete them.
- Small local models may be offered as experimental/offline options only.
- No Ollama chat model is a production default.
- Discover installed models through `/api/tags`; do not assume that the
  build-pack example `qwen3-embedding:0.6b` is installed.
- The current KnowledgeOS defaults are expected to be `qwen3:4b` for chat and
  `bge-m3:latest` for embeddings, subject to discovery at runtime.

## Windows

- Windows 11 + Docker Desktop + WSL2 is a primary supported environment.
- Validate Windows paths, Turkish filenames, spaces, host mounts, and `host.docker.internal`.
- Host data path is configurable.

## Evaluation

- Evaluation fixtures use a versioned schema.
- Include route, document, fact, evidence, answerability, cost, and latency expectations.
- Synthetic fixtures are included; real verified fixtures are supplied later from actual documents.

## Embedding default

- Default provider: Ollama.
- Default model: `qwen3-embedding:0.6b`.
- This is separate from the underperforming `qwen3:4b` chat model.
- `bge-m3:567m` is an optional multilingual alternative.
- OpenAI embeddings remain optional.
- Embedding model/configuration changes require dense reindexing.
- Model-specific formatting is isolated in an embedding adapter.
- Qdrant rejects dimension/configuration mismatches before writes.
- Setup includes multilingual and Turkish embedding health checks.
