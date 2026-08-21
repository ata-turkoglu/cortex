"""Provider-neutral structured extraction envelope with exact-source validation."""

from dataclasses import dataclass, replace

from .pipeline import CorpusSnapshot
from .provenance import ExactSourceProvenance


@dataclass(frozen=True)
class ExtractionMetadata:
    extraction_run_id: str
    provider: str
    model: str
    prompt_version: str
    schema_version: str

    def __post_init__(self) -> None:
        if any(
            not value.strip()
            for value in (
                self.extraction_run_id,
                self.provider,
                self.model,
                self.prompt_version,
                self.schema_version,
            )
        ):
            raise ValueError("extraction metadata must identify its run, model, prompt, and schema")


@dataclass(frozen=True)
class ExtractedSpan:
    chunk_id: str
    start_offset: int
    end_offset: int
    source_text: str
    confidence: float


@dataclass(frozen=True)
class ExtractedMention:
    local_id: str
    entity_type: str
    span: ExtractedSpan


@dataclass(frozen=True)
class ExtractedRelation:
    relation_type: str
    source_mention_id: str
    target_mention_id: str
    span: ExtractedSpan


@dataclass(frozen=True)
class ExtractedEvent:
    local_id: str
    event_type: str
    participant_mention_ids: tuple[str, ...]
    span: ExtractedSpan


@dataclass(frozen=True)
class ExtractedTemporal:
    local_id: str
    original_text: str
    normalized_start: str | None
    normalized_end: str | None
    semantic_role: str
    precision: str
    uncertain: bool
    span: ExtractedSpan


@dataclass(frozen=True)
class ExtractedClaim:
    subject_mention_id: str
    predicate: str
    value: object
    span: ExtractedSpan


@dataclass(frozen=True)
class KnowledgeExtractionBundle:
    metadata: ExtractionMetadata
    mentions: tuple[ExtractedMention, ...] = ()
    relations: tuple[ExtractedRelation, ...] = ()
    events: tuple[ExtractedEvent, ...] = ()
    temporals: tuple[ExtractedTemporal, ...] = ()
    claims: tuple[ExtractedClaim, ...] = ()


def align_unique_exact_spans(
    bundle: KnowledgeExtractionBundle, snapshot: CorpusSnapshot
) -> KnowledgeExtractionBundle:
    """Correct provider offsets only when its quoted text has one exact source occurrence."""
    chunks = {chunk.chunk_id: chunk.content for chunk in snapshot.chunks}

    def aligned(span: ExtractedSpan) -> ExtractedSpan:
        content = chunks.get(span.chunk_id)
        if content is None:
            return span
        if content[span.start_offset : span.end_offset] == span.source_text:
            return span
        first = content.find(span.source_text)
        if first < 0:
            return span
        occurrences = []
        cursor = first
        while cursor >= 0:
            occurrences.append(cursor)
            cursor = content.find(span.source_text, cursor + 1)
        ranked = sorted((abs(start - span.start_offset), start) for start in occurrences)
        if len(ranked) > 1 and ranked[0][0] == ranked[1][0]:
            return span
        chosen = ranked[0][1]
        return replace(span, start_offset=chosen, end_offset=chosen + len(span.source_text))

    return replace(
        bundle,
        mentions=tuple(replace(item, span=aligned(item.span)) for item in bundle.mentions),
        relations=tuple(replace(item, span=aligned(item.span)) for item in bundle.relations),
        events=tuple(replace(item, span=aligned(item.span)) for item in bundle.events),
        temporals=tuple(replace(item, span=aligned(item.span)) for item in bundle.temporals),
        claims=tuple(replace(item, span=aligned(item.span)) for item in bundle.claims),
    )


