from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.accounting import NormalizedUsage, RateCard, calculate_cost, persist_usage, totals
from app.models import Base, QueryRun, Workspace


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    now, workspace_id, query_id = datetime.now(UTC), str(uuid4()), str(uuid4())
    session.add(
        Workspace(
            id=workspace_id,
            slug="usage",
            name="Usage",
            state="active",
            created_at=now,
            updated_at=now,
        )
    )
    session.add(
        QueryRun(
            id=query_id,
            workspace_id=workspace_id,
            conversation_id=None,
            query_text="q",
            state="completed",
            input_tokens=0,
            output_tokens=0,
            estimated_cost_usd=0,
            created_at=now,
            updated_at=now,
        )
    )
    session.commit()
    return session, workspace_id, query_id


def test_cost_uses_decimal_rate_categories_and_local_is_zero(monkeypatch):
    card = RateCard("openai", "priced", Decimal("2"), Decimal("10"), Decimal("0.5"))
    monkeypatch.setattr("app.accounting.RATE_CARDS", (card,))
    cost, status, currency, version, snapshot = calculate_cost(
        "openai",
        "priced",
        NormalizedUsage(input_tokens=1_000_000, output_tokens=100_000, cached_input_tokens=200_000),
    )
    assert cost == Decimal("2.7")
    assert (status, currency, version) == ("exact", "USD", card.version)
    assert snapshot and snapshot["rate_entry"] == "openai:priced"
    assert calculate_cost("ollama", "local", NormalizedUsage())[0:2] == (Decimal("0"), "local_zero")
    assert calculate_cost("openai", "unknown", NormalizedUsage(input_tokens=1))[0:2] == (
        None,
        "unavailable",
    )


def test_usage_events_are_idempotent_and_aggregate_real_calls(monkeypatch):
    session, workspace_id, query_id = _session()
    card = RateCard("openai", "priced", Decimal("1"), Decimal("2"))
    monkeypatch.setattr("app.accounting.RATE_CARDS", (card,))
    first = persist_usage(
        session,
        workspace_id=workspace_id,
        query_run_id=query_id,
        stage="answer_synthesis",
        provider="openai",
        model="priced",
        usage=NormalizedUsage(10, 2, 12, source="provider_reported"),
        idempotency_key="provider-response-1",
    )
    duplicate = persist_usage(
        session,
        workspace_id=workspace_id,
        query_run_id=query_id,
        stage="answer_synthesis",
        provider="openai",
        model="priced",
        usage=NormalizedUsage(10, 2, 12, source="provider_reported"),
        idempotency_key="provider-response-1",
    )
    second = persist_usage(
        session,
        workspace_id=workspace_id,
        query_run_id=query_id,
        stage="answer_regeneration",
        provider="openai",
        model="priced",
        usage=NormalizedUsage(5, 3, 8, source="provider_reported"),
        idempotency_key="provider-response-2",
    )
    session.commit()
    report = totals(session, workspace_id=workspace_id, query_run_id=query_id)
    assert first.id == duplicate.id and second.id != first.id
    assert (
        report["model_calls"],
        report["input_tokens"],
        report["output_tokens"],
        report["total_tokens"],
    ) == (2, 15, 5, 20)
    assert report["recorded"] is True


def test_scoped_idempotency_and_pricing_snapshot_are_immutable(monkeypatch):
    session, workspace_id, _ = _session()
    first_card = RateCard("openai", "priced", Decimal("1"), Decimal("2"), version="v1")
    monkeypatch.setattr("app.accounting.RATE_CARDS", (first_card,))
    first = persist_usage(
        session,
        workspace_id=workspace_id,
        stage="answer",
        provider="openai",
        model="priced",
        usage=NormalizedUsage(input_tokens=1_000_000),
        idempotency_key="same",
    )
    monkeypatch.setattr(
        "app.accounting.RATE_CARDS",
        (RateCard("openai", "priced", Decimal("2"), Decimal("2"), version="v2"),),
    )
    second = persist_usage(
        session,
        workspace_id=workspace_id,
        stage="answer",
        provider="openai",
        model="priced",
        usage=NormalizedUsage(input_tokens=1_000_000),
        idempotency_key="new",
    )
    assert Decimal(first.cost_amount) == Decimal("1")
    assert '"rate_card_version": "v1"' in (first.pricing_snapshot_json or "")
    assert Decimal(second.cost_amount) == Decimal("2")
