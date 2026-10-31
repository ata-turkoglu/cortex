import pytest

from app.knowledge.extraction import (
    ExtractedClaim,
    ExtractedMention,
    ExtractedRelation,
    ExtractedSpan,
    ExtractedTemporal,
    ExtractionMetadata,
    KnowledgeExtractionBundle,
    align_unique_exact_spans,
    split_composite_person_mentions,
    validate_extraction,
)
from app.knowledge.pipeline import CorpusSnapshot, SourceChunk


def snapshot():
    content = "Ayşe 2024 yılında Ankara'ya taşındı."
    return CorpusSnapshot(
        "workspace-a",
        "fingerprint-a",
        (SourceChunk("chunk-a", "doc-a", "version-a", "logical-a", 0, content, "hash-a"),),
    )


def span(text):
    source = snapshot().chunks[0].content
    start = source.index(text)
    return ExtractedSpan("chunk-a", start, start + len(text), text, 0.91)


def metadata():
    return ExtractionMetadata("run-a", "openai", "model-a", "prompt-v1", "schema-v1")


def test_bundle_materializes_exact_provenance_for_every_assertion():
    bundle = KnowledgeExtractionBundle(
        metadata(),
        mentions=(
            ExtractedMention("person", "person", span("Ayşe")),
            ExtractedMention("place", "location", span("Ankara")),
        ),
        relations=(ExtractedRelation("moved_to", "person", "place", span("Ankara'ya")),),
        temporals=(
            ExtractedTemporal(
                "date", "2024", "2024", "2024", "event_time", "year", False, span("2024")
            ),
        ),
        claims=(ExtractedClaim("person", "moved_to", "Ankara", span("Ankara'ya")),),
    )
    evidence = validate_extraction(bundle, snapshot(), "generation-a")
    assert len(evidence) == 5
    assert all(item.workspace_id == "workspace-a" for item in evidence)
    assert all(item.generation == "generation-a" for item in evidence)


def test_hallucinated_span_and_cross_reference_are_rejected():
    bad_span = ExtractedSpan("chunk-a", 0, 4, "Ali", 0.8)
    bundle = KnowledgeExtractionBundle(
        metadata(), mentions=(ExtractedMention("person", "person", bad_span),)
    )
    with pytest.raises(ValueError, match="does not occur"):
        validate_extraction(bundle, snapshot(), "generation-a")
    relation = KnowledgeExtractionBundle(
        metadata(),
        mentions=(ExtractedMention("person", "person", span("Ayşe")),),
        relations=(ExtractedRelation("knows", "person", "missing", span("Ayşe")),),
    )
    with pytest.raises(ValueError, match="unknown mention"):
        validate_extraction(relation, snapshot(), "generation-a")


def test_unique_exact_quote_can_repair_provider_offsets_but_ambiguous_quote_cannot():
    shifted = KnowledgeExtractionBundle(
        metadata(),
        mentions=(
            ExtractedMention(
                "place", "location", ExtractedSpan("chunk-a", 0, 6, "Ankara", 0.9)
            ),
        ),
    )
    aligned = align_unique_exact_spans(shifted, snapshot())
    validate_extraction(aligned, snapshot(), "generation-a")
    assert aligned.mentions[0].span.start_offset == snapshot().chunks[0].content.index("Ankara")

    repeated_content = "Ankara ve Ankara"
    repeated = CorpusSnapshot(
        "workspace-a", "fingerprint-b",
        (SourceChunk("chunk-a", "doc-a", "version-a", "logical-a", 0,
                     repeated_content, "hash-b"),),
    )
    ambiguous_bundle = KnowledgeExtractionBundle(
        metadata(),
        mentions=(
            ExtractedMention(
                "place", "location", ExtractedSpan("chunk-a", 5, 11, "Ankara", 0.9)
            ),
        ),
    )
    ambiguous = align_unique_exact_spans(ambiguous_bundle, repeated)
    with pytest.raises(ValueError, match="offset does not exactly match"):
        validate_extraction(ambiguous, repeated, "generation-a")


def test_temporal_original_text_and_uncertainty_are_preserved():
    altered = KnowledgeExtractionBundle(
        metadata(),
        temporals=(
            ExtractedTemporal(
                "date", "2025", "2024", "2024", "event_time", "year", False, span("2024")
            ),
        ),
    )
    with pytest.raises(ValueError, match="preserve"):
        validate_extraction(altered, snapshot(), "generation-a")
    uncertain = KnowledgeExtractionBundle(
        metadata(),
        temporals=(
            ExtractedTemporal(
                "date", "2024", None, None, "event_time", "unknown", False, span("2024")
            ),
        ),
    )
    with pytest.raises(ValueError, match="uncertain"):
        validate_extraction(uncertain, snapshot(), "generation-a")


@pytest.mark.parametrize(
    ("content", "source", "expected"),
    (
        (
            "Mustafa Merter - Rauf Merter",
            "Mustafa Merter - Rauf Merter",
            ("Mustafa Merter", "Rauf Merter"),
        ),
        (
            "Mustafa Merter - Rauf Merter - Dilaver Kayra",
            "Mustafa Merter - Rauf Merter - Dilaver Kayra",
            ("Mustafa Merter", "Rauf Merter", "Dilaver Kayra"),
        ),
        (
            "Ali Çobanoğlu – Baki Toksal",
            "Ali Çobanoğlu – Baki Toksal",
            ("Ali Çobanoğlu", "Baki Toksal"),
        ),
        (
            "Karen Ingrid Merter U.Vekili Av. E. Ruhi Öztürk",
            "Karen Ingrid Merter U.Vekili Av. E. Ruhi Öztürk",
            ("Karen Ingrid Merter", "Av. E. Ruhi Öztürk"),
        ),
    ),
)
def test_explicit_composite_person_spans_split_without_identity_linking(content, source, expected):
    source_snapshot = CorpusSnapshot(
        "workspace-a",
        "fingerprint-composite",
        (SourceChunk("chunk-a", "doc-a", "version-a", "logical-a", 0, content, "hash-a"),),
    )
    bundle = KnowledgeExtractionBundle(
        metadata(),
        mentions=(
            ExtractedMention(
                "combined", "person", ExtractedSpan("chunk-a", 0, len(source), source, 0.9)
            ),
        ),
    )

    corrected = split_composite_person_mentions(bundle)

    assert tuple(item.span.source_text for item in corrected.mentions) == expected
    assert all(not item.candidate_canonical_entity_ids for item in corrected.mentions)
    validate_extraction(corrected, source_snapshot, "generation-a")
