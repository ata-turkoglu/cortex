import json
from datetime import UTC, datetime
from typing import Annotated, Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..core.secrets import SecretStore
from ..core.settings_service import PERSISTED_FIELDS, load_runtime_settings, save_settings
from ..models import ProviderConnection, SetupState, WorkflowRun
from ..providers.anthropic import AnthropicProvider
from ..providers.catalog import DEFAULT_MODELS
from ..providers.embeddings import OllamaEmbeddingAdapter
from ..providers.ollama import OllamaProvider
from ..providers.openai import OpenAIProvider
from .workspaces import get_session

router = APIRouter(tags=["settings"])


Provider = Literal["openai", "anthropic", "ollama"]


class SettingsUpdate(BaseModel):
    embedding_change_confirmed: bool = False
    upload_max_bytes: int | None = Field(default=None, ge=1)
    chunk_token_limit: int | None = Field(default=None, ge=32)
    chunk_overlap_tokens: int | None = Field(default=None, ge=0)
    embedding_provider: Provider | None = None
    embedding_model: str | None = Field(default=None, min_length=1)
    embedding_batch_size: int | None = Field(default=None, ge=1)
    embedding_timeout_seconds: int | None = Field(default=None, ge=1)
    embedding_keep_alive: str | None = Field(default=None, min_length=1)
    embedding_concurrency: int | None = Field(default=None, ge=1)
    dense_top_k: int | None = Field(default=None, ge=1)
    bm25_top_k: int | None = Field(default=None, ge=1)
    fusion_candidate_limit: int | None = Field(default=None, ge=1)
    reranker_input_limit: int | None = Field(default=None, ge=1)
    final_evidence_top_k: int | None = Field(default=None, ge=1)
    router_confidence_threshold: float | None = Field(default=None, ge=0, le=1)
    router_multi_route_threshold: float | None = Field(default=None, ge=0, le=1)
    graphrag_pending_document_threshold: int | None = Field(default=None, ge=1)
    graphrag_update_mode: Literal["manual", "threshold"] | None = None
    workflow_ingestion_concurrency: int | None = Field(default=None, ge=1)
    workflow_dense_reindex_concurrency: int | None = Field(default=None, ge=1)
    workflow_graphrag_reindex_concurrency: int | None = Field(default=None, ge=1)
    workflow_deletion_concurrency: int | None = Field(default=None, ge=1)
    workflow_retention_days: int | None = Field(default=None, ge=1)
    workflow_retry_limit: int | None = Field(default=None, ge=0)
    workflow_retry_backoff_seconds: int | None = Field(default=None, ge=0)
    workflow_timeout_seconds: int | None = Field(default=None, ge=1)
    default_page_size: int | None = Field(default=None, ge=1, le=500)
    health_check_interval_seconds: int | None = Field(default=None, ge=1)
    sse_reconnect_interval_seconds: int | None = Field(default=None, ge=1)
    conversation_memory_window_messages: int | None = Field(default=None, ge=1)
    answer_style: Literal["concise", "balanced", "detailed"] | None = None
    grounding_required: bool | None = None
    metadata_provider: Provider | None = None
    metadata_model: str | None = None
    answer_provider: Provider | None = None
    answer_model: str | None = None
    router_provider: Provider | None = None
    router_model: str | None = None
    summary_provider: Provider | None = None
    summary_model: str | None = None
    daily_soft_budget_usd: float | None = Field(default=None, ge=0)
    monthly_soft_budget_usd: float | None = Field(default=None, ge=0)
    budget_warning_percent: int | None = Field(default=None, ge=1, le=100)

    @model_validator(mode="after")
    def valid_chunking(self):
        if (
            self.chunk_token_limit is not None
            and self.chunk_overlap_tokens is not None
            and self.chunk_overlap_tokens >= self.chunk_token_limit
        ):
            raise ValueError("chunk_overlap_tokens must be smaller than chunk_token_limit")
        return self


