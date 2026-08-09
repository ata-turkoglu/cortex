import asyncio
import contextlib
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .api.catalog import router as catalog_router
from .api.chat import router as chat_router
from .api.graph import router as graph_router
from .api.health import router as health_router
from .api.ingestion_diagnostics import router as ingestion_diagnostics_router
from .api.settings import router as settings_router
from .api.uploads import router as uploads_router
from .api.workflows import router as workflows_router
from .api.workspaces import router as workspaces_router
from .core.errors import ErrorEnvelope
from .core.logging import configure_logging


@asynccontextmanager
async def lifespan(_: FastAPI):
    configure_logging()
    from .core.database import SessionLocal
    from .core.settings_service import load_runtime_settings

    session = SessionLocal()
    try:
        load_runtime_settings(session)
    except Exception:
        # The app can start before migrations have been applied.
        pass
    finally:
        session.close()
    # Durable stale-job recovery is delegated to the worker before accepting new work.
    from .workers.broker import recover_stale_jobs

    try:
        recover_stale_jobs.send()
    except Exception:
        # Startup remains available when Redis is intentionally absent in unit tests.
        pass

    async def maintenance_loop() -> None:
        from .workers.broker import reconcile_orphans

        while True:
            try:
                reconcile_orphans.send()
            except Exception:
                pass
            await asyncio.sleep(24 * 60 * 60)

    maintenance = asyncio.create_task(maintenance_loop())
    yield
    maintenance.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await maintenance
    # Stop accepting broker work before the API process exits. Actors checkpoint each step.
    from .workers.broker import broker

    try:
        broker.close()
    except Exception:
        pass


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


@app.exception_handler(HTTPException)
async def handled_http_exception(request: Request, exc: HTTPException):
    body = ErrorEnvelope(
        code="request_error",
        message=str(exc.detail),
        correlation_id=getattr(request.state, "correlation_id", "unknown"),
    ).model_dump()
    return JSONResponse(status_code=exc.status_code, content=body, headers=exc.headers)


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, _: RequestValidationError):
    body = ErrorEnvelope(
        code="validation_error",
        message="The request is invalid.",
        correlation_id=getattr(request.state, "correlation_id", "unknown"),
    ).model_dump()
    return JSONResponse(status_code=422, content=body)


app.include_router(health_router, prefix="/api/v1")
app.include_router(settings_router, prefix="/api/v1")
app.include_router(workspaces_router, prefix="/api/v1")
app.include_router(catalog_router, prefix="/api/v1")
app.include_router(graph_router, prefix="/api/v1")
app.include_router(uploads_router, prefix="/api/v1")
app.include_router(workflows_router, prefix="/api/v1")
app.include_router(chat_router, prefix="/api/v1")
app.include_router(ingestion_diagnostics_router, prefix="/api/v1")
