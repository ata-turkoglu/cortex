from datetime import UTC, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.knowledge.canonical_completeness import CanonicalCompletenessEvaluator
from app.knowledge.canonical_core import CanonicalCoreStore
from app.models import Base, KnowledgeGeneration, Workspace
from app.query.ir.schemas import (
    CountNode,
    CoverageContract,
    FieldReference,
    FilterNode,
    LogicalQueryIR,
    OutputProjection,
    RelationAggregateNode,
    RelationReference,
    ScanNode,
)


def _session():
    engine = create_engine("sqlite:///:memory:")
    session = sessionmaker(bind=engine)()
    Base.metadata.create_all(engine)
    now = datetime.now(UTC)
    session.add(
        Workspace(
            id="workspace",
            slug="workspace",
            name="Workspace",
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
            state="active",
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
    return session


def _ir(*, surname: str, count: bool = False, rank: bool = False):
    scan = ScanNode(
        node_id="people",
        workspace_id="workspace",
        resource="person",
        output_type="entity_set",
        population_mode="exhaustive",
    )
    filtered = FilterNode(
        node_id="surname",
        inputs=("people",),
        output_type="entity_set",
        field=FieldReference(resource="person", field="surname"),
        comparator="eq",
        value=surname,
    )
    nodes = [scan, filtered]
    root = "surname"
    shape = "entities"
    if count:
        nodes.append(CountNode(node_id="count", inputs=(root,), output_type="scalar"))
        root, shape = "count", "scalar"
    if rank:
        nodes.append(
            RelationAggregateNode(
                node_id="rank",
                inputs=(root,),
                relation=RelationReference(
                    relation="owns", source_resource="person", target_resource="asset_property"
                ),
                target_identity_field=FieldReference(resource="asset_property", field="entity_id"),
            )
        )
        root, shape = "rank", "entities"
    return LogicalQueryIR(
        workspace_id="workspace",
        state="resolved",
        nodes=tuple(nodes),
        root_ids=(root,),
        output=OutputProjection(shape=shape),
        coverage=CoverageContract(
            mode="exhaustive",
            population_boundary="people constrained by governed surname",
            same_generation_required=True,
        ),
    )


def _unfiltered_person_list_ir():
    scan = ScanNode(
        node_id="people",
        workspace_id="workspace",
        resource="person",
        output_type="entity_set",
        population_mode="exhaustive",
    )
    return LogicalQueryIR(
        workspace_id="workspace",
        state="resolved",
        nodes=(scan,),
        root_ids=(scan.node_id,),
        output=OutputProjection(shape="entities"),
        coverage=CoverageContract(
            mode="exhaustive",
            population_boundary="all people in the active corpus",
            same_generation_required=True,
        ),
    )


def _unresolved(store, raw_text: str, offset: int):
    mention = store.persist_person_mention(
        generation_id="generation",
        document_id="document",
        document_version_id="version",
        logical_document_id="logical",
        chunk_id=f"chunk-{offset}",
        span_start=offset,
        span_end=offset + len(raw_text),
        source_text=raw_text,
        extractor_version="test",
    )
    assert store.decide_person(mention).decision == "UNRESOLVED"


def test_global_unresolved_evidence_is_scoped_to_its_explicit_surname():
    session = _session()
    store = CanonicalCoreStore(session, "workspace")
    _unresolved(store, "Bay H. Tahsin Merter", 0)
    _unresolved(store, "A.B.", 30)
    evaluator = CanonicalCompletenessEvaluator(session, "workspace")

    merter = evaluator.evaluate("generation", _ir(surname="Merter"), known_count=3)
    yilmaz = evaluator.evaluate("generation", _ir(surname="Yılmaz"), known_count=2)

    assert merter.status == "PARTIAL"
    assert merter.relevant_unresolved_count == 1
    assert merter.affected_dimensions == ("population",)
    assert merter.evidence_refs[0].raw_text == "Bay H. Tahsin Merter"
    assert merter.known_count == merter.min_count == 3
    assert merter.additional_population_possible is True
    assert yilmaz.status == "COMPLETE"
    assert yilmaz.relevant_unresolved_count == 0


def test_unfiltered_person_list_is_partial_when_any_person_identity_is_unresolved():
    session = _session()
    store = CanonicalCoreStore(session, "workspace")
    _unresolved(store, "Bay H. Tahsin Merter", 0)
    _unresolved(store, "A.B.", 30)

    report = CanonicalCompletenessEvaluator(session, "workspace").evaluate(
        "generation", _unfiltered_person_list_ir(), known_count=84
    )

    assert report.status == "PARTIAL"
    assert report.scope == "all Persons in the active corpus"
    assert report.relevant_unresolved_count == 2
    assert report.affected_dimensions == ("population",)
    assert report.additional_population_possible is True


def test_count_and_known_row_ranking_expose_only_the_dimensions_they_affect():
    session = _session()
    store = CanonicalCoreStore(session, "workspace")
    _unresolved(store, "Bay H. Tahsin Merter", 0)
    evaluator = CanonicalCompletenessEvaluator(session, "workspace")

    count = evaluator.evaluate("generation", _ir(surname="Merter", count=True), known_count=3)
    rank = evaluator.evaluate("generation", _ir(surname="Merter", rank=True), known_count=3)

    assert count.affected_dimensions == ("population", "count")
    assert rank.affected_dimensions == ("population", "ranking")
    assert "property_count" not in rank.affected_dimensions


def test_rejected_ownership_blocker_is_scoped_to_its_surname_and_metric():
    session = _session()
    store = CanonicalCoreStore(session, "workspace")
    mention = store.persist_person_mention(
        generation_id="generation",
        document_id="document",
        document_version_id="version",
        logical_document_id="logical",
        chunk_id="chunk-ownership",
        span_start=0,
        span_end=len("Bay H. Tahsin Merter"),
        source_text="Bay H. Tahsin Merter",
        extractor_version="test",
    )
    store.persist_rejected_ownership_blocker(
        generation_id="generation",
        person_mention=mention,
        span_start=30,
        span_end=34,
        source_text="owns",
        reason="ownership assertion lacks direct local support",
    )
    evaluator = CanonicalCompletenessEvaluator(session, "workspace")

    merter_rank = evaluator.evaluate("generation", _ir(surname="Merter", rank=True), known_count=3)
    merter_list = evaluator.evaluate("generation", _ir(surname="Merter"), known_count=3)
    yilmaz_rank = evaluator.evaluate("generation", _ir(surname="YÄ±lmaz", rank=True), known_count=2)

    assert merter_rank.status == "PARTIAL"
    assert merter_rank.relevant_rejected_assertion_count == 1
    assert merter_rank.affected_dimensions == ("property_count", "ranking")
    assert merter_rank.evidence_refs[0].reason == "ownership assertion lacks direct local support"
    assert merter_list.status == "COMPLETE"
    assert yilmaz_rank.status == "COMPLETE"
