from datetime import datetime
from enum import Enum
from typing import Annotated, Any, Dict, Literal, Optional, Union

from pydantic import BaseModel, Field, model_validator


class ParserSource(str, Enum):
    GAZPROMBANK_SRAVNI = "gazprombank_reviews"
    BANKI_RU = "banki_ru"


class _BaseParserJob(BaseModel):
    start_date: Optional[datetime] = Field(
        default=None,
        description="Stop parsing when reviews older than this ISO timestamp are reached",
    )
    max_pages: int = Field(
        default=200,
        ge=1,
        le=1000,
        description="Maximum number of pages to iterate over",
    )
    page_size: int = Field(
        default=20,
        ge=1,
        le=200,
        description="Number of reviews the API should return per page",
    )
    min_delay: float = Field(
        default=1.0,
        ge=0.0,
        le=120.0,
        description="Minimum delay between requests to avoid throttling",
    )
    max_delay: float = Field(
        default=2.0,
        ge=0.0,
        le=180.0,
        description="Maximum delay between requests to avoid throttling",
    )
    finger_print: Optional[str] = Field(
        default=None,
        description="Optional fingerprint parameter for sravni proxy endpoint",
    )
    output_filename: Optional[str] = Field(
        default=None,
        description="Custom filename for results, defaults to sravni_reviews_{slug}.csv",
    )

    @model_validator(mode="after")
    def validate_delays(self) -> "_BaseParserJob":
        if self.max_delay < self.min_delay:
            raise ValueError("max_delay must be greater than or equal to min_delay")
        return self


class GazprombankReviewsJob(_BaseParserJob):
    source: Literal[ParserSource.GAZPROMBANK_SRAVNI] = ParserSource.GAZPROMBANK_SRAVNI


class BankiRuReviewsJob(_BaseParserJob):
    source: Literal[ParserSource.BANKI_RU] = ParserSource.BANKI_RU


ParseJobRequest = Annotated[
    Union[GazprombankReviewsJob, BankiRuReviewsJob],
    Field(discriminator="source"),
]


class ReviewRow(BaseModel):
    url: str
    review_date: str
    user_name: str
    user_city: str
    user_city_full: str
    review_title: str
    review_text: str
    review_status: str
    rating: Union[int, str]
    review_tag: str
    bank_name: str
    is_bank_ans: bool
    review_id: Union[int, str]


class ParseJobResult(BaseModel):
    source: ParserSource
    filename: str
    csv_path: str
    download_url: str
    rows_written: int
    metadata: Dict[str, Any] = Field(default_factory=dict)
    rows: list[ReviewRow] = Field(
        default_factory=list,
        description="Сырые строки с отзывами в том виде, как они сохранены в CSV.",
    )
