import httpx

from ..core.config import get_settings
from ..core.secrets import SecretStore
from .base import GeneratedText, ModelCapability

_NON_TEXT_MODEL_MARKERS = (
    "embedding",
    "whisper",
    "tts",
    "dall-e",
    "moderation",
    "audio",
    "image",
    "realtime",
    "transcribe",
    "search-preview",
)


def _response_text(payload: dict[str, object]) -> str:
    """Read text from both convenience mocks and the wire Responses shape."""
    direct = payload.get("output_text")
    if isinstance(direct, str) and direct:
        return direct
    for output in payload.get("output", []) if isinstance(payload.get("output"), list) else []:
        if not isinstance(output, dict):
            continue
        content = output.get("content")
        if not isinstance(content, list):
            continue
        for item in content:
            if isinstance(item, dict) and item.get("type") == "output_text":
                text = item.get("text")
                if isinstance(text, str):
                    return text
    return ""


def _capability(model: str) -> ModelCapability | None:
    normalized = model.lower()
    if "embedding" in normalized:
        return ModelCapability("openai", model, embeddings=True)
    if any(marker in normalized for marker in _NON_TEXT_MODEL_MARKERS):
        return None
    if normalized.startswith(("gpt-", "chatgpt-", "o1", "o3", "o4")):
        return ModelCapability("openai", model, chat=True)
    return None


class OpenAIProvider:
    def configured(self) -> bool:
        return bool(get_settings().openai_api_key or SecretStore().get("openai_api_key"))

    async def list_models(self) -> list[ModelCapability]:
        api_key = get_settings().openai_api_key or SecretStore().get("openai_api_key")
        if not api_key:
            return []
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(
                    "https://api.openai.com/v1/models",
                    headers={"Authorization": f"Bearer {api_key}"},
                )
                response.raise_for_status()
            models = []
            for item in response.json().get("data", []):
                model_id = item.get("id")
                if isinstance(model_id, str):
                    capability = _capability(model_id)
                    if capability:
                        models.append(capability)
            return sorted(models, key=lambda item: item.model)
        except (httpx.HTTPError, ValueError, TypeError):
            return []

    async def generate(self, model: str, instructions: str, input_text: str) -> GeneratedText:
        """Call Responses outside database transactions through a worker-owned adapter."""
        api_key = get_settings().openai_api_key or SecretStore().get("openai_api_key")
        if not api_key:
            raise RuntimeError("OpenAI is not configured")
        async with httpx.AsyncClient(timeout=180) as client:
            response = await client.post(
                "https://api.openai.com/v1/responses",
                headers={"Authorization": f"Bearer {api_key}"},
                json={"model": model, "instructions": instructions, "input": input_text},
            )
            response.raise_for_status()
        payload = response.json()
        usage = payload.get("usage") or {}
        input_details = usage.get("input_tokens_details") or {}
        output_details = usage.get("output_tokens_details") or {}
        input_tokens = int(usage["input_tokens"]) if usage.get("input_tokens") is not None else None
        output_tokens = (
            int(usage["output_tokens"]) if usage.get("output_tokens") is not None else None
        )
        return GeneratedText(
            text=_response_text(payload),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=(
                int(usage["total_tokens"])
                if usage.get("total_tokens") is not None
                else (
                    input_tokens + output_tokens
                    if input_tokens is not None and output_tokens is not None
                    else None
                )
            ),
            cached_input_tokens=(
                int(input_details["cached_tokens"])
                if input_details.get("cached_tokens") is not None
                else None
            ),
            reasoning_tokens=(
                int(output_details["reasoning_tokens"])
                if output_details.get("reasoning_tokens") is not None
                else None
            ),
            request_id=str(payload["id"]) if payload.get("id") is not None else None,
            usage_payload=usage,
        )

    async def generate_structured(
        self,
        model: str,
        instructions: str,
        input_text: str,
        *,
        schema_name: str,
        json_schema: dict[str, object],
    ) -> GeneratedText:
        """Use Responses Structured Outputs; callers still validate the returned JSON."""
        api_key = get_settings().openai_api_key or SecretStore().get("openai_api_key")
        if not api_key:
            raise RuntimeError("OpenAI is not configured")
        async with httpx.AsyncClient(timeout=180) as client:
            response = await client.post(
                "https://api.openai.com/v1/responses",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": model,
                    "instructions": instructions,
                    "input": input_text,
                    "text": {
                        "format": {
                            "type": "json_schema",
                            "name": schema_name,
                            "strict": True,
                            "schema": json_schema,
                        }
                    },
                },
            )
            response.raise_for_status()
        payload = response.json()
        usage = payload.get("usage") or {}
        return GeneratedText(
            text=_response_text(payload),
            input_tokens=(
                int(usage["input_tokens"]) if usage.get("input_tokens") is not None else None
            ),
            output_tokens=(
                int(usage["output_tokens"]) if usage.get("output_tokens") is not None else None
            ),
            total_tokens=(
                int(usage["total_tokens"]) if usage.get("total_tokens") is not None else None
            ),
            request_id=str(payload["id"]) if payload.get("id") is not None else None,
            usage_payload=usage,
        )
