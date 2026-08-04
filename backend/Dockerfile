FROM ghcr.io/astral-sh/uv:0.12.1 AS uv

FROM python:3.11.11-slim AS lock-runner
COPY --from=uv /uv /uvx /bin/
WORKDIR /work

FROM python:3.11.11-slim AS runtime
WORKDIR /app
COPY --from=uv /uv /uvx /bin/
COPY backend/pyproject.toml backend/uv.lock /app/backend/
WORKDIR /app/backend
RUN uv sync --frozen --no-dev --group query --no-install-project
COPY backend /app/backend
CMD ["uv", "run", "--frozen", "--no-sync", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

# GraphRAG is worker-only. Its upstream package requires LanceDB transitively even
# though Cortex uses Qdrant exclusively for its own vector-store boundary.
FROM runtime AS worker
RUN uv sync --frozen --no-dev --group query --group retrieval --group graphrag --no-install-project
