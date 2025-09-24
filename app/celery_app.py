from celery import Celery

from app.core.config import settings
from app.db.base import Base
from app.db.session import engine, ensure_extensions, wait_for_db

# Align worker startup with the web app so database extensions and metadata are ready.
wait_for_db()
ensure_extensions()
Base.metadata.create_all(bind=engine)

celery_app = Celery(__name__, broker=settings.REDIS_URL, backend=settings.REDIS_URL)
celery_app.autodiscover_tasks(["app.tasks"])
