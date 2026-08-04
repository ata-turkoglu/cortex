from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import text

from .database import SessionLocal


@dataclass(frozen=True)
class UsageRecord:
    layer: str
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float
    created_at: datetime


class UsageLedger:
    """Phase-3 in-process ledger; Phase 4 persists this in SQLite."""

    def __init__(self) -> None:
        self.records: list[UsageRecord] = []

    def record(
        self,
        layer: str,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        estimated_cost_usd: float,
    ) -> UsageRecord:
        record = UsageRecord(
            layer,
            provider,
            model,
            input_tokens,
            output_tokens,
            estimated_cost_usd,
            datetime.now(UTC),
        )
        self.records.append(record)
        statement = text(
            "INSERT INTO usage_records (layer, provider, model, input_tokens, output_tokens, "
            "estimated_cost_usd, created_at) VALUES (:layer, :provider, :model, :input, "
            ":output, :cost, :created)"
        )
        with SessionLocal.begin() as session:
            session.execute(
                statement,
                {
                    "layer": layer,
                    "provider": provider,
                    "model": model,
                    "input": input_tokens,
                    "output": output_tokens,
                    "cost": estimated_cost_usd,
                    "created": record.created_at,
                },
            )
        return record

    def total_cost(self) -> float:
        with SessionLocal() as session:
            return float(
                session.execute(
                    text("SELECT COALESCE(SUM(estimated_cost_usd), 0) FROM usage_records")
                ).scalar_one()
            )


usage_ledger = UsageLedger()
