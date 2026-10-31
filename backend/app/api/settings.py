import asyncio
import json
import re
from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import uuid4

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..accounting import budget_status as usage_budget_status
from ..core.config import get_settings
from ..core.embedding_runtime import (
    build_production_embedder,
    load_production_embedding_configuration,
)
from ..core.secrets import SecretStore, SecretStoreUnavailable
from ..core.settings_service import (
    PERSISTED_FIELDS,
    RuntimeEmbeddingConfigurationError,
    load_runtime_settings,
    save_settings,
)
from ..models import ProviderConnection, SetupState, WorkflowRun
from ..providers.anthropic import AnthropicProvider
from ..providers.catalog import DEFAULT_MODELS
from ..providers.embeddings import embedding_health_check
from ..providers.ollama import OllamaProvider
from ..providers.openai import OpenAIProvider
from .workspaces import get_session

router = APIRouter(tags=["settings"])
model_pull_operations: dict[str, dict[str, object]] = {}
FALLBACK_OLLAMA_CATALOG = [
    {
        "name": "qwen3:4b",
        "description": "Balanced local language model for general tasks.",
        "capabilities": ["chat"],
        "sizes": ["4B"],
    },
    {
        "name": "qwen3:8b",
        "description": "Higher-quality local language model for complex tasks.",
        "capabilities": ["chat"],
        "sizes": ["8B"],
    },
    {
        "name": "llama3.2:3b",
        "description": "Compact general-purpose local language model.",
        "capabilities": ["chat"],
        "sizes": ["3B"],
    },
    {
        "name": "gemma3:4b",
        "description": "Multimodal-capable local language model.",
        "capabilities": ["chat"],
        "sizes": ["4B"],
    },
    {
        "name": "qwen3-embedding:0.6b",
        "description": "Embedding model for semantic retrieval.",
        "capabilities": ["embedding"],
        "sizes": ["0.6B"],
    },
    {
        "name": "bge-m3",
        "description": "Multilingual embedding model for retrieval.",
        "capabilities": ["embedding"],
        "sizes": [],
    },
]


Provider = Literal["openai", "anthropic", "ollama"]
_SEMANTIC_PLANNER_TIERS = ("simple", "standard", "complex")


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
    embedding_concurrency: int | None = Field(default=None, ge=1, le=8)
    dense_top_k: int | None = Field(default=None, ge=1)
    bm25_top_k: int | None = Field(default=None, ge=1)
    fusion_candidate_limit: int | None = Field(default=None, ge=1)
    reranker_input_limit: int | None = Field(default=None, ge=1)
    final_evidence_top_k: int | None = Field(default=None, ge=1)
    graphrag_pending_document_threshold: int | None = Field(default=None, ge=1)
    graphrag_update_mode: Literal["manual", "threshold"] | None = None
    graphrag_extraction_provider: Literal["openai", "ollama"] | None = None
    graphrag_extraction_model: str | None = Field(default=None, min_length=1)
    graphrag_community_provider: Literal["openai", "ollama"] | None = None
    graphrag_community_model: str | None = Field(default=None, min_length=1)
    graphrag_global_provider: Literal["openai", "ollama"] | None = None
    graphrag_global_model: str | None = Field(default=None, min_length=1)
    graphrag_drift_provider: Literal["openai", "ollama"] | None = None
    graphrag_drift_model: str | None = Field(default=None, min_length=1)
    graphrag_drift_k_followups: int | None = Field(default=None, ge=1, le=20)
    graphrag_drift_primer_folds: int | None = Field(default=None, ge=1, le=10)
    graphrag_smart_search_enabled: bool | None = None
    graphrag_command_timeout_seconds: int | None = Field(default=None, ge=60, le=3600)
    workflow_ingestion_concurrency: int | None = Field(default=None, ge=1)
    workflow_dense_reindex_concurrency: int | None = Field(default=None, ge=1)
    workflow_graphrag_reindex_concurrency: int | None = Field(default=None, ge=1)
    workflow_deletion_concurrency: int | None = Field(default=None, ge=1)
    workflow_retention_days: int | None = Field(default=None, ge=1)
    conversation_memory_window_messages: int | None = Field(default=None, ge=1)
    answer_style: Literal["concise", "balanced", "detailed"] | None = None
    answer_synthesis_enabled: bool | None = None
    metadata_provider: Provider | None = None
    metadata_model: str | None = None
    answer_provider: Provider | None = None
    answer_model: str | None = None
    semantic_planner_simple_provider: Provider | None = None
    semantic_planner_simple_model: str | None = Field(default=None, min_length=1)
    semantic_planner_standard_provider: Provider | None = None
    semantic_planner_standard_model: str | None = Field(default=None, min_length=1)
    semantic_planner_complex_provider: Provider | None = None
    semantic_planner_complex_model: str | None = Field(default=None, min_length=1)
    semantic_planner_repair_attempts: int | None = Field(default=None, ge=0, le=3)
    semantic_planner_escalation_enabled: bool | None = None
    semantic_planner_confidence_threshold: float | None = Field(default=None, ge=0, le=1)
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


