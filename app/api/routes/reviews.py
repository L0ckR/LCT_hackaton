import csv
import io
import json
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, get_db
from app.models.review import Review
from app.schemas.review import ReviewOut
from app.tasks.sentiment import analyze_sentiment_task
from app.services.clustering import fake_cluster

router = APIRouter(prefix="/reviews", tags=["reviews"])


@router.post("/upload", response_model=List[ReviewOut])
async def upload_reviews(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    contents = await file.read()
    reviews = []
    if file.filename.endswith(".json"):
        data = json.loads(contents)
        for item in data:
            review = Review(
                product=item.get("product"),
                text=item.get("text"),
                date=datetime.fromisoformat(item.get("date")) if item.get("date") else datetime.utcnow(),
            )
            db.add(review)
            db.commit()
            db.refresh(review)
            try:
                analyze_sentiment_task.delay(review.id)
            except Exception:
                pass
            reviews.append(review)
    elif file.filename.endswith(".csv"):
        reader = csv.DictReader(io.StringIO(contents.decode()))
        for item in reader:
            review = Review(
                product=item.get("product"),
                text=item.get("text"),
                date=datetime.fromisoformat(item.get("date")) if item.get("date") else datetime.utcnow(),
            )
            db.add(review)
            db.commit()
            db.refresh(review)
            try:
                analyze_sentiment_task.delay(review.id)
            except Exception:
                pass
            reviews.append(review)
    else:
        raise HTTPException(status_code=400, detail="Unsupported file type")
    return reviews


@router.get("/", response_model=List[ReviewOut])
def list_reviews(
    product: Optional[str] = None,
    sentiment: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    query = db.query(Review)
    if product:
        query = query.filter(Review.product == product)
    if sentiment:
        query = query.filter(Review.sentiment == sentiment)
    if start_date:
        query = query.filter(Review.date >= start_date)
    if end_date:
        query = query.filter(Review.date <= end_date)
    return query.all()


@router.get("/stats")
def stats(
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    query = db.query(
        Review.product, Review.sentiment, func.count(Review.id)
    ).group_by(Review.product, Review.sentiment)
    if start_date:
        query = query.filter(Review.date >= start_date)
    if end_date:
        query = query.filter(Review.date <= end_date)
    results = query.all()
    return [
        {"product": prod, "sentiment": sent, "count": cnt}
        for prod, sent, cnt in results
    ]


@router.get("/timeseries")
def timeseries(
    product: Optional[str] = None,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    query = db.query(
        func.date_trunc('day', Review.date).label('day'),
        Review.sentiment,
        func.count(Review.id),
    ).group_by('day', Review.sentiment).order_by('day')
    if product:
        query = query.filter(Review.product == product)
    results = query.all()
    return [
        {"date": day.isoformat(), "sentiment": sent, "count": cnt}
        for day, sent, cnt in results
    ]


@router.get("/clusters")
def clusters(db: Session = Depends(get_db), user=Depends(get_current_user)):
    return fake_cluster(db)
