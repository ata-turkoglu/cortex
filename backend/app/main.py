import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .api.health import router as health_router
from .api.settings import router as settings_router
from .api.workspaces import router as workspaces_router
from .api.uploads import router as uploads_router
from .core.errors import ErrorEnvelope
from .core.logging import configure_logging


@asynccontextmanager
async def lifespan(_: FastAPI):
    configure_logging()
    # Durable stale-job recovery is delegated to the worker before accepting new work.
    from .workers.broker import recover_stale_jobs

    try:
        recover_stale_jobs.send()
    except Exception:
        # Startup remains available when Redis is intentionally absent in unit tests.
        pass
    yield


app = FastAPI(
    title="Cortex API", version="0.1.0", openapi_url="/api/v1/openapi.json", lifespan=lifespan
)


@app.middleware("http")
async def correlation_id(request: Request, call_next):
    request.state.correlation_id = request.headers.get("X-Correlation-ID", str(uuid.uuid4()))
    response = await call_next(request)
    response.headers["X-Correlation-ID"] = request.state.correlation_id
    return response


@app.exception_handler(Exception)
async def unhandled(request: Request, _):
    body = ErrorEnvelope(
        code="internal_error",
        message="An unexpected error occurred.",
        correlation_id=getattr(request.state, "correlation_id", "unknown"),
    ).model_dump()
    return JSONResponse(status_code=500, content=body)


app.include_router(health_router, prefix="/api/v1")
app.include_router(settings_router, prefix="/api/v1")
app.include_router(workspaces_router, prefix="/api/v1")
app.include_router(uploads_router, prefix="/api/v1")
