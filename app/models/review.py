from sqlalchemy import Column, Integer, String, Text, DateTime, Float, JSON
from datetime import datetime

from app.core.config import settings
from app.db.base import Base
from app.db.types import VectorAsJSON


class Review(Base):
    __tablename__ = "reviews"

    id = Column(Integer, primary_key=True, index=True)
    product = Column(String, index=True)
    text = Column(Text, nullable=False)
    date = Column(DateTime, default=datetime.utcnow)
    sentiment = Column(String, index=True)
    sentiment_score = Column(Float)
    sentiment_summary = Column(Text)
    embedding = Column(VectorAsJSON(settings.FOUNDATION_EMBEDDING_DIMENSION))
    insights = Column(JSON)
    cluster = Column(String, index=True)
