from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict

MetricType = Literal[
    "total_reviews",
    "positive_reviews",
    "negative_reviews",
    "neutral_reviews",
    "unlabeled_reviews",
    "average_sentiment",
    "positive_share",
]

VisualizationType = Literal["metric", "line", "bar"]


class WidgetBase(BaseModel):
    title: str
    metric: MetricType
    visualization: VisualizationType = "metric"


class WidgetCreate(WidgetBase):
    pass


class WidgetOut(WidgetBase):
    id: int
    value: Optional[float] = None

    model_config = ConfigDict(from_attributes=True)
