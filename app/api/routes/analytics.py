from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, case
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, get_db
from app.models.review import Review
from app.services.widgets import METRIC_MAP, timeseries_for_metric

router = APIRouter(prefix="/analytics", tags=["analytics"])


def _day_expression(db: Session):
    bind = db.get_bind()
    if bind and bind.dialect.name == "sqlite":
        return func.date(Review.date)
    return func.date_trunc("day", Review.date)


@router.get("/sentiment-trend")
def sentiment_trend(
    product: Optional[str] = None,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
) -> List[dict]:
    day_expr = _day_expression(db).label("day")
    positive_case = func.sum(case((Review.sentiment == "positive", 1), else_=0))
    negative_case = func.sum(case((Review.sentiment == "negative", 1), else_=0))
    neutral_case = func.sum(case((Review.sentiment == "neutral", 1), else_=0))

    query = (
        db.query(
            day_expr,
            func.avg(Review.sentiment_score).label("avg_score"),
            positive_case.label("positive"),
            negative_case.label("negative"),
            neutral_case.label("neutral"),
            func.count(Review.id).label("total"),
        )
        .group_by(day_expr)
        .order_by(day_expr)
    )
    if product:
        query = query.filter(Review.product == product)
    results = []
    for day, avg_score, pos, neg, neu, total in query.all():
        iso = day if isinstance(day, str) else day.isoformat()
        results.append(
            {
                "date": iso,
                "avg_score": float(avg_score or 0),
                "positive": int(pos or 0),
                "negative": int(neg or 0),
                "neutral": int(neu or 0),
                "total": int(total or 0),
            }
        )
    return results


@router.get("/metric-trend/{metric}")
def metric_trend(
    metric: str,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    if not metric:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Metric is required")
    try:
        data = timeseries_for_metric(db, metric) if metric else []
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {"metric": metric, "data": data}


@router.get("/overview")
def analytics_overview(
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    total_reviews = db.query(func.count(Review.id)).scalar() or 0
    avg_sentiment = db.query(func.avg(Review.sentiment_score)).scalar() or 0
    latest_reviews = (
        db.query(Review)
        .filter(Review.sentiment_summary.isnot(None))
        .order_by(Review.date.desc())
        .limit(5)
        .all()
    )
    highlights = []
    for review in latest_reviews:
        if review.insights and isinstance(review.insights, dict):
            for highlight in review.insights.get("highlights", [])[:2]:
                highlights.append(highlight)
    return {
        "total_reviews": int(total_reviews),
        "average_sentiment": float(avg_sentiment),
        "metrics": {key: definition.label for key, definition in METRIC_MAP.items()},
        "highlights": highlights,
    }
