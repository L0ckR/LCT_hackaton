from datetime import datetime
from typing import Iterable, List, Optional

from sqlalchemy.orm import Session

from app.models.review import Review
from app.services.pipeline import process_reviews
from app.realtime.pubsub import publish_event_sync


def _parse_date(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _build_review(record: dict, analysis: dict) -> Review:
    review = Review(
        product=record.get("product"),
        text=record.get("text", ""),
        date=_parse_date(record.get("date")) or datetime.utcnow(),
        sentiment=analysis.get("sentiment"),
        sentiment_score=analysis.get("sentiment_score"),
        sentiment_summary=analysis.get("summary"),
        embedding=analysis.get("embedding"),
    )
    highlights = analysis.get("highlights")
    if highlights:
        review.insights = {"highlights": list(highlights)[:5]}
    return review


async def import_reviews_async(
    db: Session, records: Iterable[dict], job_id: Optional[str] = None
) -> List[Review]:
    records = list(records)
    if not records:
        return []

    texts = [record.get("text", "") or "" for record in records]
    analyses = await process_reviews(texts)

    reviews: List[Review] = []
    total = len(records)
    for index, (record, analysis) in enumerate(zip(records, analyses), start=1):
        review = _build_review(record, analysis)
        db.add(review)
        reviews.append(review)
        if job_id:
            publish_event_sync(
                {
                    "type": "import_progress",
                    "job_id": job_id,
                    "processed": index,
                    "total": total,
                }
            )

    db.commit()
    for review in reviews:
        db.refresh(review)
    return reviews
