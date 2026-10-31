from datetime import UTC, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.knowledge.canonical_core import CanonicalCoreStore
from app.knowledge.canonical_reader import SQLiteCanonicalReader
from app.models import Base, KnowledgeGeneration, Workspace


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    now = datetime.now(UTC)
    session.add(
        Workspace(
            id="workspace",
            slug="workspace",
            name="Workspace",
            description=None,
            state="active",
            created_at=now,
            updated_at=now,
            deleted_at=None,
        )
    )
    session.add(
        KnowledgeGeneration(
            id="generation",
            workspace_id="workspace",
            source_fingerprint="source",
            state="building",
            failure_json=None,
            source_manifest_uri=None,
            source_manifest_hash=None,
            source_chunk_count=None,
            created_at=now,
            updated_at=now,
            activated_at=None,
        )
    )
    session.commit()
    return session


def test_sqlite_reader_lists_governed_surname_members_only():
    session = _session()
    store = CanonicalCoreStore(session, "workspace")
    for offset, name in ((0, "Ayşe Merter"), (20, "Mehmet Merter"), (40, "Zeynep Kaya")):
        mention = store.persist_person_mention(
            generation_id="generation",
            document_id="document",
            document_version_id="version",
            logical_document_id="logical",
            chunk_id=f"chunk-{offset}",
            span_start=offset,
            span_end=offset + len(name),
            source_text=name,
            extractor_version="test",
        )
        store.decide_person(mention)
    store.rebuild_membership("generation")
    session.commit()

    view = SQLiteCanonicalReader(session, "workspace").query_canonical_population(
        "generation", "person"
    )

    assert view.candidate_count == 3
    surnames = {entity.display_name: entity.properties[0].value for entity in view.entities}
    assert surnames == {
        "Ayşe Merter": "Merter",
        "Mehmet Merter": "Merter",
        "Zeynep Kaya": "Kaya",
    }


def test_same_name_is_not_implicitly_linked_and_ambiguous_name_is_unresolved():
    session = _session()
    store = CanonicalCoreStore(session, "workspace")
    first = store.persist_person_mention(
        generation_id="generation",
        document_id="document",
        document_version_id="version",
        logical_document_id="logical",
        chunk_id="chunk-a",
        span_start=0,
        span_end=11,
        source_text="Ayşe Merter",
        extractor_version="test",
    )
    second = store.persist_person_mention(
        generation_id="generation",
        document_id="document",
        document_version_id="version",
        logical_document_id="logical",
        chunk_id="chunk-b",
        span_start=0,
        span_end=11,
        source_text="Ayşe Merter",
        extractor_version="test",
    )
    ambiguous = store.persist_person_mention(
        generation_id="generation",
        document_id="document",
        document_version_id="version",
        logical_document_id="logical",
        chunk_id="chunk-c",
        span_start=0,
        span_end=6,
        source_text="Merter",
        extractor_version="test",
    )

    first_decision = store.decide_person(first)
    second_decision = store.decide_person(second)
    ambiguous_decision = store.decide_person(ambiguous)

    assert first_decision.decision == second_decision.decision == "NEW"
    assert first_decision.canonical_entity_id != second_decision.canonical_entity_id
    assert ambiguous_decision.decision == "UNRESOLVED"
    assert ambiguous_decision.canonical_entity_id is None
