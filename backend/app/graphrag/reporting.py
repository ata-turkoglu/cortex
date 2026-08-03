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
    input_tokens: int,
    output_tokens: int,
    estimated_cost_usd: float,
    provider: str | None = None,
    model: str | None = None,
) -> GraphRagStageReport:
    if min(input_tokens, output_tokens, estimated_cost_usd) < 0:
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
    return sum(report.estimated_cost_usd for report in reports)
