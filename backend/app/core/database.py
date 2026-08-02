import time
from collections.abc import Callable
from typing import TypeVar

from sqlalchemy import create_engine, event
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from .config import get_settings

settings = get_settings()
T = TypeVar("T")
engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False, "timeout": settings.sqlite_busy_timeout_ms / 1000},
)


@event.listens_for(engine, "connect")
def configure_sqlite(connection, _):
    cursor = connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute(f"PRAGMA busy_timeout={settings.sqlite_busy_timeout_ms}")
    cursor.close()


SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def run_with_lock_retry(operation: Callable[[Session], T], attempts: int = 3) -> T:
    """Run a short database operation with bounded retries for SQLite lock contention."""
    for attempt in range(attempts):
        session = SessionLocal()
        try:
            result = operation(session)
            session.commit()
            return result
        except OperationalError as exc:
            session.rollback()
            if "locked" not in str(exc).lower() or attempt == attempts - 1:
                raise
            time.sleep(0.05 * (attempt + 1))
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
    raise RuntimeError("unreachable")
