from dataclasses import dataclass


@dataclass(frozen=True)
class ModelAssignment:
    layer: str
    provider: str
    model: str


DEFAULT_MODELS = (
    ModelAssignment("answer_generation", "openai", "gpt-5.6-luna"),
    ModelAssignment("semantic_planner_simple", "openai", "gpt-5.6-luna"),
    ModelAssignment("semantic_planner_standard", "openai", "gpt-5.6-luna"),
    ModelAssignment("semantic_planner_complex", "openai", "gpt-5.6-luna"),
    ModelAssignment("conversation_summary", "openai", "gpt-5.6-luna"),
)
