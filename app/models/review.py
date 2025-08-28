from sqlalchemy import Column, Integer, String, Text, DateTime
from datetime import datetime

from app.db.base import Base


class Review(Base):
    __tablename__ = "reviews"

    id = Column(Integer, primary_key=True, index=True)
    product = Column(String, index=True)
    text = Column(Text, nullable=False)
    date = Column(DateTime, default=datetime.utcnow)
    sentiment = Column(String, index=True)
    cluster = Column(String, index=True)
