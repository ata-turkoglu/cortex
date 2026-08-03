FROM ghcr.io/astral-sh/uv:0.12.1 AS uv

FROM python:3.11.11-slim AS lock-runner
COPY --from=uv /uv /uvx /bin/
WORKDIR /work

FROM python:3.11.11-slim
WORKDIR /app
COPY --from=uv /uv /uvx /bin/
COPY backend/pyproject.toml backend/uv.lock /app/backend/
WORKDIR /app/backend
RUN uv sync --frozen --no-dev --group graphrag --no-install-project --no-build
COPY backend /app/backend
CMD ["uv", "run", "--frozen", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
