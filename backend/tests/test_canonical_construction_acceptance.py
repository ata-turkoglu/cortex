import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.knowledge.canonical_core import PROJECTION_VERSION, CanonicalCoreStore
from app.knowledge.extraction import (
    ExtractedEntityProperty,
    ExtractedMention,
    ExtractedRelation,
    ExtractedSpan,
    ExtractionMetadata,
    KnowledgeExtractionBundle,
)
from app.knowledge.pipeline import CorpusSnapshot, SourceChunk
from app.knowledge.production_executor import (
    ProductionKnowledgeExecutor,
    _bundle_payload,
)
from app.knowledge.source_manifest import write_generation_manifest
from app.models import (
    Base,
    CanonicalGenerationStatusRecord,
    CanonicalPropertyRecord,
    EntityMentionRecord,
    GenerationCanonicalMembershipRecord,
    IdentityDecisionRecord,
    KnowledgeGeneration,
    OwnershipAssertionRecord,
    RejectedAssertionBlockerRecord,
    Workspace,
)


def _span(content: str, text: str, start: int = 0) -> ExtractedSpan:
    offset = content.index(text, start)
    return ExtractedSpan("chunk-1", offset, offset + len(text), text, 1.0)


def _bundle(content: str, *, owns: bool, complete_property: bool) -> KnowledgeExtractionBundle:
    person = "Ayşe Merter"
    property_text = "İstanbul ili Kadıköy ilçesi Moda mahallesi 10 ada 5 parsel taşınmazı"
    property_span = _span(content, property_text)
    mentions = (
        ExtractedMention("person", "person", _span(content, person)),
        ExtractedMention("property", "asset_property", property_span),
    )
    values = ("İstanbul", "Kadıköy", "Moda", "10", "5")
    keys = ("province", "district", "neighborhood", "ada", "parsel")
    properties = tuple(
        ExtractedEntityProperty(
            "property", key, value, _span(content, value, property_span.start_offset)
        )
        for key, value in zip(keys, values, strict=True)
        if complete_property or key != "parsel"
    )
    relations = (
        (ExtractedRelation("owns", "person", "property", _span(content, content)),) if owns else ()
    )
    return KnowledgeExtractionBundle(
        ExtractionMetadata("run", "test", "test", "test", "test"),
        mentions=mentions,
        entity_properties=properties,
        relations=relations,
    )


