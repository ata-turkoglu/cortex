import dramatiq
from dramatiq.brokers.redis import RedisBroker

from ..core.config import get_settings
from ..core.database import run_with_lock_retry
from ..workflows.service import cleanup_retention, execute_run, recover_stale

broker = RedisBroker(url=get_settings().redis_url)
dramatiq.set_broker(broker)


@dramatiq.actor(max_retries=3)
def recover_stale_jobs() -> None:
    run_with_lock_retry(recover_stale)


@dramatiq.actor(max_retries=3)
def execute_workflow(run_id: str) -> None:
    """Execute short durable steps; Dramatiq retry is safe because checkpoints persist."""
    run_with_lock_retry(lambda session: execute_run(session, run_id))


@dramatiq.actor(max_retries=1)
def cleanup_workflow_retention() -> None:
    run_with_lock_retry(cleanup_retention)


@dramatiq.actor(max_retries=1)
def execute_query_synthesis(query_run_id: str) -> None:
    from ..chat.execution import synthesize_with_openai
    from ..core.database import SessionLocal

    synthesize_with_openai(query_run_id, SessionLocal)


@dramatiq.actor(max_retries=1)
def summarize_conversation(conversation_id: str) -> None:
    from ..chat.execution import summarize_conversation_with_openai
    from ..core.database import SessionLocal

    summarize_conversation_with_openai(conversation_id, SessionLocal)
