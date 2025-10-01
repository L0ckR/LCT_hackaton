import json
import logging
import re
import textwrap
from typing import Iterable, List
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup
from openai import APIConnectionError, APIStatusError, APITimeoutError, RateLimitError
from pydantic import ValidationError

from app.core.config import settings
from app.schemas.parser import PagePayload, ParsedReview
from app.services.openai_client import create_chat_completion

logger = logging.getLogger(__name__)

_ALLOWED_SOURCES = [
    "sravni.ru",
    "banki.ru",
    "banki.ros",
    "vbr.ru",
    "finsber",
    "vsezaimyonline.ru",
    "irecommend.ru",
    "2gis",
    "google maps",
    "yandex maps",
    "yandex zen",
    "apps.apple.com",
    "play.google.com",
    "vk.com",
    "telegram"
]

_SYSTEM_PROMPT = (
    "Ты эксперт по анализу отзывов о банковских продуктах. "
    "Тебе нужно аккуратно извлекать структурированные данные из неструктурированного текста. "
    "Отвечай строго в формате валидного JSON без пояснений и комментариев."
)

_RESPONSE_STRUCTURE_HINT = (
    '{"reviews": [ { "url": "...", "review_tag": "...", "date_review": "...", '
    '"user_name": "...", "user_city": "...", "review_title": "...", "review_text": "...", '
    '"review_status": "...", "rating": "...", "bank_name": "...", "source": "..." } ]}'
)

_MAX_TEXT_LENGTH = 15000


class ParserError(Exception):
    """Raised when the review parser fails to extract data."""


def _clean_html(content: str) -> str:
    logger.info(content)
    soup = BeautifulSoup(content, "html.parser")
    for tag in soup([
        "script",
        "style",
        "head",
        "footer",
        "nav",
        "iframe",
        "noscript",
    ]):
        tag.decompose()

    for tag in soup.find_all(True):
        if tag.name != "img":
            tag.attrs = {}
        else:
            tag.attrs = {k: v for k, v in tag.attrs.items() if k == "alt"}

    text = soup.get_text(separator=" ", strip=True)
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"https?://\S+", "", text)
    if len(text) > _MAX_TEXT_LENGTH:
        return text[:_MAX_TEXT_LENGTH]
    return text


async def _fetch_content(url: str) -> str:
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(url, follow_redirects=True)
        response.raise_for_status()
        return response.text


def _extract_json_block(payload: str) -> dict:
    if not payload:
        raise ParserError("Empty LLM response")
    content = payload.strip()
    if content.startswith("```"):
        content = re.sub(r"^```[a-zA-Z0-9]*", "", content)
        content = re.sub(r"```$", "", content).strip()

    try:
        return json.loads(content)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", content, re.S)
        if not match:
            raise ParserError("LLM response does not contain JSON")
        return json.loads(match.group(0))


def _default_source(url: str) -> str | None:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    host = host.lstrip("www.")
    return host or None


def _sources_hint() -> str:
    return "\n".join(f"- {source}" for source in _ALLOWED_SOURCES)


async def _run_llm(url: str, text: str) -> dict:
    if not settings.FOUNDATION_API_KEY:
        raise ParserError("FOUNDATION_API_KEY is not configured")

    trimmed_text = text[:_MAX_TEXT_LENGTH]
    prompt_template = textwrap.dedent(
        '''
        Тебе передан очищенный текст страницы с отзывами. URL страницы: {url}.
        Источник относится к одному из следующих агрегаторов и платформ:
        {sources}
        Проанализируй текст и извлеки как можно больше отдельных отзывов.
        Для каждого отзыва собери поля: url, review_tag, date_review, user_name, user_city,
        review_title, review_text, review_status, rating, bank_name, source.
        Если каких-то данных нет в тексте, ставь null.
        Отвечай строго JSON объектом следующей структуры: {structure}.
        url каждого отзыва по умолчанию равен адресу страницы, если не указано иное.
        Не придумывай данных, которых нет в тексте. Максимум 20 отзывов.
        Текст страницы:
        """{text}"""
        '''
    ).strip()
    user_prompt = prompt_template.format(
        url=url,
        sources=_sources_hint(),
        structure=_RESPONSE_STRUCTURE_HINT,
        text=trimmed_text,
    )

    try:
        completion = await create_chat_completion(
            model=settings.FOUNDATION_CHAT_MODEL,
            temperature=0.1,
            top_p=0.9,
            max_tokens=2000,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        )
    except (APIConnectionError, APITimeoutError, APIStatusError, RateLimitError) as exc:
        logger.warning("LLM request failed: %s", exc)
        raise ParserError("LLM request failed") from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected error during LLM call")
        raise ParserError("Unexpected LLM error") from exc

    message = completion.choices[0].message.content if completion.choices else ""
    data = _extract_json_block(message or "")
    if not isinstance(data, dict):
        raise ParserError("LLM returned non-object payload")
    return data


def _coerce_reviews(raw: dict, page: PagePayload) -> List[ParsedReview]:
    items = raw.get("reviews") if isinstance(raw, dict) else None
    if not isinstance(items, Iterable):
        return []

    reviews: List[ParsedReview] = []
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            logger.debug("Skipping non-dict review item at position %s", index)
            continue
        payload = dict(item)
        payload.setdefault("url", str(page.url))
        payload.setdefault("source", _default_source(str(page.url)))
        try:
            review = ParsedReview.model_validate(payload)
        except ValidationError as exc:
            logger.debug("Validation failed for review #%s on %s: %s", index, page.url, exc)
            continue
        reviews.append(review)
    return reviews


async def extract_reviews(pages: Iterable[PagePayload]) -> List[ParsedReview]:
    collected: List[ParsedReview] = []
    for page in pages:
        try:
            html = page.content or await _fetch_content(str(page.url))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to load page %s: %s", page.url, exc)
            continue

        cleaned = _clean_html(html)
        if not cleaned:
            logger.debug("Empty cleaned content for %s", page.url)
            continue

        try:
            llm_payload = await _run_llm(str(page.url), cleaned)
        except ParserError as exc:
            logger.warning("LLM parsing failed for %s: %s", page.url, exc)
            continue

        reviews = _coerce_reviews(llm_payload, page)
        if not reviews:
            logger.debug("No reviews extracted for %s", page.url)
            continue
        collected.extend(reviews)

    return collected
