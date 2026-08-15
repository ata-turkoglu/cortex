from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.aggregation.property import (
    aggregate_properties,
    classify_shares,
    entity_share,
    extract_property_claims,
    ownership_spans,
    property_location_display,
)
from app.models import Base, Chunk, Document, DocumentVersion, Workspace


def test_property_aggregation_normalizes_shares_deduplicates_and_preserves_provenance():
    session = sessionmaker(bind=create_engine("sqlite:///:memory:"))()
    Base.metadata.create_all(session.bind)
    now, workspace_id, document_id, version_id = (
        datetime.now(UTC),
        str(uuid4()),
        str(uuid4()),
        str(uuid4()),
    )
    session.add(
        Workspace(
            id=workspace_id,
            slug="aggregation",
            name="Aggregation",
            state="active",
            created_at=now,
            updated_at=now,
        )
    )
    session.add(
        Document(
            id=document_id,
            workspace_id=workspace_id,
            title="Title",
            active_version_id=version_id,
            created_at=now,
            updated_at=now,
        )
    )
    session.add(
        DocumentVersion(
            id=version_id,
            workspace_id=workspace_id,
            document_id=document_id,
            version_number=1,
            source_hash="source",
            source_path="source",
            source_filename="source.md",
            size_bytes=1,
            state="ready",
            created_at=now,
        )
    )
    for ordinal, text in enumerate(
        (
            "Mehmet Berke Merter tapu kaydinda hissedar. il: Istanbul ilce: Beykoz "
            "mahalle: Pasabahce pafta 1 ada 2 parsel 68 hisse 198/1408",
            "Mehmet Berke Merter tasinmazda hissedar. il: Istanbul ilce: Beykoz "
            "mahalle: Pasabahce pafta 1 ada 2 parsel 68 hisse 9/64",
        )
    ):
        session.add(
            Chunk(
                id=str(uuid4()),
                workspace_id=workspace_id,
                document_id=document_id,
                document_version_id=version_id,
                ordinal=ordinal,
                content=text,
                content_hash=str(ordinal),
                created_at=now,
            )
        )
    session.commit()

    result = aggregate_properties(session, workspace_id, "Mehmet Berke Merter", ("Berke",))

    assert result.complete is True
    assert result.distinct_property_count == 1
    assert result.records[0].representative.normalized_share is None
    assert len(result.records[0].claims) == 2
    assert result.execution["processed_chunk_count"] == 2


def _claim(text: str):
    chunk = SimpleNamespace(
        content=f"Mehmet Berke Merter {text}",
        document_id="document",
        document_version_id="version",
        id="chunk",
        ordinal=0,
    )
    return extract_property_claims(chunk, "Mehmet Berke Merter")[0]


def test_cadastral_labels_bind_values_without_field_shifting():
    fixtures = (
        ("40 pafta 303 ada 16 parsel", ("40", "303", "16")),
        ("40 pafta, 303 ada, 16 sayılı parsel", ("40", "303", "16")),
        ("303 ada 16 parsel", (None, "303", "16")),
        ("1 pafta 68 parsel", ("1", None, "68")),
        ("68 nolu parsel", (None, None, "68")),
        ("17 ada 25 parsel", (None, "17", "25")),
        ("248 pafta 1 ada", ("248", "1", None)),
        ("17 ada", (None, "17", None)),
        ("pafta 40 ada 303 parsel 16", ("40", "303", "16")),
    )
    for text, expected in fixtures:
        claim = _claim(text)
        assert (claim.sheet, claim.block, claim.parcel) == expected


def test_cadastral_parser_separates_share_and_ignores_numeric_noise():
    claim = _claim("303 ada 16 parsel, 1/8 hissesi Mehmet Berke Merter")
    assert (claim.block, claim.parcel, claim.share_text) == ("303", "16", "1/8")
    claim = _claim("2240 m2 taşocağı 9/64 hissesi 68 parsel")
    assert (claim.sheet, claim.block, claim.parcel, claim.share_text) == (None, None, "68", "9/64")
    for text in (
        "44.890.530 Kerem H. 11.222.632 Berke 16.833.948",
        "350.500.000 Satış Bedeli 338.621.000 Dağıtılan",
    ):
        chunk = SimpleNamespace(content=f"Mehmet Berke Merter {text}")
        assert extract_property_claims(chunk, "Mehmet Berke Merter") == []


def test_location_display_omits_missing_cadastral_labels():
    assert property_location_display(_claim("248 pafta 1 ada")) == "248 pafta, 1 ada"
    assert property_location_display(_claim("17 ada")) == "17 ada"


def test_shares_require_local_ownership_context_and_entity_binding():
    entity = "Mehmet Berke Merter"
    assert classify_shares("Karar No: 980/274", entity)[0].classification == "legal_identifier"
    assert classify_shares("Esas No: 975/511", entity)[0].classification == "legal_identifier"
    assert classify_shares("21/04/1988", entity)[0].classification == "date"
    assert classify_shares("980/274", entity)[0].classification == "unknown_fraction"
    multi = "- 1/8 hissesi Zehra Naile Subaşı\n- 9/64 hissesi Mehmet Berke Merter"
    assert entity_share(multi, entity).text == "9/64"
    assert entity_share("Mehmet Berke Merter'in payı 9/64'tür.", entity).text == "9/64"


def test_ownership_spans_bind_only_the_matching_item_in_collapsed_ocr_list():
    entity = "Mehmet Berke Merter"
    text = (
        "1/8 hissesi Zehra Naile Subaşı, 1/8 hissesi Nuriye Neyran Arpacı, "
        "9/64 hissesi Mehmet Berke Merter"
    )

    spans = ownership_spans(text, entity)

    assert len(spans) == 1
    assert spans[0].share and spans[0].share.text == "9/64"
    assert spans[0].source_span == "9/64 hissesi Mehmet Berke Merter"
