"""Celery task package initialization."""

# Importing the sentiment task at module import time makes sure Celery discovers it
# when autodiscover_tasks runs inside the worker container.
from .sentiment import analyze_sentiment_task  # noqa: F401
from .import_reviews import import_reviews_task  # noqa: F401

__all__ = ["analyze_sentiment_task", "import_reviews_task"]
