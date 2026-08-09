"""Durable accounting for individual GraphRAG stages."""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import GraphRagStageReport


def record_stage_usage(
    session: Session,
    workspace_id: str,
    *,
    stage: str,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    estimated_cost_usd: float | None = None,
    provider: str | None = None,
    model: str | None = None,
    request_count: int | None = None,
    duration_ms: int | None = None,
    query_run_id: str | None = None,
) -> GraphRagStageReport:
    values = (input_tokens, output_tokens, estimated_cost_usd, request_count, duration_ms)
    if any(value is not None and value < 0 for value in values):
        raise ValueError("GraphRAG usage values cannot be negative")
    report = GraphRagStageReport(
        id=str(uuid4()),
        workspace_id=workspace_id,
        stage=stage,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        estimated_cost_usd=estimated_cost_usd,
        provider=provider,
        model=model,
        request_count=request_count,
        duration_ms=duration_ms,
        query_run_id=query_run_id,
        created_at=datetime.now(UTC),
    )
    session.add(report)
    return report


def stage_cost_total(session: Session, workspace_id: str, stage: str) -> float:
    reports = session.scalars(
        select(GraphRagStageReport).where(
            GraphRagStageReport.workspace_id == workspace_id,
            GraphRagStageReport.stage == stage,
        )
    )
    return sum(report.estimated_cost_usd or 0.0 for report in reports)
