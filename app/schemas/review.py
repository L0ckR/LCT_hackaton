from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class ReviewBase(BaseModel):
    product: str
    text: str
    date: datetime
    sentiment: Optional[str] = None
    cluster: Optional[str] = None


class ReviewCreate(BaseModel):
    product: str
    text: str
    date: Optional[datetime] = None


class ReviewOut(ReviewBase):
    id: int

    class Config:
        orm_mode = True
