"""Dialect-aware custom column types."""

from __future__ import annotations

import logging
from typing import Any, Iterable, Optional

from sqlalchemy.types import JSON, TypeDecorator


logger = logging.getLogger(__name__)


class VectorAsJSON(TypeDecorator):
    """Store embeddings as pgvector on PostgreSQL and JSON elsewhere."""

    impl = JSON
    cache_ok = True

    _import_error_logged = False
    _vector_enabled = False

    def __init__(self, dimensions: Optional[int] = None) -> None:
        super().__init__()
        self._dimensions = dimensions

    def load_dialect_impl(self, dialect):  # type: ignore[override]
        if dialect.name == "postgresql" and self._vector_enabled:
            try:
                from pgvector.sqlalchemy import Vector  # Imported lazily to avoid hard dependency.

                return dialect.type_descriptor(Vector(self._dimensions))
            except ModuleNotFoundError:  # pragma: no cover - optional dependency guard
                if not VectorAsJSON._import_error_logged:
                    logger.warning(
                        "pgvector package not installed; falling back to JSON column for embeddings"
                    )
                    VectorAsJSON._import_error_logged = True
        return dialect.type_descriptor(JSON())

    def process_bind_param(self, value: Optional[Iterable[float]], dialect):  # type: ignore[override]
        if value is None:
            return None
        return list(value)

    def process_result_value(self, value: Any, dialect):  # type: ignore[override]
        return value

    @classmethod
    def enable_vector(cls) -> None:
        if not cls._vector_enabled:
            logger.info("pgvector support enabled; storing embeddings using vector type")
        cls._vector_enabled = True

    @classmethod
    def disable_vector(cls) -> None:
        if cls._vector_enabled:
            logger.info("pgvector support disabled; falling back to JSON storage for embeddings")
        cls._vector_enabled = False

    @classmethod
    def is_vector_enabled(cls) -> bool:
        return cls._vector_enabled
