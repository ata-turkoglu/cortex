"""Provider-neutral usage normalization, pricing, persistence, and aggregation."""

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .models import UsageEvent

RATE_CARD_VERSION = "cortex-v1-2026-08"


@dataclass(frozen=True)
class NormalizedUsage:
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    cached_input_tokens: int | None = None
    cache_creation_tokens: int | None = None
    reasoning_tokens: int | None = None
    embedding_tokens: int | None = None
    source: str = "unavailable"  # provider_reported, estimated, unavailable
    raw: dict[str, object] | None = None


@dataclass(frozen=True)
class RateCard:
    provider: str
    model: str
    input_per_million: Decimal
    output_per_million: Decimal
    cached_input_per_million: Decimal = Decimal("0")
    cache_creation_per_million: Decimal | None = None
    reasoning_per_million: Decimal | None = None
    embedding_per_million: Decimal | None = None
    version: str = RATE_CARD_VERSION
    currency: str = "USD"
    source: str = "cortex-rate-card"


# Deliberately versioned defaults. Unknown models are never assumed free; deployments may
# add/replace cards here without changing accounting behavior.
RATE_CARDS: tuple[RateCard, ...] = (
    # Source-controlled, operator-reviewed baseline card. Exact model IDs only; update this
    # versioned registry when a provider changes published pricing.
    RateCard("openai", "gpt-4.1", Decimal("2.00"), Decimal("8.00"), Decimal("0.50")),
    RateCard("openai", "gpt-4.1-mini", Decimal("0.40"), Decimal("1.60"), Decimal("0.10")),
    RateCard("openai", "gpt-5.6-luna", Decimal("2.00"), Decimal("8.00"), Decimal("0.50")),
)


def rate_for(provider: str, model: str) -> RateCard | None:
    return next(
        (card for card in RATE_CARDS if card.provider == provider and card.model == model), None
    )


def _snapshot(card: RateCard | None, *, status: str, provider: str) -> dict[str, object] | None:
    if not card:
        return None
    return {
        "rate_card_version": card.version,
        "rate_entry": f"{card.provider}:{card.model}",
        "source": card.source,
        "currency": card.currency,
        "unit": "per_1m_tokens",
        "input_per_million": str(card.input_per_million),
        "cached_input_per_million": str(card.cached_input_per_million),
        "output_per_million": str(card.output_per_million),
        "cache_creation_per_million": (
            str(card.cache_creation_per_million)
            if card.cache_creation_per_million is not None
            else None
        ),
        "reasoning_per_million": (
            str(card.reasoning_per_million) if card.reasoning_per_million is not None else None
        ),
        "embedding_per_million": (
            str(card.embedding_per_million) if card.embedding_per_million is not None else None
        ),
        "cost_status": status,
        "provider": provider,
    }


def calculate_cost(
    provider: str, model: str, usage: NormalizedUsage
) -> tuple[Decimal | None, str, str | None, str | None, dict[str, object] | None]:
    if provider == "ollama":
        return (
            Decimal("0"),
            "local_zero",
            "USD",
            RATE_CARD_VERSION,
            {"source": "local_provider", "cost_status": "local_zero"},
        )
    card = rate_for(provider, model)
    if not card:
        return None, "unavailable", None, None, None
    if (
        usage.input_tokens is None
        and usage.output_tokens is None
        and usage.embedding_tokens is None
    ):
        return (
            None,
            "unavailable",
            card.currency,
            card.version,
            _snapshot(card, status="unavailable", provider=provider),
        )
    input_tokens = Decimal(usage.input_tokens or 0)
    cached = Decimal(usage.cached_input_tokens or 0)
    normal_input = max(Decimal("0"), input_tokens - cached)
    amount = normal_input * card.input_per_million / Decimal("1000000")
    amount += cached * card.cached_input_per_million / Decimal("1000000")
    amount += Decimal(usage.output_tokens or 0) * card.output_per_million / Decimal("1000000")
    if usage.embedding_tokens is not None and card.embedding_per_million is not None:
        amount += Decimal(usage.embedding_tokens) * card.embedding_per_million / Decimal("1000000")
    if usage.cache_creation_tokens is not None and card.cache_creation_per_million is not None:
        amount += (
            Decimal(usage.cache_creation_tokens)
            * card.cache_creation_per_million
            / Decimal("1000000")
        )
    # Reasoning is normally included in provider output tokens. Charge it only when an explicit
    # rate exists and the provider supplies it as a distinct category.
    if usage.reasoning_tokens is not None and card.reasoning_per_million is not None:
        amount += Decimal(usage.reasoning_tokens) * card.reasoning_per_million / Decimal("1000000")
    return (
        amount,
        "exact",
        card.currency,
        card.version,
        _snapshot(card, status="exact", provider=provider),
    )


