from dataclasses import dataclass


@dataclass(frozen=True)
class ModelAssignment:
    layer: str
    provider: str
    model: str


DEFAULT_MODELS = (
    ModelAssignment("answer_generation", "openai", "gpt-5.6-luna"),
    ModelAssignment("query_router", "openai", "gpt-5.6-luna"),
    ModelAssignment("conversation_summary", "openai", "gpt-5.6-luna"),
    ModelAssignment("query_expansion", "openai", "gpt-5.6-luna"),
    ModelAssignment("embeddings", "ollama", "qwen3-embedding:0.6b"),
)
