# Phase 3 — Backend Foundation

## Goal

Create the FastAPI application, configuration system, provider abstractions, logging, health checks, and Docker services.

## Checklist

- [ ] Create FastAPI application with `/api/v1`.
- [ ] Configure Pydantic Settings.
- [ ] Configure structured JSON logging.
- [ ] Add correlation IDs for requests, jobs, and query runs.
- [ ] Configure SQLAlchemy 2.
- [ ] Configure Alembic.
- [ ] Configure Redis.
- [ ] Configure Dramatiq worker.
- [ ] Configure Qdrant client.
- [ ] Add provider interfaces for Ollama, OpenAI, and Anthropic.
- [ ] Add embedding provider interfaces for Ollama and OpenAI.
- [ ] Add model capability metadata and validation.
- [ ] Add secure credential storage/redaction behavior.
- [ ] Add health checks for backend, SQLite, Redis, worker, Qdrant, Ollama, OpenAI, Anthropic, and GraphRAG runtime.
- [ ] Add Dockerfiles.
- [ ] Add Docker Compose for frontend, backend, worker, redis, and qdrant.
- [ ] Configure host-mounted SQLite and data paths.
- [ ] Document host Ollama connectivity.
- [ ] Add backend unit tests.
- [ ] Update `IMPLEMENTATION_STATUS.md`.

## Acceptance criteria

- [ ] Docker Compose starts all required services.
- [ ] FastAPI health endpoint reports per-service status.
- [ ] Provider credentials never appear in API responses or logs.
- [ ] Alembic migration commands work.
- [ ] Backend tests pass.

## Additional checklist

- [ ] Pin Python, JavaScript, and Docker dependencies to exact versions.
- [ ] Configure SQLite WAL mode.
- [ ] Enable SQLite foreign keys.
- [ ] Configure SQLite busy timeout and bounded lock retries.
- [ ] Ensure no network/model operation runs inside a database transaction.
- [ ] Define standard Cortex API error envelope.
- [ ] Expose and validate OpenAPI schema.
- [ ] Add frontend client generation command from OpenAPI.
- [ ] Add graceful shutdown hooks.
- [ ] Add startup stale-job recovery hook.
- [ ] Add dependency-license check.

## Additional checklist — models, secrets, and Windows

- [ ] Implement secret-store abstraction.
- [ ] Implement Windows Credential Manager support or an equivalent secure OS-backed implementation.
- [ ] Implement environment-variable fallback.
- [ ] Add secret-redaction tests.
- [ ] Seed default model assignments with `gpt-5.6-luna`.
- [ ] Seed `qwen3-embedding:0.6b` as the default embedding model.
- [ ] Implement token and estimated-cost accounting.
- [ ] Implement daily/monthly soft budgets and warning thresholds.
- [ ] Implement Ollama installed-model discovery without model mutation.
- [ ] Add Windows host-path normalization and validation.
- [ ] Add `host.docker.internal` Ollama connectivity support.
- [ ] Configure the backend and worker to use the existing KnowledgeOS Ollama
      service at `http://host.docker.internal:11434` in Docker Desktop.
- [ ] Do not add a second Ollama service, model volume, or automatic model pull
      to Cortex Compose.
- [ ] Verify `/api/tags` and offer only installed models, including
      `qwen3:4b` and `bge-m3:latest` when present.

## Additional checklist — embedding provider readiness

- [ ] Configure Ollama `qwen3-embedding:0.6b` as the seeded embedding default.
- [ ] Detect whether the default embedding model is installed.
- [ ] Show, but do not execute, the required Ollama pull command.
- [ ] Implement embedding health checks for dimensions, finite values, normalization, and consistency.
- [ ] Capture Ollama model digest/details when available.
