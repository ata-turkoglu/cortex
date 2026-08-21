"""Composable generation-aware executor for the durable knowledge reindex workflow."""

from collections.abc import Callable

from .pipeline import CorpusSnapshot, StageResult


class KnowledgeWorkflowExecutor:
    """Routes every mandatory stage to an explicit adapter; no implicit success path exists."""

    def __init__(self, handlers: dict[str, Callable[[CorpusSnapshot, str], StageResult]]) -> None:
        self.handlers = handlers

    def execute(self, stage: str, snapshot: CorpusSnapshot, generation_id: str) -> StageResult:
        handler = self.handlers.get(stage)
        if handler is None:
            raise RuntimeError(f"knowledge_reindex stage is not configured: {stage}")
        result = handler(snapshot, generation_id)
        if (
            result.generation_id != generation_id
            or result.input_fingerprint != snapshot.fingerprint
        ):
            raise ValueError("knowledge_reindex adapter returned mismatched generation input")
        if not result.output_fingerprint:
            raise ValueError("knowledge_reindex adapter returned an empty output fingerprint")
        return result
