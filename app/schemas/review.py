from pydantic import BaseModel, ConfigDict
from datetime import datetime
from typing import Optional


class ReviewBase(BaseModel):
    product: str
    text: str
    date: datetime
    sentiment: Optional[str] = None
    cluster: Optional[str] = None
    sentiment_score: Optional[float] = None
    sentiment_summary: Optional[str] = None
    insights: Optional[dict] = None


class ReviewCreate(BaseModel):
    product: str
    text: str
    date: Optional[datetime] = None


class ReviewOut(ReviewBase):
    id: int

    model_config = ConfigDict(from_attributes=True)
