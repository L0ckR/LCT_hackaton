from textblob import TextBlob
from sqlalchemy.orm import Session

from app.celery_app import celery_app
from app.db.session import SessionLocal
from app.models.review import Review


@celery_app.task
def analyze_sentiment_task(review_id: int):
    db: Session = SessionLocal()
    try:
        review = db.query(Review).get(review_id)
        if review:
            blob = TextBlob(review.text)
            polarity = blob.sentiment.polarity
            if polarity > 0.1:
                review.sentiment = "positive"
            elif polarity < -0.1:
                review.sentiment = "negative"
            else:
                review.sentiment = "neutral"
            db.add(review)
            db.commit()
    finally:
        db.close()