class ProviderValidationRequest(BaseModel):
    api_key: str | None = Field(default=None, min_length=1)


class SetupCompleteRequest(BaseModel):
    data_path: str | None = None


async def _capabilities() -> dict[str, list[object]]:
    try:
        ollama = await OllamaProvider().list_models()
    except Exception:
        ollama = []
    return {
        "openai": await OpenAIProvider().list_models(),
        "anthropic": await AnthropicProvider().list_models(),
        "ollama": ollama,
    }


async def _validate_assignments(patch: dict[str, object]) -> None:
    capabilities = await _capabilities()
    for layer in ("embedding", "metadata", "answer", "router", "summary"):
        provider, model = patch.get(f"{layer}_provider"), patch.get(f"{layer}_model")
        if not provider and not model:
            continue
        provider = provider or getattr(get_settings(), f"{layer}_provider")
        model = model or getattr(get_settings(), f"{layer}_model")
        matches = [item for item in capabilities[provider] if item.model == model]
        if not matches:
            raise HTTPException(422, f"{provider}/{model} is unavailable for {layer}")
        capability = matches[0]
        required = "embeddings" if layer == "embedding" else "chat"
        if not getattr(capability, required):
            raise HTTPException(422, f"{provider}/{model} lacks {required} capability for {layer}")


@router.get("/settings")
def read_settings(session: Annotated[Session, Depends(get_session)]):
    return {"settings": load_runtime_settings(session), "global_only": True}


@router.put("/settings")
async def update_settings(
    payload: SettingsUpdate, session: Annotated[Session, Depends(get_session)]
):
    patch = payload.model_dump(exclude_none=True)
    confirmed = bool(patch.pop("embedding_change_confirmed", False))
    current = get_settings()
    embedding_changed = any(
        name in patch and patch[name] != getattr(current, name)
        for name in ("embedding_provider", "embedding_model")
    )
    if embedding_changed and not confirmed:
        raise HTTPException(
            409, "embedding configuration changes require explicit reindex confirmation"
        )
    await _validate_assignments(patch)
    try:
        values, reindex_required = save_settings(session, patch)
        session.commit()
    except ValueError as exc:
        session.rollback()
        raise HTTPException(422, str(exc)) from exc
    return {"settings": values, "reindex_required": reindex_required}


@router.post("/settings/reset-defaults")
def reset_defaults(session: Annotated[Session, Depends(get_session)]):
    defaults = get_settings().__class__().model_dump()
    safe_defaults = {name: value for name, value in defaults.items() if name in PERSISTED_FIELDS}
    values, reindex_required = save_settings(session, safe_defaults)
    return {"settings": values, "reindex_required": reindex_required}


@router.get("/settings/diagnostics")
def diagnostics(session: Annotated[Session, Depends(get_session)]):
    counts = dict(
        session.execute(select(WorkflowRun.state, func.count()).group_by(WorkflowRun.state)).all()
    )
    return {
        "windows": {
            "data_path": str(get_settings().data_path),
            "ollama_base_url": get_settings().ollama_base_url,
        },
        "workflows": {
            "interrupted": counts.get("interrupted", 0),
            "repairing": counts.get("repairing", 0),
            "failed": counts.get("failed", 0),
        },
        "reconciliation": {
            "state": "not-scheduled",
            "message": "No reconciliation workflow is currently running.",
        },
    }


@router.get("/settings/graphrag/estimate")
def graphrag_estimate():
    settings = get_settings()
    return {
        "update_mode": settings.graphrag_update_mode,
        "pending_document_threshold": settings.graphrag_pending_document_threshold,
        "confirmation_threshold_usd": settings.graphrag_cost_warning_usd,
        "requires_confirmation": settings.graphrag_cost_warning_usd > 0,
    }


