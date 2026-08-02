import dramatiq
from dramatiq.brokers.redis import RedisBroker

from ..core.config import get_settings

broker = RedisBroker(url=get_settings().redis_url)
dramatiq.set_broker(broker)


@dramatiq.actor(max_retries=3)
def recover_stale_jobs() -> None:
    """Phase 3 hook; durable workflow recovery is implemented in Phase 7."""