def retain_exact_assertions(
    bundle: KnowledgeExtractionBundle, snapshot: CorpusSnapshot
) -> tuple[KnowledgeExtractionBundle, int]:
    """Drop invalid assertions and all dependencies instead of accepting weak evidence."""
    chunks = {chunk.chunk_id: chunk.content for chunk in snapshot.chunks}

    def exact(span: ExtractedSpan) -> bool:
        content = chunks.get(span.chunk_id)
        return bool(
            content is not None
            and 0 <= span.start_offset < span.end_offset <= len(content)
            and content[span.start_offset : span.end_offset] == span.source_text
        )

    mentions = tuple(item for item in bundle.mentions if exact(item.span))
    mention_ids = {item.local_id for item in mentions}
    relations = tuple(
        item for item in bundle.relations
        if exact(item.span)
        and item.source_mention_id in mention_ids
        and item.target_mention_id in mention_ids
    )
    events = tuple(
        item for item in bundle.events
        if exact(item.span) and set(item.participant_mention_ids) <= mention_ids
    )
    temporals = tuple(
        item for item in bundle.temporals
        if exact(item.span)
        and item.original_text == item.span.source_text
        and item.precision in {"exact", "day", "month", "year", "approximate", "unknown"}
        and (item.precision == "unknown" or bool(item.normalized_start))
        and not (item.precision in {"approximate", "unknown"} and not item.uncertain)
    )
    claims = tuple(
        item for item in bundle.claims
        if exact(item.span) and item.subject_mention_id in mention_ids
    )
    retained = replace(
        bundle,
        mentions=mentions,
        relations=relations,
        events=events,
        temporals=temporals,
        claims=claims,
    )
    original_count = sum(len(getattr(bundle, name)) for name in (
        "mentions", "relations", "events", "temporals", "claims"
    ))
    retained_count = sum(len(getattr(retained, name)) for name in (
        "mentions", "relations", "events", "temporals", "claims"
    ))
    return retained, original_count - retained_count


def validate_extraction(
    bundle: KnowledgeExtractionBundle,
    snapshot: CorpusSnapshot,
    generation_id: str,
) -> tuple[ExactSourceProvenance, ...]:
    """Reject hallucinated spans/references and materialize complete evidence chains."""
    if not generation_id.strip():
        raise ValueError("generation_id is required")
    chunks = {chunk.chunk_id: chunk for chunk in snapshot.chunks}
    mention_ids = {mention.local_id for mention in bundle.mentions}
    if len(mention_ids) != len(bundle.mentions) or any(not item for item in mention_ids):
        raise ValueError("mention local IDs must be non-empty and unique")
    spans = [mention.span for mention in bundle.mentions]
    for relation in bundle.relations:
        if {relation.source_mention_id, relation.target_mention_id} - mention_ids:
            raise ValueError("relation references an unknown mention")
        spans.append(relation.span)
    for event in bundle.events:
        if set(event.participant_mention_ids) - mention_ids:
            raise ValueError("event references an unknown participant mention")
        spans.append(event.span)
    for temporal in bundle.temporals:
        if temporal.original_text != temporal.span.source_text:
            raise ValueError("temporal original text must preserve the exact source span")
        if temporal.precision in {"approximate", "unknown"} and not temporal.uncertain:
            raise ValueError("approximate or unknown temporal values must remain uncertain")
        if temporal.precision not in {
            "exact", "day", "month", "year", "approximate", "unknown"
        }:
            raise ValueError("temporal precision is unsupported")
        if temporal.precision != "unknown" and not temporal.normalized_start:
            raise ValueError("known temporal precision requires a normalized start")
        spans.append(temporal.span)
    for claim in bundle.claims:
        if claim.subject_mention_id not in mention_ids:
            raise ValueError("claim references an unknown subject mention")
        spans.append(claim.span)

    evidence = []
    for span in spans:
        chunk = chunks.get(span.chunk_id)
        if chunk is None:
            raise ValueError("extraction span references a chunk outside the corpus snapshot")
        if span.source_text not in chunk.content:
            raise ValueError("extraction quoted source text does not occur in its source chunk")
        if (
            span.start_offset < 0
            or span.end_offset <= span.start_offset
            or span.end_offset > len(chunk.content)
            or chunk.content[span.start_offset : span.end_offset] != span.source_text
        ):
            raise ValueError("extraction offset does not exactly match quoted source text")
        evidence.append(
            ExactSourceProvenance(
                workspace_id=snapshot.workspace_id,
                document_id=chunk.document_id,
                document_version_id=chunk.document_version_id,
                logical_document_id=chunk.logical_document_id,
                chunk_id=chunk.chunk_id,
                start_offset=span.start_offset,
                end_offset=span.end_offset,
                source_text=span.source_text,
                extraction_run_id=bundle.metadata.extraction_run_id,
                provider=bundle.metadata.provider,
                model=bundle.metadata.model,
                prompt_version=bundle.metadata.prompt_version,
                schema_version=bundle.metadata.schema_version,
                confidence=span.confidence,
                validation_state="extracted",
                generation=generation_id,
            )
        )
    return tuple(evidence)
