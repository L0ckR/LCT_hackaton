"""Database helper functions reuseable across the application."""

from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session
from sqlalchemy.sql import ColumnElement

from app.core.config import settings


def day_bucket(db: Session, column) -> ColumnElement:
    """Return a day-level bucket expression aware of the active dialect."""

    bind = db.get_bind()
    if bind and bind.dialect.name == "postgresql":
        return func.time_bucket(settings.TIMESCALE_BUCKET_INTERVAL, column)
    if bind and bind.dialect.name == "sqlite":
        return func.date(column)
    return func.date_trunc("day", column)
