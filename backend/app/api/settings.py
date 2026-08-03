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
    }
