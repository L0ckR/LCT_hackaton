from collections.abc import Iterable
from dataclasses import dataclass
from typing import Callable, Dict, List

from sqlalchemy import func, case
from sqlalchemy.orm import Session

from app.models.review import Review
from app.models.widget import Widget
from app.schemas.widget import MetricType


@dataclass(frozen=True)
class MetricDefinition:
    label: str
    calculator: Callable[[Session], float]


def _count_by_sentiment(db: Session, sentiment: str | None) -> int:
    query = db.query(func.count(Review.id))
    if sentiment is None:
        query = query.filter(Review.sentiment.is_(None))
    else:
        query = query.filter(Review.sentiment == sentiment)
    return query.scalar() or 0


def _average_sentiment(db: Session) -> float:
    result = db.query(func.avg(Review.sentiment_score)).scalar()
    return float(result or 0)


def _positive_share(db: Session) -> float:
    total = db.query(func.count(Review.id)).scalar() or 0
    if not total:
        return 0.0
    positive = _count_by_sentiment(db, "positive")
    return round(positive / total * 100, 2)


METRIC_MAP: Dict[MetricType, MetricDefinition] = {
    "total_reviews": MetricDefinition(
        label="Total Reviews", calculator=lambda db: db.query(func.count(Review.id)).scalar() or 0
    ),
    "positive_reviews": MetricDefinition(
        label="Positive Reviews", calculator=lambda db: _count_by_sentiment(db, "positive")
    ),
    "negative_reviews": MetricDefinition(
        label="Negative Reviews", calculator=lambda db: _count_by_sentiment(db, "negative")
    ),
    "neutral_reviews": MetricDefinition(
        label="Neutral Reviews", calculator=lambda db: _count_by_sentiment(db, "neutral")
    ),
    "unlabeled_reviews": MetricDefinition(
        label="Unlabeled Reviews", calculator=lambda db: _count_by_sentiment(db, None)
    ),
    "average_sentiment": MetricDefinition(
        label="Average Sentiment Score", calculator=_average_sentiment
    ),
    "positive_share": MetricDefinition(
        label="Positive Review Share (%)", calculator=_positive_share
    ),
}


def available_metrics() -> Iterable[tuple[str, MetricDefinition]]:
    return METRIC_MAP.items()


def compute_widget_value(widget: Widget, db: Session) -> float:
    metric = METRIC_MAP.get(widget.metric)
    if not metric:
        return 0.0
    return float(metric.calculator(db))


def _day_expression(db: Session):
    bind = db.get_bind()
    if bind and bind.dialect.name == "sqlite":
        return func.date(Review.date)
    return func.date_trunc("day", Review.date)


def timeseries_for_metric(db: Session, metric: MetricType) -> List[Dict[str, float]]:
    if metric not in METRIC_MAP:
        raise ValueError(f"Unsupported metric: {metric}")
    day_expr = _day_expression(db).label("day")

    if metric == "average_sentiment":
        query = (
            db.query(day_expr, func.avg(Review.sentiment_score).label("value"))
            .group_by(day_expr)
            .order_by(day_expr)
        )
    elif metric == "positive_share":
        positive_case = func.sum(
            case((Review.sentiment == "positive", 1), else_=0)
        )
        total_count = func.count(Review.id)
        query = (
            db.query(
                day_expr,
                (positive_case * 100.0 / func.nullif(total_count, 0)).label("value"),
            )
            .group_by(day_expr)
            .order_by(day_expr)
        )
    else:
        count_query = (
            db.query(day_expr, func.count(Review.id).label("value"))
            .group_by(day_expr)
            .order_by(day_expr)
        )
        if metric in {"positive_reviews", "negative_reviews", "neutral_reviews"}:
            sentiment_label = metric.split("_")[0]
            count_query = count_query.filter(Review.sentiment == sentiment_label)
        elif metric == "unlabeled_reviews":
            count_query = count_query.filter(Review.sentiment.is_(None))
        query = count_query

    results = []
    for day, value in query.all():
        iso = day if isinstance(day, str) else day.isoformat()
        results.append({"date": iso, "value": float(value or 0)})
    return results
