import logging
import time
from urllib.parse import urlparse

from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.db.types import VectorAsJSON

logger = logging.getLogger(__name__)

engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def _extension_available(connection, name: str) -> bool:
    query = text(
        "SELECT 1 FROM pg_available_extensions WHERE name = :name"
    )
    return bool(connection.execute(query, {"name": name}).scalar())


def _type_exists(connection, type_name: str) -> bool:
    query = text(
        "SELECT EXISTS (SELECT 1 FROM pg_type WHERE typname = :name)"
    )
    return bool(connection.execute(query, {"name": type_name}).scalar())


def ensure_extensions() -> None:
    """Create TimescaleDB and pgvector extensions when using PostgreSQL."""

    if engine.dialect.name != "postgresql":
        return

    # Use engine.begin() so extension creation happens in a committed transaction.
    with engine.begin() as connection:
        try:
            if _extension_available(connection, "timescaledb"):
                connection.execute(text("CREATE EXTENSION IF NOT EXISTS timescaledb"))
            else:
                logger.warning("TimescaleDB extension is not available on this server")

            vector_enabled = False
            vectorscale_available = _extension_available(connection, "vectorscale")
            vector_available = _extension_available(connection, "vector")

            if vectorscale_available:
                try:
                    connection.execute(
                        text("CREATE EXTENSION IF NOT EXISTS vectorscale CASCADE")
                    )
                    vector_enabled = _type_exists(connection, "vector")
                except SQLAlchemyError as exc:  # pragma: no cover - defensive
                    logger.warning("Failed to create vectorscale extension: %s", exc)
            elif vector_available:
                try:
                    connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
                    vector_enabled = _type_exists(connection, "vector")
                except SQLAlchemyError as exc:  # pragma: no cover - defensive
                    logger.warning("Failed to create pgvector extension: %s", exc)
            else:
                logger.warning(
                    "Neither vectorscale nor pgvector extensions are available on this server"
                )

            if vector_enabled:
                VectorAsJSON.enable_vector()
            else:
                VectorAsJSON.disable_vector()

            if settings.DATABASE_SEARCH_PATH:
                db_name = engine.url.database
                if db_name:
                    try:
                        connection.execute(
                            text(
                                f'ALTER DATABASE "{db_name}" SET search_path TO {settings.DATABASE_SEARCH_PATH}'
                            )
                        )
                    except SQLAlchemyError as exc:  # pragma: no cover - defensive
                        logger.warning(
                            "Failed to set search_path for database %s: %s",
                            db_name,
                            exc,
                            exc_info=True,
                        )
        except SQLAlchemyError as exc:  # pragma: no cover - defensive
            logger.warning("Failed to ensure database extensions: %s", exc, exc_info=True)
            VectorAsJSON.disable_vector()


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
