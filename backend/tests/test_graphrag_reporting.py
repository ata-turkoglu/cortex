from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.graphrag.reporting import record_stage_usage, stage_cost_total
from app.models import Base, Workspace


def test_graphrag_stage_usage_is_workspace_scoped_and_aggregated():
    engine = create_engine("sqlite:///:memory:")
    session = sessionmaker(bind=engine)()
    Base.metadata.create_all(engine)
    now = datetime.now(UTC)
    first = Workspace(
        id=str(uuid4()),
        slug="usage-a",
        name="Usage A",
        state="active",
        created_at=now,
        updated_at=now,
    )
    second = Workspace(
        id=str(uuid4()),
        slug="usage-b",
        name="Usage B",
        state="active",
        created_at=now,
        updated_at=now,
    )
    session.add_all([first, second])
    record_stage_usage(
        session,
        first.id,
        stage="entity_extraction",
        input_tokens=10,
        output_tokens=2,
        estimated_cost_usd=0.1,
    )
    record_stage_usage(
        session,
        first.id,
        stage="entity_extraction",
        input_tokens=20,
        output_tokens=3,
        estimated_cost_usd=0.2,
    )
    record_stage_usage(
        session,
        second.id,
        stage="entity_extraction",
        input_tokens=20,
        output_tokens=3,
        estimated_cost_usd=0.9,
    )
    session.commit()
    assert stage_cost_total(session, first.id, "entity_extraction") == 0.30000000000000004
