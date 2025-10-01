from typing import List, Optional

from pydantic import BaseModel, HttpUrl


class PagePayload(BaseModel):
    url: HttpUrl
    content: Optional[str] = None


class ParseRequest(BaseModel):
    pages: List[PagePayload]


class ParsedReview(BaseModel):
    url: HttpUrl
    review_tag: Optional[str] = None
    date_review: Optional[str] = None
    user_name: Optional[str] = None
    user_city: Optional[str] = None
    review_title: Optional[str] = None
    review_text: Optional[str] = None
    review_status: Optional[str] = None
    rating: Optional[str] = None
    bank_name: Optional[str] = None
    source: Optional[str] = None


class ParseResponse(BaseModel):
    reviews: List[ParsedReview]
