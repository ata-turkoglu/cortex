from app.knowledge.entities import canonical_person_display_name, normalize_person_identity
from app.knowledge.extraction import (
    ExtractedEntityProperty,
    ExtractedMention,
    ExtractedSpan,
    ExtractionMetadata,
    KnowledgeExtractionBundle,
    retain_exact_assertions,
)
from app.knowledge.pipeline import CorpusSnapshot, SourceChunk
from app.query.answer import AnswerEngine
from app.query.orchestration import CompletenessReport, GroundedItem, ReasoningPackage


def _snapshot(content: str = "Lütfü Bükülmez Hasan Tahsin Merter") -> CorpusSnapshot:
    return CorpusSnapshot(
        "workspace",
        "fingerprint",
        (SourceChunk("chunk", "document", "version", "logical", 0, content, "hash"),),
    )


def _metadata() -> ExtractionMetadata:
    return ExtractionMetadata("run", "provider", "model", "prompt", "schema")


def test_person_identity_normalization_removes_titles_context_and_parenthetical_aliases():
    assert normalize_person_identity("RAUF MERTER") == normalize_person_identity("Rauf Merter")
    assert normalize_person_identity("Av. Baki Teksal") == "baki teksal"
    assert canonical_person_display_name("Varisleri Nesip Mustafa Merter") == "Nesip Mustafa Merter"
    assert normalize_person_identity("Karen Ingrid Merter (Matahiessen)") == "karen ingrid merter"


def test_person_identity_normalization_matches_turkish_case_variants():
    assert normalize_person_identity("HASAN TAHS\u0130N MERTER") == "hasan tahsin merter"


def test_person_identity_rejects_single_token_and_initial_fragments():
    assert normalize_person_identity("Merter") is None
    assert normalize_person_identity("Tahsin") is None
    assert normalize_person_identity("A.B.") is None


def test_person_identity_rejects_clauses_properties_and_possessive_spans():
    assert normalize_person_identity("Eminönü Mehyar Mahallesi 303 ada 16 Parsel") is None
    assert normalize_person_identity("Hüseyin Subaşı’nın mirasının mansup mirasçısı") is None
    assert normalize_person_identity("Hasan Tahsin Merter varisleri") is None


def test_cross_mention_surname_assertion_is_quarantined():
    content = "Lütfü Bükülmez Hasan Tahsin Merter"
    bundle = KnowledgeExtractionBundle(
        _metadata(),
        mentions=(
            ExtractedMention(
                "m1", "person", ExtractedSpan("chunk", 0, 14, "Lütfü Bükülmez", 1)
            ),
            ExtractedMention(
                "m2", "person", ExtractedSpan("chunk", 15, 34, "Hasan Tahsin Merter", 1)
            ),
        ),
        entity_properties=(
            ExtractedEntityProperty(
                "m1", "surname", "Merter", ExtractedSpan("chunk", 28, 34, "Merter", 1)
            ),
        ),
    )
    retained, rejected = retain_exact_assertions(bundle, _snapshot(content))
    assert retained.entity_properties == ()
    assert rejected == 1


def test_same_mention_surname_assertion_is_retained():
    content = "Lütfü Bükülmez Hasan Tahsin Merter"
    bundle = KnowledgeExtractionBundle(
        _metadata(),
        mentions=(
            ExtractedMention("m1", "person", ExtractedSpan("chunk", 0, 14, "Lütfü Bükülmez", 1)),
        ),
        entity_properties=(
            ExtractedEntityProperty(
                "m1", "surname", "Bükülmez", ExtractedSpan("chunk", 6, 14, "Bükülmez", 1)
            ),
        ),
    )
    retained, rejected = retain_exact_assertions(bundle, _snapshot(content))
    assert len(retained.entity_properties) == 1
    assert rejected == 0


def test_ranked_person_rows_render_without_internal_identifiers():
    package = ReasoningPackage(
        workspace_id="workspace",
        generation_id="generation",
        state="corpus_complete",
        structured_rows=(
            GroundedItem(
                item_id="row-1",
                values={
                    "entity_id": "opaque-id",
                    "entity_type": "person",
                    "display_name": "Rauf Merter",
                    "property_count": 2,
                },
                evidence_ids=("evidence",),
            ),
        ),
        completeness=CompletenessReport(
            coverage="exhaustive",
            state="complete",
            boundary="canonical people",
            generation_id="generation",
            candidate_count=1,
            processed_count=1,
        ),
        confidence=1,
    )
    content = AnswerEngine().render(package).content
    assert "Rauf Merter — 2 taşınmaz kaydı" in content
    assert "entity_id" not in content
    assert "entity_type" not in content


def test_same_name_does_not_supply_an_implicit_identity_candidate():
    """V2 forbids same-name auto-linking; candidates must be externally supplied."""
    assert normalize_person_identity("Rauf Merter") == normalize_person_identity("RAUF MERTER")
    # Normalization is deliberately not an identity decision.  The durable
    # CanonicalCoreStore coverage exercises NEW/UNRESOLVED/LINK decisions.