@router.post("/settings/providers/{provider}/validate")
async def validate_provider(
    provider: Provider,
    payload: ProviderValidationRequest,
    session: Annotated[Session, Depends(get_session)],
):
    if payload.api_key:
        SecretStore().set(f"{provider}_api_key", payload.api_key)
    if provider == "ollama":
        try:
            await OllamaProvider().list_models()
            status = "available"
        except Exception:
            status = "unavailable"
    elif provider == "openai" and payload.api_key:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.get(
                    "https://api.openai.com/v1/models",
                    headers={"Authorization": f"Bearer {payload.api_key}"},
                )
                response.raise_for_status()
            status = "configured"
        except httpx.HTTPError:
            status = "invalid"
    else:
        configured = bool(payload.api_key) or bool(
            getattr(get_settings(), f"{provider}_api_key", None)
        )
        status = "configured" if configured else "not-configured"
    now = datetime.now(UTC)
    record = session.get(ProviderConnection, provider)
    value = json.dumps({"status": status, "validated_at": now.isoformat()})
    if record:
        record.validation_json, record.updated_at = value, now
    else:
        session.add(ProviderConnection(provider=provider, validation_json=value, updated_at=now))
    return {"provider": provider, "status": status}


@router.post("/settings/embedding/health")
async def embedding_health():
    settings = get_settings()
    if settings.embedding_provider != "ollama":
        raise HTTPException(
            422, "only the configured Ollama embedding adapter supports this health test"
        )
    result = await OllamaEmbeddingAdapter().health_check()
    return result.__dict__


@router.get("/settings/embedding/status")
async def embedding_status():
    settings = get_settings()
    try:
        models = await OllamaProvider().list_models()
    except Exception:
        models = []
    installed = next((model for model in models if model.model == settings.embedding_model), None)
    return {
        "provider": settings.embedding_provider,
        "model": settings.embedding_model,
        "installed": installed is not None,
        "dimension": None,
        "model_digest": None,
        "last_benchmark": None,
        "requires_full_reindex": True,
    }


@router.post("/settings/setup/complete")
def complete_setup(
    payload: SetupCompleteRequest, session: Annotated[Session, Depends(get_session)]
):
    now = datetime.now(UTC)
    state = {"data_path": payload.data_path, "completed": True}
    row = session.get(SetupState, 1)
    if row:
        row.completed_at, row.state_json, row.updated_at = now, json.dumps(state), now
    else:
        session.add(
            SetupState(id=1, completed_at=now, state_json=json.dumps(state), updated_at=now)
        )
    return {"completed": True}


@router.get("/settings/providers")
async def provider_status():
    settings = get_settings()
    return {
        "providers": [
            {"provider": "openai", "configured": OpenAIProvider().configured()},
            {"provider": "anthropic", "configured": AnthropicProvider().configured()},
            {"provider": "ollama", "configured": True, "base_url": settings.ollama_base_url},
        ],
        "defaults": [assignment.__dict__ for assignment in DEFAULT_MODELS],
        "capabilities": {
            provider: [model.__dict__ for model in models]
            for provider, models in (await _capabilities()).items()
        },
    }


@router.get("/settings/budgets")
async def budget_status():
    settings = get_settings()
    return {
        "daily_soft_budget_usd": settings.daily_soft_budget_usd,
        "monthly_soft_budget_usd": settings.monthly_soft_budget_usd,
        "warning_percent": settings.budget_warning_percent,
        "enforcement": "pause-queued-cost-incurring-work",
        "query_expansion_enabled": settings.query_expansion_enabled,
        "automatic_quality_escalation_enabled": settings.automatic_quality_escalation_enabled,
        "openai_input_cost_per_1k_usd": settings.openai_input_cost_per_1k_usd,
        "openai_output_cost_per_1k_usd": settings.openai_output_cost_per_1k_usd,
    }


@router.get("/settings/ollama/models")
async def ollama_models():
    models = await OllamaProvider().list_models()
    return {
        "models": [model.__dict__ for model in models],
        "missing_default_command": "ollama pull qwen3-embedding:0.6b",
        "warning": "Small local chat models are experimental and not production defaults.",
    }
