from app.core.config import Settings
from app.providers.catalog import DEFAULT_MODELS


def test_chat_model_defaults_and_cost_controls_are_safe_by_default():
    assignments = {assignment.layer: assignment for assignment in DEFAULT_MODELS}
    for layer in (
        "semantic_planner_simple",
        "semantic_planner_standard",
        "semantic_planner_complex",
        "conversation_summary",
        "answer_generation",
    ):
        assert assignments[layer].model == "gpt-5.6-luna"
    settings = Settings()
    assert settings.semantic_planner_escalation_enabled
    assert settings.semantic_planner_repair_attempts == 1