class OllamaModelPullRequest(BaseModel):
    model: str = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def valid_model_name(self):
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]*", self.model):
            raise ValueError("invalid Ollama model name")
        return self


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
    for layer in (
        "embedding",
        "metadata",
        "answer",
        "summary",
        "graphrag_extraction",
        "graphrag_community",
        "graphrag_global",
        "graphrag_drift",
    ):
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

    # Grounded answer synthesis is implemented only for OpenAI structured output.
    synthesis_enabled = patch.get("answer_synthesis_enabled")
    if synthesis_enabled is None:
        synthesis_enabled = get_settings().answer_synthesis_enabled
    answer_provider = patch.get("answer_provider") or get_settings().answer_provider
    if synthesis_enabled and answer_provider != "openai":
        raise HTTPException(422, "Answer synthesis currently supports only OpenAI")

    # The conversation-summary worker implements only the OpenAI text adapter and skips
    # any other assignment, so reject one that would silently disable summaries.
    summary_provider = patch.get("summary_provider")
    if summary_provider and summary_provider != "openai":
        raise HTTPException(422, "Conversation summary currently supports only OpenAI")

    # Production Query V2 currently wires only OpenAI's Responses structured-output
    # adapter for semantic planning. Validate every effective tier assignment on
    # every save so an unrelated Settings update cannot leave a latent planner
    # configuration failure behind.
    for tier in _SEMANTIC_PLANNER_TIERS:
        layer = f"semantic_planner_{tier}"
        provider = patch.get(f"{layer}_provider") or getattr(
            get_settings(), f"{layer}_provider"
        )
        model = patch.get(f"{layer}_model") or getattr(get_settings(), f"{layer}_model")
        label = f"Semantic Planner / {tier.title()}"
        if provider != "openai":
            raise HTTPException(
                422,
                f"{label} requires the configured OpenAI structured-output provider",
            )
        if not OpenAIProvider().configured():
            raise HTTPException(422, f"{label} requires a configured OpenAI credential")
        matches = [item for item in capabilities["openai"] if item.model == model]
        if not matches:
            raise HTTPException(422, f"{label}: openai/{model} is unavailable")
        if not matches[0].chat:
            raise HTTPException(
                422,
                f"{label}: openai/{model} lacks chat and strict structured-output support",
            )


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
        try:
            SecretStore().set(f"{provider}_api_key", payload.api_key)
        except SecretStoreUnavailable as exc:
            raise HTTPException(503, str(exc)) from exc
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
async def embedding_health(session: Annotated[Session, Depends(get_session)]):
    configuration, adapter = build_production_embedder(session)
    if configuration.provider != "ollama":
        raise HTTPException(
            422, "only the configured Ollama embedding adapter supports this health test"
        )
    result = await embedding_health_check(adapter)
    return result.__dict__


