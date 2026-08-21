"""Worker-owned OpenAI extraction adapter; calls happen outside database transactions."""

import asyncio
import json
from dataclasses import dataclass
from uuid import uuid4

from ..providers.base import LLMProvider
from ..providers.openai import OpenAIProvider
from .extraction import (
    ExtractionMetadata,
    KnowledgeExtractionBundle,
    align_unique_exact_spans,
    retain_exact_assertions,
    validate_extraction,
)
from .extraction_json import decode_extraction_json
from .pipeline import CorpusSnapshot

_INSTRUCTIONS = """Extract only facts explicitly present in the supplied chunk.
Return JSON only with
mentions, relations, events, temporals, and claims arrays. Every item must provide chunk_id,
start_offset, end_offset, source_text, and confidence. Never infer facts or spans. Mention IDs are
local to this response; relation/event/claim references must use those IDs. Keep temporal
original_text exactly equal to its source_text. source_text must be copied as one literal,
contiguous substring of content. Offsets are zero-based Python Unicode string indices. If an
assertion cannot be supported by an exact literal span, omit it instead of paraphrasing."""

_SPAN_PROPERTIES = {
    "chunk_id": {"type": "string"},
    "start_offset": {"type": "integer", "minimum": 0},
    "end_offset": {"type": "integer", "minimum": 1},
    "source_text": {"type": "string", "minLength": 1},
    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
}
_SPAN_REQUIRED = list(_SPAN_PROPERTIES)


def _row(properties: dict[str, object], required: list[str]) -> dict[str, object]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {**properties, **_SPAN_PROPERTIES},
        "required": [*required, *_SPAN_REQUIRED],
    }


_EXTRACTION_SCHEMA: dict[str, object] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "mentions": {"type": "array", "items": _row(
            {"id": {"type": "string"}, "entity_type": {
                "type": "string",
                "enum": ["person", "organization", "location", "asset_property", "dynamic"],
            }},
            ["id", "entity_type"],
        )},
        "relations": {"type": "array", "items": _row(
            {
                "relation_type": {"type": "string"},
                "source_mention_id": {"type": "string"},
                "target_mention_id": {"type": "string"},
            },
            ["relation_type", "source_mention_id", "target_mention_id"],
        )},
        "events": {"type": "array", "items": _row(
            {
                "id": {"type": "string"},
                "event_type": {"type": "string"},
                "participants": {"type": "array", "items": {
                    "type": "object", "additionalProperties": False,
                    "properties": {"mention_id": {"type": "string"}},
                    "required": ["mention_id"],
                }},
            },
            ["id", "event_type", "participants"],
        )},
        "temporals": {"type": "array", "items": _row(
            {
                "id": {"type": "string"},
                "original_text": {"type": "string"},
                "normalized_start": {"type": ["string", "null"]},
                "normalized_end": {"type": ["string", "null"]},
                "semantic_role": {"type": "string"},
                "precision": {"type": "string", "enum": [
                    "exact", "day", "month", "year", "approximate", "unknown"
                ]},
                "uncertain": {"type": "boolean"},
            },
            ["id", "original_text", "normalized_start", "normalized_end",
             "semantic_role", "precision", "uncertain"],
        )},
        "claims": {"type": "array", "items": _row(
            {
                "subject_mention_id": {"type": "string"},
                "predicate": {"type": "string"},
                "value": {"type": ["string", "number", "boolean", "null"]},
            },
            ["subject_mention_id", "predicate", "value"],
        )},
    },
    "required": ["mentions", "relations", "events", "temporals", "claims"],
}


@dataclass(frozen=True)
class ProviderExtractionResult:
    bundles: tuple[KnowledgeExtractionBundle, ...]
    evidence_count: int
    rejected_assertion_count: int = 0


class OpenAIKnowledgeExtractor:
    """Strict adapter for a configured OpenAI text model."""

    def __init__(
        self,
        model: str,
        provider: LLMProvider | None = None,
        *,
        provider_name: str = "openai",
    ) -> None:
        if not model.strip():
            raise ValueError("knowledge extraction model is required")
        self.model = model
        self.provider = provider or OpenAIProvider()
        self.provider_name = provider_name

    async def _extract_chunk(
        self, snapshot: CorpusSnapshot, generation_id: str, chunk_id: str, content: str
    ) -> tuple[KnowledgeExtractionBundle, int]:
        request_id = str(uuid4())
        input_text = json.dumps({"chunk_id": chunk_id, "content": content}, ensure_ascii=False)
        structured = getattr(self.provider, "generate_structured", None)
        validation_error = ""
        for attempt in range(3):
            bundle = None
            instructions = _INSTRUCTIONS + (
                f"\nThe previous response failed validation: {validation_error}. "
                "Return a corrected extraction and omit any assertion without literal evidence."
                if validation_error
                else ""
            )
            response = (
                await structured(
                    self.model,
                    instructions,
                    input_text,
                    schema_name="knowledge_extraction_v1",
                    json_schema=_EXTRACTION_SCHEMA,
                )
                if structured
                else await self.provider.generate(self.model, instructions, input_text)
            )
            metadata = ExtractionMetadata(
                extraction_run_id=response.request_id or request_id,
                provider=self.provider_name,
                model=self.model,
                prompt_version="knowledge-extraction-v1",
                schema_version="knowledge-extraction-json-v1",
            )
            try:
                bundle = align_unique_exact_spans(
                    decode_extraction_json(response.text, metadata), snapshot
                )
                validate_extraction(bundle, snapshot, generation_id)
                return bundle, 0
            except ValueError as exc:
                validation_error = str(exc)
                if attempt == 2 and bundle is not None:
                    retained, rejected = retain_exact_assertions(bundle, snapshot)
                    validate_extraction(retained, snapshot, generation_id)
                    return retained, rejected
                if attempt == 2:
                    raise
        raise RuntimeError("unreachable")

    async def _extract_all(
        self, snapshot: CorpusSnapshot, generation_id: str
    ) -> tuple[tuple[KnowledgeExtractionBundle, int], ...]:
        chunks = list(snapshot.chunks)
        extracted: list[tuple[KnowledgeExtractionBundle, int]] = []
        # Keep provider pressure bounded. Repair attempts can multiply requests,
        # and an unbounded corpus-wide gather causes avoidable upstream timeouts.
        for offset in range(0, len(chunks), 4):
            extracted.extend(
                await asyncio.gather(
                    *(
                    self._extract_chunk(snapshot, generation_id, chunk.chunk_id, chunk.content)
                        for chunk in chunks[offset : offset + 4]
                    )
                )
            )
        return tuple(extracted)

    def extract(self, snapshot: CorpusSnapshot, generation_id: str) -> ProviderExtractionResult:
        """Extract one immutable snapshot; no SQLAlchemy session is accepted or retained."""
        extracted = asyncio.run(self._extract_all(snapshot, generation_id))
        bundles = tuple(item[0] for item in extracted)
        evidence_count = sum(
            len(validate_extraction(bundle, snapshot, generation_id)) for bundle in bundles
        )
        return ProviderExtractionResult(
            bundles, evidence_count, sum(item[1] for item in extracted)
        )
