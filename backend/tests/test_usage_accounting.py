from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.accounting import budget_status, persist_usage, usage_from_generated
from app.knowledge.pipeline import CorpusSnapshot, SourceChunk
from app.knowledge.production_executor import ProductionKnowledgeExecutor
from app.knowledge.provider_extractor import OpenAIKnowledgeExtractor
from app.models import Base, UsageEvent
from app.providers.base import GeneratedText
from app.query.production_chat import _record_planner_usage
from app.query.understanding.planner import PlannerAttempt


def _session_factory():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def _generated(text="{}", tokens=(1000, 500)):
    return GeneratedText(
        text=text,
        input_tokens=tokens[0],
        output_tokens=tokens[1],
        total_tokens=sum(tokens),
        request_id="provider-request",
    )


def test_every_billed_planner_attempt_is_recorded_with_its_cost():
    session = _session_factory()()
    attempts = (
        PlannerAttempt("simple", "openai", "gpt-5.6-luna", False, None, _generated()),
        PlannerAttempt("simple", "openai", "gpt-5.6-luna", True, "resolved", _generated()),
        PlannerAttempt("simple", "deterministic", "governed", False, "resolved", None),
    )

    _record_planner_usage(session, "workspace", "run", attempts)
    _record_planner_usage(session, "workspace", "run", attempts)  # idempotent retry

    events = session.scalars(select(UsageEvent)).all()
    assert [event.stage for event in events] == ["semantic_planner", "semantic_planner"]
    assert {event.query_run_id for event in events} == {"run"}
    # 1000 input at $2/M + 500 output at $8/M = $0.006 per call.
    assert sum(Decimal(event.cost_amount) for event in events) == Decimal("0.012")


class _ExtractionProvider:
    async def generate(self, model, instructions, input_text):
        return _generated(
            '{"mentions":[{"id":"person","entity_type":"person","chunk_id":"chunk-a",'
            '"start_offset":0,"end_offset":4,"source_text":"Ayse","confidence":0.9}]}'
        )


def test_knowledge_extraction_usage_is_recorded_after_each_batch():
    factory = _session_factory()
    extractor = OpenAIKnowledgeExtractor("gpt-5.6-luna", _ExtractionProvider())
    snapshot = CorpusSnapshot(
        "workspace",
        "fingerprint",
        (SourceChunk("chunk-a", "doc-a", "version-a", "logical-a", 0, "Ayse", "hash-a"),),
    )
    extractor.extract(snapshot, "generation")
    executor = SimpleNamespace(
        extractor=extractor, session_factory=factory, workspace_id="workspace"
    )

    ProductionKnowledgeExecutor._record_extraction_usage(executor, "generation")

    session = factory()
    events = session.scalars(select(UsageEvent)).all()
    assert [(event.stage, event.provider, event.input_tokens) for event in events] == [
        ("knowledge_extraction", "openai", 1000)
    ]
    assert extractor.drain_provider_calls() == ()


def test_budget_status_warns_without_blocking_and_counts_unpriced_calls():
    session = _session_factory()()
    persist_usage(
        session,
        workspace_id="workspace",
        stage="semantic_planner",
        provider="openai",
        model="gpt-5.6-luna",
        usage=usage_from_generated(_generated(tokens=(1_000_000, 0))),
        idempotency_key="priced",
    )
    persist_usage(
        session,
        workspace_id="workspace",
        stage="semantic_planner",
        provider="openai",
        model="unknown-model",
        usage=usage_from_generated(_generated()),
        idempotency_key="unpriced",
    )

    status = budget_status(
        session,
        daily_budget_usd=2.5,
        monthly_budget_usd=0,
        warning_percent=80,
        now=datetime.now(UTC),
    )

    assert status["enforcement"] == "warn_only"
    assert status["daily"]["state"] == "warning"
    assert status["daily"]["percent"] == 80.0
    assert status["daily"]["unpriced_calls"] == 1
    assert status["monthly"]["state"] == "unbounded"
