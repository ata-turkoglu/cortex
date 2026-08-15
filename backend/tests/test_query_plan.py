from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.chat.query_plan import plan_query, resolve_entities, retrieval_queries
from app.models import Base, Chunk, Document, DocumentVersion, Workspace


def test_core_query_operations_and_safety_flags():
    assert plan_query("Berke kim?").operation == "identify"
    assert plan_query("Hasan Tahsin Merter hakkında neler biliyoruz?").operation == "describe"
    assert plan_query("Berke hangi belgelerde geçiyor?").operation == "lookup_documents"
    timeline = plan_query("1988'de Berke ile ilgili ne olmuş?")
    assert timeline.operation == "timeline"
    assert timeline.constraints.date_start == "1988"
    count = plan_query("Hasan Tahsin Merter'in kaç adet tapusu var?")
    assert (count.operation, count.requires_aggregation, count.requires_exhaustive_retrieval) == (
        "count",
        True,
        True,
    )
    listing = plan_query("Berke'nin hangi malları var?")
    assert listing.operation == "list" and listing.requires_exhaustive_retrieval
    assert count.entities[0].mention == "Hasan Tahsin Merter"
    assert listing.entities[0].mention == "Berke"
    parcel_count = plan_query("Mehmet Berke Merter kaç farklı parselde hissedar?")
    assert parcel_count.entities[0].mention == "Mehmet Berke Merter"
    assert parcel_count.aggregation_type == "distinct_parcel"


def test_aggregation_routing_requires_inventory_or_count_semantics():
    normal = (
        "Berke kim?",
        "Berke hakkinda ne biliyoruz?",
        "Berke'nin mallari hakkinda ne biliyoruz?",
        "Bu arsivde neler var?",
        "1980'lerde neler olmus?",
    )
    for query in normal:
        plan = plan_query(query)
        assert plan.requires_aggregation is False
        assert plan.requires_exhaustive_retrieval is False
    for query in (
        "Berke'nin hangi mallari var?",
        "Berke'nin tum tasinmazlarini listele.",
        "Mehmet Berke Merter hangi parsellerde hissedar?",
        "Hasan Tahsin Merter kac adet tapusu var?",
    ):
        plan = plan_query(query)
        assert plan.target == "property"
        assert plan.requires_aggregation is True
        assert plan.requires_exhaustive_retrieval is True


def test_describe_possessive_property_tail_leaves_a_person_mention():
    plan = plan_query("Berke'nin malları hakkında ne biliyoruz?")

    assert plan.operation == "describe"
    assert plan.entities[0].mention == "Berke"


def test_entity_resolution_uses_only_workspace_chunk_evidence():
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
            slug="plan",
            name="Plan",
            state="active",
            created_at=now,
            updated_at=now,
        )
    )
    session.add(
        Document(
            id=document_id,
            workspace_id=workspace_id,
            title="Kayit",
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
    session.add(
        Chunk(
            id=str(uuid4()),
            workspace_id=workspace_id,
            document_id=document_id,
            document_version_id=version_id,
            ordinal=0,
            content="Mehmet Berke Merter tapu kaydında hissedar olarak geçer.",
            content_hash="chunk",
            created_at=now,
        )
    )
    session.commit()

    plan = resolve_entities(session, workspace_id, plan_query("Berke kim?"))

    assert plan.entities[0].resolved_value == "Mehmet Berke Merter"
    assert "Mehmet Berke Merter" in retrieval_queries("Berke kim?", plan)
