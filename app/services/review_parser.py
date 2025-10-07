import asyncio
import csv
import json
import logging
import random
import re
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from html import unescape
from typing import Any, Dict, Iterable, List, Optional, Sequence

import requests

try:
    from bs4 import BeautifulSoup  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    BeautifulSoup = None  # type: ignore

try:
    from fake_useragent import UserAgent
except ImportError:  # pragma: no cover - dependency provided at runtime
    UserAgent = None  # type: ignore

logger = logging.getLogger(__name__)

GAZPROMBANK_ID = "5bb4f768245bc22a520a6115"
GAZPROMBANK_SLUG = "gazprombank"
GAZPROMBANK_NAME = "Газпромбанк"
BANKI_RU_SLUG = "gazprombank"
BANKI_RU_NAME = "Газпромбанк"


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
        self._max_retries = 6
        self._max_retries = 6

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
            if page_rows:
                sample = page_rows[0]
                logger.info(
                    "sravni page %s parsed review id=%s title=%s",
                    page,
                    sample.get("review_id"),
                    (sample.get("review_title") or "")[:80],
                )
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


class BankiRuParser:
    """Parser for banki.ru reviews."""

    _BASE_URL_TEMPLATE = "https://www.banki.ru/services/responses/bank/{slug}/"
    _REVIEW_URL_TEMPLATE = (
        "https://www.banki.ru/services/responses/bank/{slug}/?id={review_id}"
    )
    _DEFAULT_MAX_RETRIES = 6

    def __init__(self, data_dir: Optional[Path] = None) -> None:
        root_dir = Path(__file__).resolve().parents[2]
        self.data_dir = data_dir or (root_dir / "data")
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._csv_writer = _CsvWriter(self.data_dir)
        self._user_agent_provider = _UserAgentProvider()
        self._session = requests.Session()
        self._max_retries = self._DEFAULT_MAX_RETRIES

    def parse_reviews(
        self,
        page_size: int = 20,
        max_pages: int = 200,
        start_date: Optional[datetime] = None,
        bank_slug: Optional[str] = None,
        bank_name: Optional[str] = None,
        output_filename: Optional[str] = None,
        finger_print: Optional[str] = None,  # noqa: ARG002 - совместимость схемы
        delay_range: tuple[float, float] = (1.0, 2.0),
    ) -> ParseResult:
        if page_size <= 0:
            raise ParserServiceError("Page size must be positive")
        if max_pages <= 0:
            raise ParserServiceError("Max pages must be positive")
        if delay_range[0] > delay_range[1]:
            raise ParserServiceError("Invalid delay range configuration")
        if finger_print:
            logger.debug("finger_print parameter is ignored for banki.ru parser")

        slug = bank_slug or BANKI_RU_SLUG
        bank_name = bank_name or BANKI_RU_NAME

        logger.info("Starting banki.ru reviews parsing for %s", bank_name)
        delay_min, delay_max = delay_range
        threshold = start_date.replace(tzinfo=None) if start_date else None
        parsed_rows: List[Dict[str, Any]] = []
        skipped_pages: List[int] = []

        for page in range(1, max_pages + 1):
            page_url = self._build_page_url(slug, page, page_size)
            logger.debug("Fetching banki.ru reviews page %s url=%s", page, page_url)
            try:
                response = self._fetch_banki_page(page_url, slug, page)
            except ParserServiceError as exc:
                logger.error(
                    "Skipping banki.ru page %s after repeated failures: %s",
                    page,
                    exc,
                )
                skipped_pages.append(page)
                if delay_max > 0:
                    time.sleep(random.uniform(delay_min, delay_max))
                continue

            items, has_more, ld_reviews, statuses = self._extract_page_payload(response.text)
            if not items:
                logger.info("No review items returned on banki.ru page %s, stopping", page)
                break
            if ld_reviews and len(ld_reviews) != len(items):
                logger.debug(
                    "banki.ru JSON-LD reviews count (%s) differs from item count (%s) on page %s",
                    len(ld_reviews),
                    len(items),
                    page,
                )

            should_stop = False
            page_rows: List[Dict[str, Any]] = []
            for index, item in enumerate(items):
                meta = ld_reviews[index] if index < len(ld_reviews) else {}
                status_text = statuses[index] if index < len(statuses) else ""
                row, stop_row = self._build_row(
                    item=item,
                    meta=meta,
                    slug=slug,
                    bank_name=bank_name,
                    threshold=threshold,
                    status_text=status_text,
                )
                if row:
                    page_rows.append(row)
                if stop_row:
                    should_stop = True
                    break

            parsed_rows.extend(page_rows)
            if should_stop:
                logger.info("Reached start date threshold on banki.ru page %s", page)
                break
            if page_rows:
                sample = page_rows[0]
                logger.info(
                    "banki.ru page %s parsed review id=%s title=%s",
                    page,
                    sample.get("review_id"),
                    (sample.get("review_title") or "")[:80],
                )
            if not has_more:
                logger.info("Last banki.ru page reached for banki.ru parser")
                break
            if delay_max > 0:
                time.sleep(random.uniform(delay_min, delay_max))

        if not parsed_rows:
            raise ParserServiceError("No reviews parsed for banki.ru")

        filename = self._ensure_csv_filename(output_filename or f"banki_ru_reviews_{slug}.csv")
        headers = (
            "url",
            "review_date",
            "user_name",
            "user_city",
            "user_city_full",
            "review_title",
            "review_text",
            "review_status",
            "rating",
            "review_tag",
            "bank_name",
            "is_bank_ans",
            "review_id",
        )
        unique_rows = self._deduplicate_rows(parsed_rows)
        path = self._csv_writer.write(filename, headers, unique_rows)
        logger.info(
            "Finished banki.ru reviews parsing for %s. Total reviews: %s",
            bank_name,
            len(unique_rows),
        )
        return ParseResult(
            source="banki_ru",
            filename=filename,
            csv_path=path,
            rows_written=len(unique_rows),
            metadata={
                "bank_slug": slug,
                "bank_name": bank_name,
                "start_date": start_date.isoformat() if start_date else None,
                "max_pages": max_pages,
                "page_size": page_size,
                "skipped_pages": skipped_pages,
            },
            rows=unique_rows,
        )

    def _build_page_url(self, slug: str, page: int, page_size: int) -> str:
        base = self._base_url(slug)
        if page <= 1:
            return f"{base}?type=all&period=all&perPage={page_size}"
        return f"{base}?page={page}&type=all&period=all&perPage={page_size}"

    def _base_url(self, slug: str) -> str:
        return self._BASE_URL_TEMPLATE.format(slug=slug)

    def _build_headers(self, referer: Optional[str] = None) -> Dict[str, str]:
        headers = {
            "User-Agent": self._user_agent_provider.get(),
            "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
        }
        if referer:
            headers["Referer"] = referer
        return headers

    def _fetch_banki_page(self, url: str, slug: str, page: int) -> requests.Response:
        referer = f"{self._base_url(slug)}?type=all&period=all"
        max_retries = getattr(self, "_max_retries", self._DEFAULT_MAX_RETRIES)
        if not hasattr(self, "_max_retries"):
            self._max_retries = max_retries
        for attempt in range(1, max_retries + 1):
            try:
                response = self._session.get(
                    url,
                    headers=self._build_headers(referer=referer),
                    timeout=30,
                )
            except requests.RequestException as exc:
                logger.warning(
                    "banki.ru request error on page %s (attempt %s/%s): %s",
                    page,
                    attempt,
                    max_retries,
                    exc,
                )
                time.sleep(5)
                continue

            if response.status_code == 429:
                logger.warning(
                    "Received HTTP 429 on banki.ru page %s (attempt %s/%s), backing off for 60s",
                    page,
                    attempt,
                    max_retries,
                )
                time.sleep(60)
                continue
            if response.status_code == 403:
                wait_seconds = min(180, 30 * attempt)
                logger.error(
                    "Received HTTP 403 on banki.ru page %s (attempt %s/%s). Retrying after %ss",
                    page,
                    attempt,
                    max_retries,
                    wait_seconds,
                )
                time.sleep(wait_seconds)
                self._reset_session()
                continue
            if 500 <= response.status_code < 600:
                wait_seconds = min(90, 10 * attempt)
                logger.error(
                    "Received HTTP %s on banki.ru page %s (attempt %s/%s). Retrying after %ss",
                    response.status_code,
                    page,
                    attempt,
                    max_retries,
                    wait_seconds,
                )
                time.sleep(wait_seconds)
                self._reset_session()
                continue
            if response.status_code != 200:
                message = (
                    f"Unexpected response {response.status_code} on banki.ru page {page}"
                )
                logger.error(message)
                raise ParserServiceError(message)
            return response

        message = f"Failed to fetch banki.ru page {page} after multiple attempts"
        logger.error(message)
        raise ParserServiceError(message)

    def _reset_session(self) -> None:
        try:
            self._session.close()
        except Exception:  # pragma: no cover - defensive
            pass
        self._session = requests.Session()

    def _deduplicate_rows(self, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        seen_keys: set[tuple[Any, ...]] = set()
        unique_rows: List[Dict[str, Any]] = []
        for row in rows:
            review_id = row.get("review_id")
            if review_id:
                key = ("id", review_id)
            else:
                key = ("content", row.get("review_date"), row.get("review_text"))
            if key in seen_keys:
                continue
            seen_keys.add(key)
            unique_rows.append(row)
        removed = len(rows) - len(unique_rows)
        if removed:
            logger.info("Removed %s duplicate reviews while merging results", removed)
        return unique_rows

    def _extract_page_payload(
        self,
        html_content: str,
    ) -> tuple[List[Dict[str, Any]], bool, List[Dict[str, Any]], List[str]]:
        options: Optional[Dict[str, Any]] = None
        for match in re.finditer(
            r'data-module-options=(?P<q>"|\')(?P<content>.*?)(?P=q)',
            html_content,
            re.DOTALL,
        ):
            raw_options = match.group("content")
            try:
                candidate = json.loads(unescape(raw_options))
            except json.JSONDecodeError:
                continue
            if "responses" in candidate:
                options = candidate
                break
        else:
            raise ParserServiceError(
                "Banki.ru markup changed: responses payload not found"
            )
        assert options is not None  # for type checkers
        responses = options.get("responses") or {}
        items = responses.get("data") or []
        has_more = bool(responses.get("hasMorePages"))
        ld_reviews = self._extract_jsonld_reviews(html_content)
        statuses = self._extract_status_badges(html_content, items)
        return items, has_more, ld_reviews, statuses

    def _extract_jsonld_reviews(self, html_content: str) -> List[Dict[str, Any]]:
        reviews: List[Dict[str, Any]] = []
        for match in re.finditer(
            r'<script type="application/ld\+json">(.*?)</script>',
            html_content,
            re.DOTALL,
        ):
            try:
                payload = json.loads(match.group(1))
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict) and isinstance(payload.get("review"), list):
                for entry in payload["review"]:
                    if isinstance(entry, dict) and entry.get("@type") == "Review":
                        reviews.append(entry)
                break
        return reviews

    def _extract_status_badges(
        self, html_content: str, items: Sequence[Dict[str, Any]]
    ) -> List[str]:
        if BeautifulSoup is None or not items:
            return ["" for _ in items]
        soup = BeautifulSoup(html_content, "html.parser")
        result: List[str] = []
        for item in items:
            status_text = ""
            review_id = item.get("id")
            if review_id:
                pattern = re.compile(rf"/services/responses/bank/.+\?id={review_id}(?:&|$)")
                link = soup.find("a", href=pattern)
                container = None
                if link:
                    container = link
                    for _ in range(5):  # climb up a few levels to reach card root
                        container = container.parent
                        if container is None:
                            break
                        if container and container.name and container.name.lower() in {"article", "div", "section"}:
                            # look for badge inside this container
                            badge = container.find(
                                string=re.compile(r"^Отзыв", re.IGNORECASE)
                            )
                            if badge:
                                status_text = badge.strip()
                                break
                    # if not found, attempt secondary search within container divs
                    if not status_text and container:
                        for div in container.find_all("div"):
                            text = (div.get_text() or "").strip()
                            if text.startswith("Отзыв"):
                                status_text = text
                                break
            result.append(status_text)
        return result

    def _build_row(
        self,
        *,
        item: Dict[str, Any],
        meta: Dict[str, Any],
        slug: str,
        bank_name: str,
        threshold: Optional[datetime],
        status_text: str,
    ) -> tuple[Optional[Dict[str, Any]], bool]:
        review_id = item.get("id")
        date_raw = item.get("dateCreate") or ""
        review_date_dt = self._parse_datetime(date_raw)
        if threshold and review_date_dt and review_date_dt < threshold:
            return None, True

        review_url = (
            self._REVIEW_URL_TEMPLATE.format(slug=slug, review_id=review_id)
            if review_id
            else ""
        )
        review_date_value = (
            review_date_dt.isoformat() if review_date_dt else (date_raw or "")
        )
        description = meta.get("description") or item.get("text") or ""
        review_text = self._normalize_text(description)
        title = item.get("title") or meta.get("name") or ""
        rating = item.get("grade") or meta.get("reviewRating", {}).get("ratingValue", "")
        status_text = self._infer_status_from_item(status_text, item)

        row = {
            "url": review_url,
            "review_date": review_date_value,
            "user_name": meta.get("author", ""),
            "user_city": "",
            "user_city_full": "",
            "review_title": title,
            "review_text": review_text,
            "review_status": status_text,
            "rating": rating,
            "review_tag": "",
            "bank_name": bank_name or "",
            "is_bank_ans": bool(item.get("agentAnswerText")),
            "review_id": review_id or "",
        }
        return row, False

    def _infer_status_from_item(self, status_text: str, item: Dict[str, Any]) -> str:
        if status_text:
            return status_text
        is_countable = item.get("isCountable")
        if is_countable is True:
            return "Отзыв проверен"
        if is_countable is False:
            return "Отзыв не зачтен"
        return "Отзыв проверяется"

    def _normalize_text(self, value: str) -> str:
        if not value:
            return ""
        normalized = re.sub(r"(?i)</p>", "\n", value)
        normalized = re.sub(r"(?i)<br\s*/?>", "\n", normalized)
        normalized = re.sub(r"<[^>]+>", " ", normalized)
        normalized = unescape(normalized)
        return re.sub(r"\s+", " ", normalized).strip()

    def _parse_datetime(self, value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        try:
            return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            logger.debug("Failed to parse banki.ru datetime value: %s", value)
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
        self._banki_parser = BankiRuParser(self._sravni_parser.data_dir)

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

    async def parse_banki_ru_reviews(
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
            self._banki_parser.parse_reviews,
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
