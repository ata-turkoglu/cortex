from fastapi import APIRouter

from ..core.config import get_settings
from ..providers.catalog import DEFAULT_MODELS
from ..providers.ollama import OllamaProvider

router = APIRouter(tags=["settings"])


@router.get("/settings/providers")
async def provider_status():
    settings = get_settings()
    return {
        "providers": [
            {"provider": "openai", "configured": bool(settings.openai_api_key)},
            {"provider": "anthropic", "configured": bool(settings.anthropic_api_key)},
            {"provider": "ollama", "configured": True, "base_url": settings.ollama_base_url},
        ],
        "defaults": [assignment.__dict__ for assignment in DEFAULT_MODELS],
    }


@router.get("/settings/budgets")
async def budget_status():
    return {
        "daily_soft_budget_usd": 0.0,
        "monthly_soft_budget_usd": 0.0,
        "warning_percent": 80,
        "enforcement": "pause-queued-cost-incurring-work",
    }


@router.get("/settings/ollama/models")
async def ollama_models():
    models = await OllamaProvider().list_models()
    return {
        "models": [model.__dict__ for model in models],
        "missing_default_command": "ollama pull qwen3-embedding:0.6b",
    }
