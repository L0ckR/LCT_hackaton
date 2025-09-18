import logging
import time
from urllib.parse import urlparse

from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

from app.core.config import settings

logger = logging.getLogger(__name__)

engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def wait_for_db(max_attempts: int = 10, delay_seconds: float = 2.0) -> None:
    """Block until the database is reachable or raise after exhausting retries."""

    url = urlparse(settings.DATABASE_URL)
    if url.scheme.startswith("sqlite"):
        return

    for attempt in range(1, max_attempts + 1):
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            if attempt > 1:
                logger.info("Database became reachable on attempt %s", attempt)
            return
        except OperationalError as exc:  # pragma: no cover - best effort guard
            logger.warning(
                "Database not ready (attempt %s/%s): %s", attempt, max_attempts, exc
            )
            if attempt == max_attempts:
                raise
            time.sleep(delay_seconds)
