# Dependency layers are built once and copied into clean API and worker targets.
# Runtime data is always supplied through the Compose /data mount, never the image.
FROM ghcr.io/astral-sh/uv:0.12.1 AS uv

FROM python:3.11.11-slim AS python-base
WORKDIR /app/backend
COPY --from=uv /uv /uvx /bin/
ENV UV_COMPILE_BYTECODE=1 \
    UV_HTTP_TIMEOUT=1800 \
    UV_HTTP_RETRIES=5 \
    UV_CONCURRENT_DOWNLOADS=1 \
    UV_LINK_MODE=copy \
    PIP_NO_CACHE_DIR=1
COPY backend/pyproject.toml backend/uv.lock ./

# The worker extends the API dependency environment, so the query dependency layer
# is cached and shared while each final target receives only its finished virtualenv.
FROM python-base AS query-deps
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --group query --no-install-project

FROM query-deps AS backend-builder
COPY backend/alembic.ini ./
COPY backend/alembic ./alembic
COPY backend/app ./app
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --group query --no-editable

FROM query-deps AS worker-deps
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --group query --group retrieval --group graphrag --no-install-project

FROM worker-deps AS worker-builder
COPY backend/alembic.ini ./
COPY backend/alembic ./alembic
COPY backend/app ./app
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --group query --group retrieval --group graphrag --no-editable

FROM python:3.11.11-slim AS runtime-base
WORKDIR /app/backend
COPY --from=uv /uv /uvx /bin/
ENV PATH="/app/backend/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

FROM runtime-base AS runtime
COPY --from=backend-builder /app/backend/.venv ./.venv
COPY --from=backend-builder /app/backend/alembic.ini ./
COPY --from=backend-builder /app/backend/alembic ./alembic
COPY --from=backend-builder /app/backend/app ./app
CMD ["sh", "-c", "alembic upgrade head && exec uv run --frozen --no-sync uvicorn app.main:app --host 0.0.0.0 --port 8000"]

FROM runtime-base AS worker
COPY --from=worker-builder /app/backend/.venv ./.venv
COPY --from=worker-builder /app/backend/alembic.ini ./
COPY --from=worker-builder /app/backend/alembic ./alembic
COPY --from=worker-builder /app/backend/app ./app
CMD ["uv", "run", "--frozen", "--no-sync", "dramatiq", "app.workers"]