def persist_usage(
    session: Session,
    *,
    workspace_id: str,
    stage: str,
    provider: str,
    model: str,
    usage: NormalizedUsage,
    idempotency_key: str,
    query_run_id: str | None = None,
    workflow_run_id: str | None = None,
    workflow_step_id: str | None = None,
    provider_request_id: str | None = None,
) -> UsageEvent:
    canonical_key = f"{workspace_id}:{provider}:{idempotency_key}"
    existing = session.scalar(select(UsageEvent).where(UsageEvent.idempotency_key == canonical_key))
    if existing:
        return existing
    cost, cost_status, currency, version, snapshot = calculate_cost(provider, model, usage)
    event = UsageEvent(
        id=str(uuid4()),
        workspace_id=workspace_id,
        query_run_id=query_run_id,
        workflow_run_id=workflow_run_id,
        workflow_step_id=workflow_step_id,
        stage=stage,
        provider=provider,
        model=model,
        provider_request_id=provider_request_id,
        idempotency_key=canonical_key,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        total_tokens=usage.total_tokens,
        cached_input_tokens=usage.cached_input_tokens,
        cache_creation_tokens=usage.cache_creation_tokens,
        reasoning_tokens=usage.reasoning_tokens,
        embedding_tokens=usage.embedding_tokens,
        usage_source=usage.source,
        cost_status=cost_status,
        cost_amount=cost,
        currency=currency,
        pricing_version=version,
        pricing_snapshot_json=json.dumps(snapshot, sort_keys=True) if snapshot else None,
        diagnostic=("rate_unavailable" if cost_status == "unavailable" else None),
        provider_usage_json=json.dumps(usage.raw, ensure_ascii=False) if usage.raw else None,
        created_at=datetime.now(UTC),
    )
    try:
        with session.begin_nested():
            session.add(event)
            session.flush()
    except IntegrityError:
        return session.scalar(select(UsageEvent).where(UsageEvent.idempotency_key == canonical_key))
    return event


def totals(
    session: Session,
    *,
    workspace_id: str,
    query_run_id: str | None = None,
    workflow_run_id: str | None = None,
) -> dict[str, object]:
    statement = select(UsageEvent).where(UsageEvent.workspace_id == workspace_id)
    if query_run_id:
        statement = statement.where(UsageEvent.query_run_id == query_run_id)
    if workflow_run_id:
        statement = statement.where(UsageEvent.workflow_run_id == workflow_run_id)
    events = session.scalars(statement.order_by(UsageEvent.created_at)).all()
    if not events:
        return {
            "recorded": False,
            "model_calls": 0,
            "input_tokens": None,
            "output_tokens": None,
            "total_tokens": None,
            "cost": None,
            "currency": None,
            "calls": [],
        }

    def summed(name: str):
        values = [getattr(event, name) for event in events]
        return (
            sum(value for value in values if value is not None)
            if any(value is not None for value in values)
            else None
        )

    amounts = [event.cost_amount for event in events]
    cost_complete = all(event.cost_status in {"exact", "local_zero"} for event in events)

    def breakdown(key: str) -> list[dict[str, object]]:
        groups: dict[str, list[UsageEvent]] = {}
        for event in events:
            groups.setdefault(str(getattr(event, key)), []).append(event)
        return [
            {
                key: value,
                "model_calls": len(group),
                "total_tokens": sum(item.total_tokens or 0 for item in group),
            }
            for value, group in groups.items()
        ]

    provider_model_groups: dict[tuple[str, str], list[UsageEvent]] = {}
    for event in events:
        provider_model_groups.setdefault((event.provider, event.model), []).append(event)

    return {
        "recorded": True,
        "model_calls": len(events),
        "input_tokens": summed("input_tokens"),
        "output_tokens": summed("output_tokens"),
        "total_tokens": summed("total_tokens"),
        "cost": (
            str(sum((Decimal(value) for value in amounts if value is not None), Decimal("0")))
            if cost_complete and any(value is not None for value in amounts)
            else None
        ),
        "cost_status": "complete" if cost_complete else "unavailable",
        "currency": next((event.currency for event in events if event.currency), None),
        "stage_breakdown": breakdown("stage"),
        "provider_model_breakdown": [
            {
                "provider": provider,
                "model": model,
                "model_calls": len(group),
                "total_tokens": sum(item.total_tokens or 0 for item in group),
            }
            for (provider, model), group in provider_model_groups.items()
        ],
        "calls": [
            {
                "id": event.id,
                "stage": event.stage,
                "provider": event.provider,
                "model": event.model,
                "input_tokens": event.input_tokens,
                "output_tokens": event.output_tokens,
                "total_tokens": event.total_tokens,
                "cost": str(event.cost_amount) if event.cost_amount is not None else None,
                "cost_status": event.cost_status,
                "usage_source": event.usage_source,
                "diagnostic": event.diagnostic,
                "pricing_version": event.pricing_version,
                "pricing_snapshot": (
                    json.loads(event.pricing_snapshot_json) if event.pricing_snapshot_json else None
                ),
            }
            for event in events
        ],
    }
