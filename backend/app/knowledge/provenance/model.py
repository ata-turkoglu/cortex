"""Exact-source provenance required by canonical assertions."""

from dataclasses import dataclass
from uuid import NAMESPACE_URL, uuid5


@dataclass(frozen=True)
class ExactSourceProvenance:
    workspace_id: str
    document_id: str
    document_version_id: str
    logical_document_id: str
    chunk_id: str
    start_offset: int
    end_offset: int
    source_text: str
    extraction_run_id: str
    provider: str
    model: str
    prompt_version: str
    schema_version: str
    confidence: float
    validation_state: str
    generation: str

    def __post_init__(self) -> None:
        required = (
            self.workspace_id,
            self.document_id,
            self.document_version_id,
            self.logical_document_id,
            self.chunk_id,
            self.source_text,
            self.extraction_run_id,
            self.provider,
            self.model,
            self.prompt_version,
            self.schema_version,
            self.validation_state,
            self.generation,
        )
        if any(not value.strip() for value in required):
            raise ValueError("exact provenance requires the complete source and extraction chain")
        if self.start_offset < 0 or self.end_offset <= self.start_offset:
            raise ValueError("source span offsets must be ordered and non-empty")
        if self.end_offset - self.start_offset != len(self.source_text):
            raise ValueError("source text must exactly match the declared source span")
        if not 0 <= self.confidence <= 1:
            raise ValueError("confidence must be between zero and one")

    @property
    def evidence_id(self) -> str:
        material = "\x1f".join(
            (
                self.workspace_id,
                self.document_id,
                self.document_version_id,
                self.logical_document_id,
                self.chunk_id,
                str(self.start_offset),
                str(self.end_offset),
                self.extraction_run_id,
                self.generation,
            )
        )
        return str(uuid5(NAMESPACE_URL, material))
