from datetime import UTC, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.knowledge.canonical_core import CanonicalCoreStore
from app.knowledge.canonical_reader import SQLiteCanonicalReader
from app.models import Base, KnowledgeGeneration, Workspace


def _store():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    now = datetime.now(UTC)
    session.add(
        Workspace(
            id="workspace",
            slug="workspace",
            name="workspace",
            state="active",
            created_at=now,
            updated_at=now,
        )
    )
    session.add(
        KnowledgeGeneration(
            id="generation",
            workspace_id="workspace",
            source_fingerprint="source",
            state="building",
            created_at=now,
            updated_at=now,
        )
    )
    session.flush()
    return session, CanonicalCoreStore(session, "workspace")


def _mention(store, name, offset, version="version"):
    return store.persist_person_mention(
        generation_id="generation",
        document_id="document",
        document_version_id=version,
        logical_document_id="logical",
        chunk_id=f"chunk-{version}",
        span_start=offset,
        span_end=offset + len(name),
        source_text=name,
        extractor_version="test",
    )


def test_new_unresolved_and_idempotent_mentions_are_durable():
    session, store = _store()
    first = _mention(store, "Ayşe Merter", 0)
    again = _mention(store, "Ayşe Merter", 0)
    assert again.id == first.id
    assert store.decide_person(first).decision == "NEW"
    unresolved = store.decide_person(_mention(store, "Merter", 0, "version-2"))
    assert unresolved.decision == "UNRESOLVED"
    store.record_chunk("generation", "chunk-version", "a" * 64)
    store.record_chunk("generation", "chunk-version-2", "b" * 64)
    status = store.record_status(
        generation_id="generation",
        manifest_hash="a" * 64,
        manifest_chunk_count=2,
    )
    assert status.status == "PARTIAL"
    session.commit()


def test_suffix_courtesy_title_does_not_create_a_canonical_person():
    _session, store = _store()

    decision = store.decide_person(_mention(store, "Ali Bey", 0))

    assert decision.decision == "UNRESOLVED"


def test_unresolved_counter_is_authoritative_across_retries_and_reprocessing():
    session, store = _store()
    mentions = (
        _mention(store, "Ali Merter", 0, "version-1"),
        _mention(store, "Ali Bey", 10, "version-2"),
        _mention(store, "B.", 20, "version-3"),
    )
    for mention in mentions:
        store.decide_person(mention)
    for index in range(3):
        store.record_chunk("generation", f"chunk-{index}", str(index) * 64)

    initial = store.record_status(
        generation_id="generation", manifest_hash="f" * 64, manifest_chunk_count=3
    )
    retry = store.record_status(
        generation_id="generation", manifest_hash="f" * 64, manifest_chunk_count=3
    )
    session.expire_all()
    reprocessed = store.record_status(
        generation_id="generation", manifest_hash="f" * 64, manifest_chunk_count=3
    )

    assert (initial.unresolved_mention_count, retry.unresolved_mention_count) == (2, 2)
    assert reprocessed.unresolved_mention_count == 2


def test_same_name_is_not_implicitly_linked_and_generation_membership_keeps_zeroes():
    session, store = _store()
    first = store.decide_person(_mention(store, "Ayşe Merter", 0))
    second = store.decide_person(_mention(store, "Ayşe Merter", 0, "version-2"))
    assert first.decision == second.decision == "NEW"
    assert first.canonical_entity_id != second.canonical_entity_id
    store.rebuild_membership("generation")
    assert store.ranked_people_by_surname("generation", "Merter") == [
        ("Ayşe Merter", 0),
        ("Ayşe Merter", 0),
    ]
    session.commit()


def test_exact_name_consolidation_requires_two_document_versions():
    _session, store = _store()
    first = store.decide_person(_mention(store, "AyÅŸe Merter", 0, "version-1"))
    second = store.decide_person(_mention(store, "AyÅŸe Merter", 0, "version-2"))
    same_document = store.decide_person(_mention(store, "Zeynep Merter", 10, "version-1"))
    same_document_duplicate = store.decide_person(
        _mention(store, "Zeynep Merter", 30, "version-1")
    )

    remapped = store.consolidate_exact_person_identities("generation")
    store.rebuild_membership("generation")

    assert remapped
    assert first.canonical_entity_id == second.canonical_entity_id
    assert same_document.mention_id not in remapped
    assert same_document_duplicate.mention_id not in remapped
    assert store.ranked_people_by_surname("generation", "Merter") == [
        ("AyÅŸe Merter", 0),
        ("Zeynep Merter", 0),
        ("Zeynep Merter", 0),
    ]


def test_workspace_and_generation_membership_and_ownership_are_isolated():
    session, first_store = _store()
    now = datetime.now(UTC)
    session.add(
        Workspace(
            id="other-workspace",
            slug="other-workspace",
            name="other-workspace",
            state="active",
            created_at=now,
            updated_at=now,
        )
    )
    session.add_all(
        [
            KnowledgeGeneration(
                id="generation-2",
                workspace_id="workspace",
                source_fingerprint="source-2",
                state="building",
                created_at=now,
                updated_at=now,
            ),
            KnowledgeGeneration(
                id="other-generation",
                workspace_id="other-workspace",
                source_fingerprint="other-source",
                state="building",
                created_at=now,
                updated_at=now,
            ),
        ]
    )
    session.flush()
    other_store = CanonicalCoreStore(session, "other-workspace")

    ali = first_store.persist_person_mention(
        generation_id="generation", document_id="d1", document_version_id="v1",
        logical_document_id="l1", chunk_id="c1", span_start=0, span_end=10,
        source_text="Ali Merter", extractor_version="test",
    )
    ali_id = first_store.decide_person(ali).canonical_entity_id
    zeynep = first_store.persist_person_mention(
        generation_id="generation", document_id="d2", document_version_id="v2",
        logical_document_id="l2", chunk_id="c2", span_start=0, span_end=13,
        source_text="Zeynep Merter", extractor_version="test",
    )
    first_store.decide_person(zeynep)
    other_ali = other_store.persist_person_mention(
        generation_id="other-generation", document_id="d1", document_version_id="v1",
        logical_document_id="l1", chunk_id="c1", span_start=0, span_end=10,
        source_text="Ali Merter", extractor_version="test",
    )
    other_ali_id = other_store.decide_person(other_ali).canonical_entity_id
    assert ali_id != other_ali_id

    linked_ali = first_store.persist_person_mention(
        generation_id="generation-2", document_id="d3", document_version_id="v3",
        logical_document_id="l3", chunk_id="c3", span_start=0, span_end=10,
        source_text="Ali Merter", extractor_version="test",
    )
    assert first_store.decide_person(
        linked_ali, candidate_ids=(ali_id,), candidate_provenance="prior generation"
    ).canonical_entity_id == ali_id
    first_store.rebuild_membership("generation")
    first_store.rebuild_membership("generation-2")
    other_store.rebuild_membership("other-generation")

    primary_reader = SQLiteCanonicalReader(session, "workspace")
    other_reader = SQLiteCanonicalReader(session, "other-workspace")
    first_generation = primary_reader.query_canonical_population("generation", "person")
    second_generation = primary_reader.query_canonical_population("generation-2", "person")
    foreign_generation = other_reader.query_canonical_population("other-generation", "person")
    first_names = [item.display_name for item in first_generation.entities]
    # Population order follows opaque canonical IDs, not display names.
    assert sorted(first_names) == ["Ali Merter", "Zeynep Merter"]
    assert [item.display_name for item in second_generation.entities] == ["Ali Merter"]
    assert [item.display_name for item in foreign_generation.entities] == ["Ali Merter"]
