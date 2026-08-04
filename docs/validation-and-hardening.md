# Phase 10 validation and hardening

## Completed checks

- Backend: `uv run ruff check app tests alembic`, `uv run pytest -q -p no:cacheprovider`,
  and `CORTEX_DATABASE_URL=sqlite:///:memory: uv run alembic -c alembic.ini upgrade head`.
  Result: lint passed, 77 tests passed, and a fresh SQLite migration completed.
- Frontend: `corepack pnpm test`, `corepack pnpm build`, and `corepack pnpm lint` from
  `frontend`. Result: 5 tests passed; type-check/build/lint passed. Vite reports a non-blocking
  667 kB JavaScript chunk advisory.
- Context and license inventory: `python scripts/ai-context/validate-context.py`,
  `python scripts/ai-context/check-context-freshness.py`, and
  `python scripts/license-report.py`.
- The generated OpenAPI schema is contract-tested in the backend suite. API validation and
  handled HTTP errors now return the standard Cortex envelope with a correlation ID.

## Docker Compose follow-up

`docker compose -f infrastructure/docker-compose.yml config` validates. The frontend service
command was corrected to run from its configured `/app/frontend` working directory. On
2026-08-03, `docker compose -f infrastructure/docker-compose.yml up -d --no-build` started
frontend, backend, worker, Redis, and Qdrant successfully; the frontend returned HTTP 200 and
the backend health map reported all required services healthy. The worker was then restarted and
the backend remained healthy. `python scripts/api/generate-client.py` regenerated the OpenAPI
schema from the live backend.

Phase 10 is complete. The representative benchmark, lifecycle coverage, and browser-level
Playwright checks are all recorded below.

The representative 5,000-document chunking benchmark is a deterministic regression guard for
the first ingestion boundary; its test budget is ten seconds on the target development machine.
It complements, rather than replaces, a future full-service ingestion-throughput benchmark.

The frontend virtual-list regression renders a 5,000-item list but materializes only its visible
overscanned window; paginated chat messages are constrained server-side by the API limit/offset
contract.

Playwright 1.51.1 Chromium validation passed against the live Compose frontend: the dashboard
and Processes routes loaded successfully. Browser binaries are intentionally installed outside
the repository in Playwright's managed cache.

Upload hardening coverage accepts supported PDF/DOCX signatures before worker parsing and asserts
structured failures for corrupt PDF/DOCX and encrypted-PDF-shaped fixtures, alongside size, MIME,
extension, and path-traversal rejection.

The workflow SSE integration test uses a real FastAPI route and SQLite state machine. It creates
a workspace and workflow, completes the workflow, records the last event ID, and verifies that a
`Last-Event-ID` reconnect receives the terminal `completed` state.

The application lifespan test verifies that the broker is closed during graceful shutdown.
Evaluation fixtures now use a versioned schema covering route, workspace, document, fact,
evidence, answerability, latency, and estimated-cost expectations.

## Final validation — 2026-08-04

- Backend lint and the complete suite passed: 93 tests. A fresh in-memory SQLite migration also
  passed.
- Frontend unit tests (6), production type-check/build, lint, and live Compose Playwright tests
  (2) passed.
- Compose is healthy for backend, SQLite, Redis, Qdrant, and worker. Ollama and remote providers
  correctly report unavailable/not configured until the user supplies their optional runtime
  configuration.
- The API image has no GraphRAG package; the worker image has both Microsoft GraphRAG and its
  upstream-required LanceDB dependency. Cortex itself continues to use Qdrant exclusively.
- OpenAPI TypeScript generation, dependency-lock validation, AI-context generation/validation/
  freshness, and license inventory generation passed.

The Playwright navigation regression intercepts the workflow REST response and verifies that an
active ingestion workflow is restored after Processes → Dashboard → Processes navigation.