@router.get("/settings/embedding/status")
async def embedding_status(session: Annotated[Session, Depends(get_session)]):
    configuration = load_production_embedding_configuration(session)
    try:
        models = await OllamaProvider().list_models()
    except Exception:
        models = []
    installed = next((model for model in models if model.model == configuration.model), None)
    return {
        "provider": configuration.provider,
        "model": configuration.model,
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
def budget_status(session: Annotated[Session, Depends(get_session)]):
    try:
        load_runtime_settings(session)
    except RuntimeEmbeddingConfigurationError:
        pass  # First-run installs report defaults until settings are persisted.
    settings = get_settings()
    return usage_budget_status(
        session,
        daily_budget_usd=settings.daily_soft_budget_usd,
        monthly_budget_usd=settings.monthly_soft_budget_usd,
        warning_percent=settings.budget_warning_percent,
    )


@router.get("/settings/ollama/models")
async def ollama_models():
    models = await OllamaProvider().list_models()
    return {
        "models": [model.__dict__ for model in models],
        "warning": "Small local chat models are experimental and not production defaults.",
    }


def _catalog_text(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", value)).strip()


def _catalog_values(card: str, attribute: str) -> list[str]:
    return [
        _catalog_text(match)
        for match in re.findall(rf"<span {attribute}[^>]*>([\s\S]*?)</span>", card)
    ]


def _catalog_from_html(html: str, kind: str) -> list[dict[str, object]]:
    models = []
    for card in re.findall(r"<li x-test-model[\s\S]*?</li>", html):
        match = re.search(r'href="/library/([^"\'#?/]+)', card)
        if not match:
            continue
        description = re.search(r'<p class="max-w-lg[^>]*>([\s\S]*?)</p>', card)
        models.append(
            {
                "name": match.group(1),
                "description": (
                    _catalog_text(description.group(1)) if description else "Ollama Library model"
                ),
                "capabilities": _catalog_values(card, "x-test-capability"),
                "sizes": _catalog_values(card, "x-test-size"),
                "kind": kind,
            }
        )
    return models


@router.get("/settings/ollama/catalog")
async def ollama_catalog():
    """Discover selectable models from the official Ollama library; retain local fallbacks."""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            popular, embeddings = await asyncio.gather(
                client.get("https://ollama.com/library?sort=popular"),
                client.get("https://ollama.com/library?q=embed"),
            )
        popular.raise_for_status()
        embeddings.raise_for_status()
        discovered = _catalog_from_html(popular.text, "llm") + _catalog_from_html(
            embeddings.text, "embedding"
        )
        by_name = {str(item["name"]): item for item in discovered}
        for item in FALLBACK_OLLAMA_CATALOG:
            by_name.setdefault(str(item["name"]), item)
        return {"models": sorted(by_name.values(), key=lambda item: str(item["name"]))}
    except httpx.HTTPError:
        return {"models": FALLBACK_OLLAMA_CATALOG}


async def _pull_ollama_model(operation_id: str, model: str) -> None:
    """Track a user-started Ollama pull without holding a database transaction open."""
    operation = model_pull_operations[operation_id]
    try:
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream(
                "POST",
                get_settings().ollama_base_url + "/api/pull",
                json={"name": model, "stream": True},
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    update = json.loads(line)
                    if error := update.get("error"):
                        raise RuntimeError(str(error))
                    operation["completed"] = int(update.get("completed") or operation["completed"])
                    operation["total"] = int(update.get("total") or operation["total"])
        operation["status"] = "completed"
    except (httpx.HTTPError, RuntimeError, json.JSONDecodeError) as exc:
        operation["status"] = "failed"
        operation["error"] = str(exc)


@router.post("/settings/ollama/models/pull", status_code=202)
async def pull_ollama_model(payload: OllamaModelPullRequest):
    model = payload.model.strip()
    operation_id = str(uuid4())
    model_pull_operations[operation_id] = {
        "operation_id": operation_id,
        "model": model,
        "status": "running",
        "completed": 0,
        "total": 0,
        "error": None,
    }
    asyncio.create_task(_pull_ollama_model(operation_id, model))
    return model_pull_operations[operation_id]


@router.get("/settings/ollama/models/pull/{operation_id}")
def ollama_model_pull_status(operation_id: str):
    operation = model_pull_operations.get(operation_id)
    if not operation:
        raise HTTPException(404, "Ollama model download was not found")
    return operation
