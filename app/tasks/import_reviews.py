import asyncio
from typing import List

from app.celery_app import celery_app
from app.db.session import SessionLocal
from app.realtime.pubsub import publish_event_sync
from app.services.reviews import import_reviews_async


async def _process(records: List[dict], job_id: str) -> int:
    if not records:
        return 0

    db = SessionLocal()
    try:
        publish_event_sync(
            {
                "type": "import_progress",
                "job_id": job_id,
                "processed": 0,
                "total": len(records),
            }
        )
        await import_reviews_async(db, records, job_id=job_id)
    finally:
        db.close()
    publish_event_sync({"type": "reviews_updated"})
    publish_event_sync(
        {"type": "import_completed", "job_id": job_id, "count": len(records)}
    )
    return len(records)


@celery_app.task
def import_reviews_task(records: List[dict]):
    job_id = import_reviews_task.request.id or ""
    return asyncio.run(_process(records, job_id))
