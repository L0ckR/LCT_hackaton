from sqlalchemy.orm import Session

from app.celery_app import celery_app
from app.db.session import SessionLocal
from app.models.review import Review
from app.services.ml import analyze_text


@celery_app.task
def analyze_sentiment_task(review_id: int):
    db: Session = SessionLocal()
    try:
        review = db.query(Review).get(review_id)
        if review is None:
            return
        result = analyze_text(review.text)
        review.sentiment = result.get("sentiment")
        review.sentiment_score = result.get("sentiment_score")
        review.sentiment_summary = result.get("summary")
        embedding = result.get("embedding")
        if embedding is not None:
            review.embedding = embedding
        highlights = result.get("highlights")
        if highlights:
            review.insights = {"highlights": highlights}
        db.add(review)
        db.commit()
    finally:
        db.close()
