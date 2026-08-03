# Phase 3 — Backend Foundation

## Goal

Create the FastAPI application, configuration system, provider abstractions, logging, health checks, and Docker services.

## Checklist

- [x] Create FastAPI application with `/api/v1`.
- [x] Configure Pydantic Settings.
- [x] Configure structured JSON logging.
- [x] Add correlation IDs for requests, jobs, and query runs.
- [x] Configure SQLAlchemy 2.
- [x] Configure Alembic.
- [x] Configure Redis.
- [x] Configure Dramatiq worker.
- [x] Configure Qdrant client.
- [x] Add provider interfaces for Ollama, OpenAI, and Anthropic.
- [x] Add embedding provider interfaces for Ollama and OpenAI.
- [x] Add model capability metadata and validation.
- [x] Add secure credential storage/redaction behavior.
- [x] Add health checks for backend, SQLite, Redis, worker, Qdrant, Ollama, OpenAI, Anthropic, and GraphRAG runtime.
- [x] Add Dockerfiles.
- [x] Add Docker Compose for frontend, backend, worker, redis, and qdrant.
- [x] Configure host-mounted SQLite and data paths.
- [x] Document host Ollama connectivity.
- [x] Add backend unit tests.
- [x] Update `IMPLEMENTATION_STATUS.md`.

## Acceptance criteria

- [x] Docker Compose starts all required services.
- [x] FastAPI health endpoint reports per-service status.
- [x] Provider credentials never appear in API responses or logs.
- [x] Alembic migration commands work.
- [x] Backend tests pass.

## Additional checklist

- [x] Pin Python, JavaScript, and Docker dependencies to exact versions.
- [x] Configure SQLite WAL mode.
- [x] Enable SQLite foreign keys.
- [x] Configure SQLite busy timeout and bounded lock retries.
- [x] Ensure no network/model operation runs inside a database transaction.
- [x] Define standard Cortex API error envelope.
- [x] Expose and validate OpenAPI schema.
- [x] Add frontend client generation command from OpenAPI.
- [x] Add graceful shutdown hooks.
- [x] Add startup stale-job recovery hook.
- [x] Add dependency-license check.

## Additional checklist — models, secrets, and Windows

- [x] Implement secret-store abstraction.
- [x] Implement Windows Credential Manager support or an equivalent secure OS-backed implementation.
- [x] Implement environment-variable fallback.
- [x] Add secret-redaction tests.
- [x] Seed default model assignments with `gpt-5.6-luna`.
- [x] Seed `qwen3-embedding:0.6b` as the default embedding model.
- [x] Implement token and estimated-cost accounting.
- [x] Implement daily/monthly soft budgets and warning thresholds.
- [x] Implement Ollama installed-model discovery without model mutation.
- [x] Add Windows host-path normalization and validation.
- [x] Add `host.docker.internal` Ollama connectivity support.
- [x] Configure the backend and worker to use the existing KnowledgeOS Ollama
      service at `http://host.docker.internal:11434` in Docker Desktop.
- [x] Do not add a second Ollama service, model volume, or automatic model pull
      to Cortex Compose.
- [x] Verify `/api/tags` and offer only installed models, including
      `qwen3:4b` and `bge-m3:latest` when present.

## Additional checklist — embedding provider readiness

- [x] Configure Ollama `qwen3-embedding:0.6b` as the seeded embedding default.
- [x] Detect whether the default embedding model is installed.
- [x] Show, but do not execute, the required Ollama pull command.
- [x] Implement embedding health checks for dimensions, finite values, normalization, and consistency.
- [x] Capture Ollama model digest/details when available.
