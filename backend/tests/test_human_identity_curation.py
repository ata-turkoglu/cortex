from datetime import UTC, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.knowledge.canonical_core import CanonicalCoreStore
from app.knowledge.identity_curation import HumanIdentityCurationStore
from app.models import Base, KnowledgeGeneration, Workspace


def _store():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    now = datetime.now(UTC)
    session.add(
        Workspace(
            id="workspace", slug="workspace", name="workspace", state="active",
            created_at=now, updated_at=now,
        )
    )
    for generation_id, fingerprint in (("generation-a", "a"), ("generation-b", "b")):
        session.add(
            KnowledgeGeneration(
                id=generation_id, workspace_id="workspace", source_fingerprint=fingerprint,
                state="building", created_at=now, updated_at=now,
            )
        )
    session.flush()
    return session, CanonicalCoreStore(session, "workspace")


def _mention(store, generation, chunk="chunk-a", text="Bay H. Tahsin MERTER"):
    return store.persist_person_mention(
        generation_id=generation,
        document_id="document-a",
        document_version_id="version-a",
        logical_document_id="logical-a",
        chunk_id=chunk,
        span_start=10,
        span_end=10 + len(text),
        source_text=text,
        extractor_version="test",
    )


def test_curated_link_is_exact_mention_scoped_and_reused_by_a_new_generation():
    session, store = _store()
    target = store.decide_person(_mention(store, "generation-a", "target", "Hasan Tahsin Merter"))
    unresolved = _mention(store, "generation-a")
    assert store.decide_person(unresolved).decision == "UNRESOLVED"

    curated = HumanIdentityCurationStore(session, "workspace").decide(
        unresolved,
        action="LINK_TO_EXISTING",
        canonical_entity_id=target.canonical_entity_id,
        reason="Curator verified the exact source reference.",
    )
    replay = _mention(store, "generation-b")
    resolved = store.decide_person(replay)
    unrelated = _mention(store, "generation-b", "chunk-b", "H. Tahsin")

    assert curated.active
    assert resolved.decision == "LINK"
    assert resolved.canonical_entity_id == target.canonical_entity_id
    assert store.decide_person(unrelated).decision == "UNRESOLVED"


def test_keep_unresolved_remains_fail_closed_and_supersession_is_auditable():
    session, store = _store()
    target = store.decide_person(_mention(store, "generation-a", "target", "Hasan Tahsin Merter"))
    mention = _mention(store, "generation-a")
    store.decide_person(mention)
    curation = HumanIdentityCurationStore(session, "workspace")
    first = curation.decide(
        mention, action="KEEP_UNRESOLVED", canonical_entity_id=None, reason="Insufficient evidence."
    )
    assert store.decide_person(_mention(store, "generation-b")).decision == "UNRESOLVED"

    second = curation.decide(
        mention,
        action="LINK_TO_EXISTING",
        canonical_entity_id=target.canonical_entity_id,
        reason="Later source review verified the reference.",
    )

    assert not first.active
    assert second.previous_decision_id == first.id
    assert [item.id for item in curation.history(mention.id)] == [first.id, second.id]


def test_curated_link_can_supersede_an_automatically_created_candidate_in_a_new_generation():
    session, store = _store()
    target = store.decide_person(_mention(store, "generation-a", "target", "Tahsin Merter"))
    duplicate = _mention(store, "generation-a", "duplicate", "Tahsin Merter")
    assert store.decide_person(duplicate).decision == "NEW"

    HumanIdentityCurationStore(session, "workspace").decide(
        duplicate,
        action="LINK_TO_EXISTING",
        canonical_entity_id=target.canonical_entity_id,
        reason="Curator verified that the two exact source spans denote the same person.",
    )

    replay = _mention(store, "generation-b", "duplicate", "Tahsin Merter")
    resolved = store.decide_person(replay)

    assert resolved.decision == "LINK"
    assert resolved.canonical_entity_id == target.canonical_entity_id