def _fixture(tmp_path, *, owns: bool = True, complete_property: bool = True):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False)
    session = session_factory()
    now = datetime.now(UTC)
    workspace_id, generation_id = "workspace", "generation"
    content = (
        "Ayşe Merter, İstanbul ili Kadıköy ilçesi Moda mahallesi 10 ada 5 parsel "
        "taşınmazının malikidir."
    )
    chunk = SourceChunk(
        "chunk-1",
        "document",
        "version",
        "logical",
        0,
        content,
        hashlib.sha256(content.encode()).hexdigest(),
    )
    snapshot = CorpusSnapshot(workspace_id, "source", (chunk,))
    session.add(
        Workspace(
            id=workspace_id,
            slug=workspace_id,
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
            id=generation_id,
            workspace_id=workspace_id,
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
    root = tmp_path / "workspaces" / workspace_id / "knowledge-candidates"
    manifest = write_generation_manifest(tmp_path, snapshot, generation_id)
    generation = session.get(KnowledgeGeneration, generation_id)
    generation.source_manifest_uri = manifest.uri
    generation.source_manifest_hash = manifest.sha256
    generation.source_chunk_count = manifest.chunk_count
    session.commit()
    executor = ProductionKnowledgeExecutor.__new__(ProductionKnowledgeExecutor)
    executor.workspace_id = workspace_id
    executor.data_root = tmp_path
    executor.root = root
    executor.session_factory = session_factory
    artifact = root / generation_id / "extraction.json"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text(
        json.dumps(
            {
                "bundles": [
                    _bundle_payload(
                        _bundle(content, owns=owns, complete_property=complete_property)
                    )
                ]
            }
        ),
        encoding="utf-8",
    )
    return session, executor, snapshot, generation_id


def test_manifest_backed_constructor_persists_direct_ownership_and_is_idempotent(tmp_path):
    session, executor, snapshot, generation_id = _fixture(tmp_path)

    executor.identity_resolution(snapshot, generation_id)
    executor.identity_resolution(snapshot, generation_id)

    status = session.get(
        CanonicalGenerationStatusRecord, ("workspace", generation_id, PROJECTION_VERSION)
    )
    assert status.status == "READY"
    assert status.processed_chunk_count == 1
    assert status.assertion_count == 1
    assert (
        session.scalars(select(OwnershipAssertionRecord)).all()[0].relation_type
        == "document_supported_ownership"
    )


def test_nonownership_cooccurrence_is_safely_processed_and_label_bound_omissions_are_repaired(
    tmp_path,
):
    session, executor, snapshot, generation_id = _fixture(tmp_path, owns=False)
    executor.identity_resolution(snapshot, generation_id)
    cooccurrence = session.get(
        CanonicalGenerationStatusRecord, ("workspace", generation_id, PROJECTION_VERSION)
    )
    assert cooccurrence.status == "READY"
    assert cooccurrence.rejected_assertion_count == 0

    session, executor, snapshot, generation_id = _fixture(
        tmp_path / "incomplete", complete_property=False
    )
    executor.identity_resolution(snapshot, generation_id)
    repaired = session.get(
        CanonicalGenerationStatusRecord, ("workspace", generation_id, PROJECTION_VERSION)
    )
    assert repaired.status == "READY"
    assert repaired.rejected_assertion_count == 0
    assert len(session.scalars(select(OwnershipAssertionRecord)).all()) == 1


def test_invalid_countable_evidence_is_partial_and_never_persists_property_or_ownership(tmp_path):
    session, executor, snapshot, generation_id = _fixture(tmp_path)
    bundle = _bundle(snapshot.chunks[0].content, owns=True, complete_property=True)
    invalid_property = replace(
        bundle.mentions[1],
        span=replace(bundle.mentions[1].span, start_offset=0, end_offset=1, source_text="X"),
    )
    artifact = executor.root / generation_id / "extraction.json"
    invalid_bundle = replace(bundle, mentions=(bundle.mentions[0], invalid_property))
    artifact.write_text(
        json.dumps({"bundles": [_bundle_payload(invalid_bundle)]}), encoding="utf-8"
    )

    executor.identity_resolution(snapshot, generation_id)

    status = session.get(
        CanonicalGenerationStatusRecord, ("workspace", generation_id, PROJECTION_VERSION)
    )
    assert status.status == "PARTIAL"
    assert status.rejected_assertion_count > 0
    assert session.scalars(select(CanonicalPropertyRecord)).all() == []
    assert session.scalars(select(OwnershipAssertionRecord)).all() == []


def test_failed_manifest_chunk_can_be_corrected_without_duplicate_canonical_rows(tmp_path):
    session, executor, snapshot, generation_id = _fixture(tmp_path)
    valid = _bundle(snapshot.chunks[0].content, owns=True, complete_property=True)
    invalid = replace(
        valid,
        mentions=(
            replace(
                valid.mentions[0],
                candidate_canonical_entity_ids=("not-a-link",),
                candidate_provenance="adversarial acceptance fixture",
            ),
            valid.mentions[1],
        ),
    )
    artifact = executor.root / generation_id / "extraction.json"
    artifact.write_text(json.dumps({"bundles": [_bundle_payload(invalid)]}), encoding="utf-8")
    executor.identity_resolution(snapshot, generation_id)
    assert (
        session.get(
            CanonicalGenerationStatusRecord, ("workspace", generation_id, PROJECTION_VERSION)
        ).status
        == "FAILED"
    )

    artifact.write_text(json.dumps({"bundles": [_bundle_payload(valid)]}), encoding="utf-8")
    executor.identity_resolution(snapshot, generation_id)
    status = session.get(
        CanonicalGenerationStatusRecord, ("workspace", generation_id, PROJECTION_VERSION)
    )
    assert status.status == "READY"
    assert status.failed_chunk_count == 0
    assert len(session.scalars(select(CanonicalPropertyRecord)).all()) == 1
    assert len(session.scalars(select(OwnershipAssertionRecord)).all()) == 1


def test_property_identity_deduplicates_exact_values_but_not_near_collisions(tmp_path):
    session, _, _, _ = _fixture(tmp_path)
    store = CanonicalCoreStore(session, "workspace")
    base = {
        "province": "X",
        "district": "Y",
        "neighborhood": "Z",
        "ada": "303",
        "parsel": "16",
    }

    first = store.upsert_property(base)
    duplicate = store.upsert_property({**base, "province": " x "})
    near_collision = store.upsert_property({**base, "parsel": "17"})
    pafta_collision = store.upsert_property({**base, "pafta": "9"})
    section_collision = store.upsert_property({**base, "independent_section": "4"})
    session.commit()

    assert first is not None
    assert duplicate is not None and duplicate.id == first.id
    assert near_collision is not None and near_collision.id != first.id
    assert pafta_collision is not None and pafta_collision.id != first.id
    assert section_collision is not None and section_collision.id != first.id
    assert len(session.scalars(select(CanonicalPropertyRecord)).all()) == 4
    incomplete = {key: value for key, value in base.items() if key != "parsel"}
    assert store.upsert_property(incomplete) is None


def test_identical_property_identity_is_never_deduplicated_across_workspaces(tmp_path):
    session, _, _, _ = _fixture(tmp_path)
    now = datetime.now(UTC)
    session.add(
        Workspace(
            id="other-workspace",
            slug="other-workspace",
            name="Other",
            description=None,
            state="active",
            created_at=now,
            updated_at=now,
            deleted_at=None,
        )
    )
    session.commit()
    fields = {"province": "X", "district": "Y", "neighborhood": "Z", "ada": "303", "parsel": "16"}
    first = CanonicalCoreStore(session, "workspace").upsert_property(fields)
    second = CanonicalCoreStore(session, "other-workspace").upsert_property(fields)
    session.commit()
    assert first.id != second.id
    assert first.workspace_id != second.workspace_id


def test_workspace_and_generation_ownership_counts_never_leak(tmp_path):
    session, _, _, generation_id = _fixture(tmp_path)
    now = datetime.now(UTC)
    session.add_all(
        [
            Workspace(
                id="other-workspace",
                slug="other-workspace",
                name="Other",
                description=None,
                state="active",
                created_at=now,
                updated_at=now,
                deleted_at=None,
            ),
            KnowledgeGeneration(
                id="other-generation",
                workspace_id="other-workspace",
                source_fingerprint="other",
                state="building",
                failure_json=None,
                source_manifest_uri=None,
                source_manifest_hash=None,
                source_chunk_count=None,
                created_at=now,
                updated_at=now,
                activated_at=None,
            ),
            KnowledgeGeneration(
                id="generation-2",
                workspace_id="workspace",
                source_fingerprint="second",
                state="building",
                failure_json=None,
                source_manifest_uri=None,
                source_manifest_hash=None,
                source_chunk_count=None,
                created_at=now,
                updated_at=now,
                activated_at=None,
            ),
        ]
    )
    fields = {"province": "X", "district": "Y", "neighborhood": "Z", "ada": "303", "parsel": "16"}

    def person(store, generation, chunk):
        mention = store.persist_person_mention(
            generation_id=generation,
            document_id="d",
            document_version_id="v",
            logical_document_id="l",
            chunk_id=chunk,
            span_start=0,
            span_end=10,
            source_text="Ali Merter",
            extractor_version="test",
        )
        store.decide_person(mention)
        return mention

    left = CanonicalCoreStore(session, "workspace")
    right = CanonicalCoreStore(session, "other-workspace")
    left_person = person(left, generation_id, "left")
    person(right, "other-generation", "right")
    person(left, "generation-2", "second")
    prop = left.upsert_property(fields)
    prop_mention = left.persist_property_mention(
        generation_id=generation_id,
        document_id="d",
        document_version_id="v",
        logical_document_id="l",
        chunk_id="left",
        span_start=11,
        span_end=19,
        source_text="property",
        extractor_version="test",
    )
    left.persist_ownership_assertion(
        generation_id=generation_id,
        person_mention=left_person,
        property_mention=prop_mention,
        property_record=prop,
        span_start=0,
        span_end=19,
        source_text="Ali Merter property",
        assertion_rule_version="test",
    )
    left.rebuild_membership(generation_id)
    left.rebuild_membership("generation-2")
    right.rebuild_membership("other-generation")
    session.commit()
    assert left.ranked_people_by_surname(generation_id, "Merter") == [("Ali Merter", 1)]
    assert left.ranked_people_by_surname("generation-2", "Merter") == [("Ali Merter", 0)]
    assert right.ranked_people_by_surname("other-generation", "Merter") == [("Ali Merter", 0)]


def test_manifest_scope_and_identity_mismatches_fail_before_canonical_writes(tmp_path):
    session, executor, snapshot, generation_id = _fixture(tmp_path)
    variants = (
        replace(snapshot, chunks=(replace(snapshot.chunks[0], document_id="wrong-document"),)),
        replace(
            snapshot,
            chunks=(replace(snapshot.chunks[0], document_version_id="wrong-version"),),
        ),
        replace(snapshot, chunks=(replace(snapshot.chunks[0], content="tampered"),)),
    )
    for variant in variants:
        try:
            executor.identity_resolution(variant, generation_id)
        except ValueError:
            pass
        else:
            raise AssertionError("manifest mismatch must fail closed")
        assert session.scalars(select(OwnershipAssertionRecord)).all() == []
        assert session.scalars(select(CanonicalPropertyRecord)).all() == []


def test_manifest_unknown_chunk_and_person_property_spans_create_no_invalid_rows(tmp_path):
    session, executor, snapshot, generation_id = _fixture(tmp_path)
    valid = _bundle(snapshot.chunks[0].content, owns=True, complete_property=True)
    artifact = executor.root / generation_id / "extraction.json"
    invalid = replace(
        valid,
        mentions=(
            replace(valid.mentions[0], span=replace(valid.mentions[0].span, chunk_id="unknown")),
            valid.mentions[1],
        ),
    )
    artifact.write_text(json.dumps({"bundles": [_bundle_payload(invalid)]}), encoding="utf-8")
    executor.identity_resolution(snapshot, generation_id)
    assert session.scalars(select(OwnershipAssertionRecord)).all() == []
    assert session.scalars(select(CanonicalPropertyRecord)).all() == []


def test_constructor_rejects_workspace_mismatch_before_any_canonical_write(tmp_path):
    session, executor, snapshot, generation_id = _fixture(tmp_path)
    mismatched = CorpusSnapshot("other-workspace", snapshot.fingerprint, snapshot.chunks)

    try:
        executor.identity_resolution(mismatched, generation_id)
    except ValueError as error:
        assert "crosses executor workspace" in str(error)
    else:
        raise AssertionError("workspace-mismatched snapshot must fail closed")

    assert session.scalars(select(OwnershipAssertionRecord)).all() == []
    assert (
        session.get(
            CanonicalGenerationStatusRecord, ("workspace", generation_id, PROJECTION_VERSION)
        )
        is None
    )


def test_target_generation_rejects_wrong_snapshot_or_manifest_before_canonical_writes(tmp_path):
    session, executor, snapshot, generation_id = _fixture(tmp_path)
    now = datetime.now(UTC)
    target_generation = "generation-2"
    session.add(
        KnowledgeGeneration(
            id=target_generation,
            workspace_id="workspace",
            source_fingerprint="target-source",
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
    session.flush()
    target_snapshot = CorpusSnapshot("workspace", "target-source", snapshot.chunks)
    target_manifest = write_generation_manifest(tmp_path, target_snapshot, target_generation)
    target = session.get(KnowledgeGeneration, target_generation)
    target.source_manifest_uri = target_manifest.uri
    target.source_manifest_hash = target_manifest.sha256
    target.source_chunk_count = target_manifest.chunk_count
    session.commit()

    artifact = executor.root / target_generation / "extraction.json"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    target_bundle = _bundle(snapshot.chunks[0].content, owns=True, complete_property=True)
    artifact.write_text(
        json.dumps({"bundles": [_bundle_payload(target_bundle)]}),
        encoding="utf-8",
    )

    try:
        executor.identity_resolution(snapshot, target_generation)
    except ValueError as error:
        assert "snapshot does not match the target generation" in str(error)
    else:
        raise AssertionError("a G1 snapshot must not construct target G2")

    source_generation = session.get(KnowledgeGeneration, generation_id)
    target.source_manifest_uri = source_generation.source_manifest_uri
    target.source_manifest_hash = source_generation.source_manifest_hash
    target.source_chunk_count = source_generation.source_chunk_count
    session.commit()
    try:
        executor.identity_resolution(target_snapshot, target_generation)
    except Exception as error:
        assert "manifest generation mismatch" in str(error)
    else:
        raise AssertionError("a G1 manifest must not construct target G2")

    assert session.scalars(
        select(EntityMentionRecord).where(EntityMentionRecord.generation_id == target_generation)
    ).all() == []
    assert session.scalars(select(IdentityDecisionRecord)).all() == []
    assert session.scalars(
        select(GenerationCanonicalMembershipRecord).where(
            GenerationCanonicalMembershipRecord.generation_id == target_generation
        )
    ).all() == []
    assert session.scalars(
        select(OwnershipAssertionRecord).where(
            OwnershipAssertionRecord.generation_id == target_generation
        )
    ).all() == []
    assert session.get(
        CanonicalGenerationStatusRecord, ("workspace", target_generation, PROJECTION_VERSION)
    ) is None


def test_invalid_person_span_creates_no_person_identity_or_membership(tmp_path):
    session, executor, snapshot, generation_id = _fixture(tmp_path)
    valid = _bundle(snapshot.chunks[0].content, owns=True, complete_property=True)
    invalid_person = replace(
        valid.mentions[0],
        span=replace(valid.mentions[0].span, start_offset=0, end_offset=1, source_text="X"),
    )
    artifact = executor.root / generation_id / "extraction.json"
    invalid_bundle = replace(valid, mentions=(invalid_person, valid.mentions[1]))
    artifact.write_text(
        json.dumps({"bundles": [_bundle_payload(invalid_bundle)]}),
        encoding="utf-8",
    )

    executor.identity_resolution(snapshot, generation_id)

    assert session.scalars(
        select(EntityMentionRecord).where(EntityMentionRecord.entity_type == "person")
    ).all() == []
    assert session.scalars(select(IdentityDecisionRecord)).all() == []
    assert session.scalars(select(GenerationCanonicalMembershipRecord)).all() == []
    status = session.get(
        CanonicalGenerationStatusRecord, ("workspace", generation_id, PROJECTION_VERSION)
    )
    assert status.status == "PARTIAL"
    assert status.rejected_assertion_count > 0


def test_invalid_property_span_creates_no_property_or_ownership(tmp_path):
    session, executor, snapshot, generation_id = _fixture(tmp_path)
    valid = _bundle(snapshot.chunks[0].content, owns=True, complete_property=True)
    invalid_property = replace(
        valid.mentions[1],
        span=replace(valid.mentions[1].span, start_offset=0, end_offset=1, source_text="X"),
    )
    artifact = executor.root / generation_id / "extraction.json"
    invalid_bundle = replace(valid, mentions=(valid.mentions[0], invalid_property))
    artifact.write_text(
        json.dumps({"bundles": [_bundle_payload(invalid_bundle)]}),
        encoding="utf-8",
    )

    executor.identity_resolution(snapshot, generation_id)

    assert session.scalars(select(CanonicalPropertyRecord)).all() == []
    assert session.scalars(select(OwnershipAssertionRecord)).all() == []
    status = session.get(
        CanonicalGenerationStatusRecord, ("workspace", generation_id, PROJECTION_VERSION)
    )
    assert status.status == "PARTIAL"
    assert status.rejected_assertion_count > 0


def test_ownership_span_without_direct_ownership_support_creates_no_assertion(tmp_path):
    session, executor, snapshot, generation_id = _fixture(tmp_path)
    content = snapshot.chunks[0].content.replace("malikidir", "belgede birlikte geçmektedir")
    invalid_chunk = replace(
        snapshot.chunks[0],
        content=content,
        content_hash=hashlib.sha256(content.encode()).hexdigest(),
    )
    invalid_snapshot = CorpusSnapshot(
        snapshot.workspace_id, snapshot.fingerprint, (invalid_chunk,)
    )
    # Recreate the fixture manifest for this otherwise authoritative source.
    generation = session.get(KnowledgeGeneration, generation_id)
    manifest_path = tmp_path / generation.source_manifest_uri
    manifest_path.unlink()
    manifest = write_generation_manifest(tmp_path, invalid_snapshot, generation_id)
    generation.source_manifest_hash = manifest.sha256
    generation.source_chunk_count = manifest.chunk_count
    session.commit()
    valid = _bundle(content, owns=True, complete_property=True)
    artifact = executor.root / generation_id / "extraction.json"
    artifact.write_text(json.dumps({"bundles": [_bundle_payload(valid)]}), encoding="utf-8")

    executor.identity_resolution(invalid_snapshot, generation_id)

    assert session.scalars(select(OwnershipAssertionRecord)).all() == []
    status = session.get(
        CanonicalGenerationStatusRecord, ("workspace", generation_id, PROJECTION_VERSION)
    )
    assert status.status == "PARTIAL"
    assert status.rejected_assertion_count == 1
    blocker = session.scalar(select(RejectedAssertionBlockerRecord))
    assert blocker is not None
    assert blocker.potentially_countable is True
    assert blocker.relation_type == "owns"
    assert blocker.affected_dimension == "property_count"
    assert blocker.normalized_subject_surname == "merter"
    assert blocker.reason == "ownership assertion lacks direct local support"


def test_equal_property_counts_use_deterministic_name_then_id_tie_break(tmp_path):
    session, _executor, _snapshot, generation_id = _fixture(tmp_path)
    store = CanonicalCoreStore(session, "workspace")
    fields = {"province": "X", "district": "Y", "neighborhood": "Z", "ada": "303", "parsel": "16"}
    property_record = store.upsert_property(fields)
    for index, name in enumerate(("Fatma Merter", "Ayse Merter")):
        person = store.persist_person_mention(
            generation_id=generation_id,
            document_id=f"document-{index}",
            document_version_id=f"version-{index}",
            logical_document_id=f"logical-{index}",
            chunk_id=f"chunk-{index}",
            span_start=0,
            span_end=len(name),
            source_text=name,
            extractor_version="tie-fixture",
        )
        store.decide_person(person)
        property_mention = store.persist_property_mention(
            generation_id=generation_id,
            document_id=f"document-{index}",
            document_version_id=f"version-{index}",
            logical_document_id=f"logical-{index}",
            chunk_id=f"chunk-{index}",
            span_start=len(name) + 1,
            span_end=len(name) + 9,
            source_text="property",
            extractor_version="tie-fixture",
        )
        store.persist_ownership_assertion(
            generation_id=generation_id,
            person_mention=person,
            property_mention=property_mention,
            property_record=property_record,
            span_start=0,
            span_end=len(name) + 9,
            source_text=f"{name} property",
            assertion_rule_version="tie-fixture",
        )
    store.rebuild_membership(generation_id)
    session.commit()

    runs = [store.ranked_people_by_surname(generation_id, "Merter") for _ in range(3)]
    assert runs == [[("Ayse Merter", 1), ("Fatma Merter", 1)]] * 3


def _owned_bundle_for_chunk(
    chunk_id: str,
    content: str,
    person: str,
    *,
    owns: bool = True,
) -> KnowledgeExtractionBundle:
    property_text = "X province Y district Z neighborhood 303 ada 16 parsel property"
    property_span = ExtractedSpan(
        chunk_id,
        content.index(property_text),
        content.index(property_text) + len(property_text),
        property_text,
        1.0,
    )
    person_start = content.index(person)
    person_span = ExtractedSpan(chunk_id, person_start, person_start + len(person), person, 1.0)
    fields = ("X", "Y", "Z", "303", "16")
    keys = ("province", "district", "neighborhood", "ada", "parsel")
    return KnowledgeExtractionBundle(
        ExtractionMetadata("run", "test", "test", "test", "test"),
        mentions=(
            ExtractedMention("person", "person", person_span),
            ExtractedMention("property", "asset_property", property_span),
        ),
        entity_properties=tuple(
            ExtractedEntityProperty(
                "property",
                key,
                value,
                ExtractedSpan(
                    chunk_id,
                    content.index(value, property_span.start_offset),
                    content.index(value, property_span.start_offset) + len(value),
                    value,
                    1.0,
                ),
            )
            for key, value in zip(keys, fields, strict=True)
        ),
        relations=(
            ExtractedRelation(
                "owns", "person", "property", ExtractedSpan(chunk_id, 0, len(content), content, 1.0)
            ),
        )
        if owns
        else (),
    )


def test_production_multi_chunk_duplicate_property_is_deduplicated_in_sqlite_reader(tmp_path):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False)
    session = session_factory()
    now = datetime.now(UTC)
    session.add(
        Workspace(
            id="fixture-workspace",
            slug="fixture-workspace",
            name="Fixture workspace",
            description=None,
            state="active",
            created_at=now,
            updated_at=now,
            deleted_at=None,
        )
    )
    session.add(
        KnowledgeGeneration(
            id="fixture-generation",
            workspace_id="fixture-workspace",
            source_fingerprint="fixture-source",
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
    contents = (
        "Ali Merter owns X province Y district Z neighborhood 303 ada 16 parsel property.",
        "Ali Merter owns X province Y district Z neighborhood 303 ada 16 parsel property.",
    )
    chunks = tuple(
        SourceChunk(
            f"chunk-{index}",
            f"document-{index}",
            f"version-{index}",
            f"logical-{index}",
            index,
            content,
            hashlib.sha256(content.encode()).hexdigest(),
        )
        for index, content in enumerate(contents)
    )
    snapshot = CorpusSnapshot("fixture-workspace", "fixture-source", chunks)
    manifest = write_generation_manifest(tmp_path, snapshot, "fixture-generation")
    generation = session.get(KnowledgeGeneration, "fixture-generation")
    generation.source_manifest_uri = manifest.uri
    generation.source_manifest_hash = manifest.sha256
    generation.source_chunk_count = manifest.chunk_count
    session.commit()
    executor = ProductionKnowledgeExecutor.__new__(ProductionKnowledgeExecutor)
    executor.workspace_id = "fixture-workspace"
    executor.data_root = tmp_path
    executor.root = tmp_path / "workspaces" / "fixture-workspace" / "knowledge-candidates"
    executor.session_factory = session_factory
    artifact = executor.root / "fixture-generation" / "extraction.json"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text(
        json.dumps(
            {
                "bundles": [
                    _bundle_payload(
                        _owned_bundle_for_chunk(chunk.chunk_id, chunk.content, "Ali Merter")
                    )
                    for chunk in chunks
                ]
            }
        ),
        encoding="utf-8",
    )

    executor.identity_resolution(snapshot, "fixture-generation")

    session.expire_all()
    status = session.get(
        CanonicalGenerationStatusRecord,
        ("fixture-workspace", "fixture-generation", PROJECTION_VERSION),
    )
    assert status.status == "READY"
    assert status.safe_property_count == 1
    assert status.assertion_count == 2
    assert len(session.scalars(select(CanonicalPropertyRecord)).all()) == 1
    assert CanonicalCoreStore(session, "fixture-workspace").ranked_people_by_surname(
        "fixture-generation", "Merter"
    ) == [("Ali Merter", 1)]


def test_production_explicit_identity_candidate_links_repeated_person_in_later_generation(tmp_path):
    session, executor, snapshot, generation_id = _fixture(tmp_path)
    executor.identity_resolution(snapshot, generation_id)
    session.expire_all()
    first = session.scalars(select(IdentityDecisionRecord)).one()
    assert first.decision == "NEW"

    next_generation = "generation-2"
    now = datetime.now(UTC)
    session.add(
        KnowledgeGeneration(
            id=next_generation,
            workspace_id="workspace",
            source_fingerprint="source-2",
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
    chunk = snapshot.chunks[0]
    next_snapshot = CorpusSnapshot("workspace", "source-2", (chunk,))
    manifest = write_generation_manifest(tmp_path, next_snapshot, next_generation)
    generation = session.get(KnowledgeGeneration, next_generation)
    generation.source_manifest_uri = manifest.uri
    generation.source_manifest_hash = manifest.sha256
    generation.source_chunk_count = manifest.chunk_count
    bundle = _bundle(chunk.content, owns=True, complete_property=True)
    person = replace(
        bundle.mentions[0],
        candidate_canonical_entity_ids=(first.canonical_entity_id,),
        candidate_provenance="prior accepted canonical mention in fixture generation",
    )
    artifact = executor.root / next_generation / "extraction.json"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    linked_bundle = replace(bundle, mentions=(person, bundle.mentions[1]))
    artifact.write_text(
        json.dumps({"bundles": [_bundle_payload(linked_bundle)]}),
        encoding="utf-8",
    )
    session.commit()

    executor.identity_resolution(next_snapshot, next_generation)
    session.expire_all()
    decisions = session.scalars(
        select(IdentityDecisionRecord).where(IdentityDecisionRecord.workspace_id == "workspace")
    ).all()
    assert {item.decision for item in decisions} == {"NEW", "LINK"}
    linked = next(item for item in decisions if item.decision == "LINK")
    assert linked.canonical_entity_id == first.canonical_entity_id
