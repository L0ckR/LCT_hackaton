import asyncio
import csv
import logging
import random
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import requests

try:
    from fake_useragent import UserAgent
except ImportError:  # pragma: no cover - dependency provided at runtime
    UserAgent = None  # type: ignore

logger = logging.getLogger(__name__)

GAZPROMBANK_ID = "5bb4f768245bc22a520a6115"
GAZPROMBANK_SLUG = "gazprombank"
GAZPROMBANK_NAME = "Газпромбанк"


class ParserServiceError(RuntimeError):
    """Raised when parsing fails in a recoverable way."""


@dataclass(slots=True)
class ParseResult:
    source: str
    filename: str
    csv_path: Path
    rows_written: int
    metadata: Dict[str, Any]
    rows: List[Dict[str, Any]]


class _UserAgentProvider:
    """Provides random user agents with a safe fallback list."""

    _FALLBACK_USER_AGENTS: tuple[str, ...] = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) "
        "Version/17.4 Safari/605.1.15",
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36",
    )

    def __init__(self) -> None:
        self._ua = None
        if UserAgent is not None:
            try:
                self._ua = UserAgent()
                logger.debug("Initialized fake-useragent provider")
            except Exception as exc:  # pragma: no cover - defensive path
                logger.warning("Failed to initialize fake-useragent: %s", exc)
                self._ua = None

    def get(self) -> str:
        if self._ua is not None:
            try:
                return str(self._ua.random)
            except Exception as exc:  # pragma: no cover - defensive path
                logger.debug("fake-useragent random lookup failed: %s", exc)
        return random.choice(self._FALLBACK_USER_AGENTS)


class _CsvWriter:
    """Helper to persist records to CSV with automatic directory creation."""

    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def write(self, filename: str, headers: Iterable[str], rows: Iterable[Dict[str, Any]]) -> Path:
        path = self.base_dir / filename
        with path.open("w", encoding="utf-8", newline="") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=list(headers))
            writer.writeheader()
            count = 0
            for row in rows:
                writer.writerow(row)
                count += 1
        logger.info("Wrote %s rows to %s", count, path)
        return path


