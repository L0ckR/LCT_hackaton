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
from app.services.clustering import fake_cluster
from app.services.reviews import import_reviews_async
from app.realtime import broadcast_refresh

router = APIRouter(prefix="/reviews", tags=["reviews"])


@router.post("/upload", response_model=List[ReviewOut])
async def upload_reviews(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    contents = await file.read()
    records = []
    if file.filename.endswith(".json"):
        data = json.loads(contents)
        if isinstance(data, dict):
            data = [data]
        records = list(data)
    elif file.filename.endswith(".csv"):
        reader = csv.DictReader(io.StringIO(contents.decode()))
        records = list(reader)
    else:
        raise HTTPException(status_code=400, detail="Unsupported file type")

    reviews = await import_reviews_async(db, records)
    await broadcast_refresh()
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


@router.get("/recent", response_model=List[ReviewOut])
def recent_reviews(
    limit: int = 20,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    limit = max(1, min(limit, 100))
    return (
        db.query(Review)
        .order_by(Review.id.desc())
        .limit(limit)
        .all()
    )


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
    if db.bind and db.bind.dialect.name == "sqlite":
        day_expr = func.date(Review.date).label("day")
    else:
        day_expr = func.date_trunc('day', Review.date).label('day')

    query = db.query(
        day_expr,
        Review.sentiment,
        func.count(Review.id),
    ).group_by(day_expr, Review.sentiment).order_by(day_expr)
    if product:
        query = query.filter(Review.product == product)
    results = query.all()
    return [
        {
            "date": day if isinstance(day, str) else day.isoformat(),
            "sentiment": sent,
            "count": cnt,
        }
        for day, sent, cnt in results
    ]


@router.get("/clusters")
def clusters(db: Session = Depends(get_db), user=Depends(get_current_user)):
    return fake_cluster(db)