class SravniParser:
    """Parser for sravni.ru ratings and reviews."""

    _REVIEWS_URL_TEMPLATE = (
        "https://www.sravni.ru/proxy-reviews/reviews?"
        "filterBy=all&"
        "fingerPrint={finger_print}&"
        "isClient=false&"
        "locationRoute=&"
        "newIds=true&"
        "orderBy=byDate&"
        "pageIndex={page}&"
        "pageSize={page_size}&"
        "reviewObjectId={bank_id}&"
        "reviewObjectType=banks&"
        "specificProductId=&"
        "tag=&"
        "withVotes=true"
    )
    _DEFAULT_FINGER_PRINT = "1d345dd221ef718448c6bef7fc795d47"

    def __init__(self, data_dir: Optional[Path] = None) -> None:
        root_dir = Path(__file__).resolve().parents[2]
        self.data_dir = data_dir or (root_dir / "data")
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._csv_writer = _CsvWriter(self.data_dir)
        self._user_agent_provider = _UserAgentProvider()
        self._session = requests.Session()

    def parse_gazprombank_reviews(
        self,
        page_size: int = 20,
        max_pages: int = 200,
        start_date: Optional[datetime] = None,
        bank_slug: Optional[str] = None,
        bank_name: Optional[str] = None,
        output_filename: Optional[str] = None,
        finger_print: Optional[str] = None,
        delay_range: tuple[float, float] = (1.0, 2.0),
    ) -> ParseResult:
        if page_size <= 0:
            raise ParserServiceError("Page size must be positive")
        if max_pages <= 0:
            raise ParserServiceError("Max pages must be positive")
        if delay_range[0] > delay_range[1]:
            raise ParserServiceError("Invalid delay range configuration")

        slug = bank_slug or GAZPROMBANK_SLUG
        bank_name = bank_name or GAZPROMBANK_NAME

        logger.info(
            "Starting sravni reviews parsing for %s (%s)", bank_name or slug, GAZPROMBANK_ID
        )
        delay_min, delay_max = delay_range
        parsed_rows: List[Dict[str, Any]] = []
        finger = finger_print or self._DEFAULT_FINGER_PRINT
        for page in range(max_pages):
            page_url = self._REVIEWS_URL_TEMPLATE.format(
                finger_print=finger,
                page=page,
                page_size=page_size,
                bank_id=GAZPROMBANK_ID,
            )
            logger.debug("Fetching sravni reviews page %s url=%s", page, page_url)
            response = self._session.get(
                page_url,
                headers=self._build_headers(referer=f"https://www.sravni.ru/bank/{slug}/otzyvy/"),
                timeout=30,
            )
            if response.status_code == 429:
                logger.warning("Received HTTP 429 on page %s, backing off for 60s", page)
                time.sleep(60)
                continue
            if response.status_code != 200:
                message = f"Unexpected response {response.status_code} on page {page}"
                logger.error(message)
                raise ParserServiceError(message)
            try:
                payload = response.json()
            except ValueError as exc:
                raise ParserServiceError(f"Failed to decode JSON on page {page}: {exc}") from exc
            items = payload.get("items") or []
            if not items:
                logger.info("No review items returned on page %s, stopping", page)
                break

            page_rows, should_stop = self._process_review_items(
                items=items,
                start_date=start_date,
                bank_name=bank_name,
                slug=slug,
            )
            parsed_rows.extend(page_rows)
            if should_stop:
                logger.info("Reached start date threshold, stopping at page %s", page)
                break
            if len(items) < page_size:
                logger.info("Last page reached based on returned item count")
                break
            if delay_max > 0:
                time.sleep(random.uniform(delay_min, delay_max))

        if not parsed_rows:
            raise ParserServiceError("No reviews parsed for the specified bank")

        filename = self._ensure_csv_filename(output_filename or f"sravni_reviews_{slug}.csv")
        headers = (
            "url",
            "review_date",
            "user_name",
            "user_city",
            "user_city_full",
            "review_title",
            "review_text",
            "review_status",
            "problem_status",
            "rating",
            "review_tag",
            "bank_name",
            "is_bank_ans",
            "review_id",
        )
        path = self._csv_writer.write(filename, headers, parsed_rows)
        logger.info(
            "Finished sravni reviews parsing for %s (%s). Total reviews: %s",
            bank_name or slug,
            GAZPROMBANK_ID,
            len(parsed_rows),
        )
        return ParseResult(
            source="gazprombank_reviews",
            filename=filename,
            csv_path=path,
            rows_written=len(parsed_rows),
            metadata={
                "bank_id": GAZPROMBANK_ID,
                "bank_slug": slug,
                "bank_name": bank_name,
                "start_date": start_date.isoformat() if start_date else None,
                "max_pages": max_pages,
                "page_size": page_size,
            },
            rows=parsed_rows,
        )

    def _build_headers(self, referer: Optional[str] = None) -> Dict[str, str]:
        headers = {
            "User-Agent": self._user_agent_provider.get(),
            "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
            "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
        }
        if referer:
            headers["Referer"] = referer
        return headers

    def _process_review_items(
        self,
        items: Iterable[Dict[str, Any]],
        start_date: Optional[datetime],
        bank_name: Optional[str],
        slug: str,
    ) -> tuple[List[Dict[str, Any]], bool]:
        rows: List[Dict[str, Any]] = []
        should_stop = False
        threshold = start_date
        for item in items:
            review_id = item.get("id")
            review_date_raw = item.get("date")
            review_date = self._parse_datetime(review_date_raw)
            if threshold and review_date and review_date < threshold:
                logger.debug(
                    "Reached review date %s that is older than threshold %s",
                    review_date,
                    threshold,
                )
                should_stop = True
                break
            url_review = (
                f"https://www.sravni.ru/bank/{slug}/otzyvy/{review_id}/"
                if review_id
                else ""
            )
            rows.append(
                {
                    "url": url_review,
                    "review_date": review_date_raw or "",
                    "user_name": item.get("authorName", ""),
                    "user_city": item.get("locationData", {}).get("name", "")
                    if item.get("locationData")
                    else "",
                    "user_city_full": item.get("locationData", {}).get("fullName", "")
                    if item.get("locationData")
                    else "",
                    "review_title": item.get("title", ""),
                    "review_text": item.get("text", ""),
                    "review_status": item.get("ratingStatus", ""),
                    "problem_status": item.get("problemSolved", ""),
                    "rating": item.get("rating", ""),
                    "review_tag": item.get("reviewTag", ""),
                    "bank_name": bank_name or "",
                    "is_bank_ans": item.get("hasCompanyResponse", False),
                    "review_id": review_id or "",
                }
            )
        return rows, should_stop

    def _parse_datetime(self, value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        normalized = value.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(normalized)
        except ValueError:
            logger.debug("Failed to parse datetime value: %s", value)
            return None

    def _ensure_csv_filename(self, filename: str) -> str:
        name = filename.strip()
        if not name:
            raise ParserServiceError("Output filename cannot be empty")
        candidate = Path(name).name
        if not candidate.lower().endswith(".csv"):
            candidate = f"{candidate}.csv"
        return candidate


class ParserService:
    """Async wrapper around Sravni parser for use in FastAPI routes."""

    def __init__(self) -> None:
        self._sravni_parser = SravniParser()

    @property
    def data_dir(self) -> Path:
        return self._sravni_parser.data_dir

    async def parse_gazprombank_reviews(
        self,
        *,
        page_size: int = 20,
        max_pages: int = 200,
        start_date: Optional[datetime] = None,
        bank_slug: Optional[str] = None,
        bank_name: Optional[str] = None,
        output_filename: Optional[str] = None,
        finger_print: Optional[str] = None,
        delay_range: tuple[float, float] = (1.0, 2.0),
    ) -> ParseResult:
        return await asyncio.to_thread(
            self._sravni_parser.parse_gazprombank_reviews,
            page_size,
            max_pages,
            start_date,
            bank_slug,
            bank_name,
            output_filename,
            finger_print,
            delay_range,
        )

    def resolve_csv_path(self, filename: str) -> Path:
        safe_name = Path(filename).name
        path = self.data_dir / safe_name
        if not path.exists():
            raise ParserServiceError(f"CSV file {safe_name} not found")
        if not path.is_file():
            raise ParserServiceError(f"{safe_name} is not a regular file")
        return path
