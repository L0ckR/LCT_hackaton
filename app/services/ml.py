import asyncio
import json
import logging
import re
from typing import Any, Dict, Iterable, List, Literal, Optional

from openai import APIConnectionError, APIStatusError, APITimeoutError, RateLimitError
from pydantic import BaseModel, Field, ValidationError, field_validator
from textblob import TextBlob

from app.core.config import settings
from app.services.openai_client import create_chat_completion, create_embeddings

logger = logging.getLogger(__name__)


class SentimentPayload(BaseModel):
    sentiment: Literal["positive", "negative", "neutral"]
    sentiment_score: Optional[float] = None
    summary: Optional[str] = None
    highlights: List[str] = Field(default_factory=list)

    @field_validator("summary", mode="before")
    @classmethod
    def _stringify_summary(cls, value: Any) -> Optional[str]:
        if value is None or isinstance(value, str):
            return value
        try:
            return json.dumps(value, ensure_ascii=False)
        except (TypeError, ValueError):
            return str(value)


def _llm_available() -> bool:
    return bool(settings.FOUNDATION_API_KEY)


def _make_semaphore(limit: Optional[int]) -> asyncio.Semaphore:
    value = limit or 1
    if value < 1:
        value = 1
    return asyncio.Semaphore(value)


_embedding_semaphore = _make_semaphore(settings.FOUNDATION_EMBEDDING_CONCURRENCY)
_chat_semaphore = _make_semaphore(settings.FOUNDATION_CHAT_CONCURRENCY)


def _fallback_analysis(text: str) -> Dict[str, Any]:
    blob = TextBlob(text)
    polarity = blob.sentiment.polarity
    if polarity > 0.1:
        label = "positive"
    elif polarity < -0.1:
        label = "negative"
    else:
        label = "neutral"
    return {
        "sentiment": label,
        "sentiment_score": float(polarity),
        "summary": text[:280],
        "embedding": None,
        "highlights": [],
    }


def _parse_payload(content: str) -> SentimentPayload:
    if not content:
        raise ValueError("Empty response")
    stripped = content.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```[a-zA-Z0-9]*", "", stripped)
        stripped = re.sub(r"```$", "", stripped).strip()

    try:
        return SentimentPayload.model_validate_json(stripped)
    except (ValidationError, json.JSONDecodeError):
        match = re.search(r"\{.*\}", stripped, re.S)
        if not match:
            raise
        return SentimentPayload.model_validate_json(match.group(0))


async def generate_embeddings_async(texts: Iterable[str]) -> List[Optional[List[float]]]:
    sequences = list(texts)
    if not sequences:
        return []
    if not _llm_available():
        return [None] * len(sequences)

    batch_size = max(1, settings.FOUNDATION_EMBEDDING_BATCH_SIZE)
    results: List[Optional[List[float]]] = [None] * len(sequences)

    async def _run_chunk(chunk: List[tuple[int, str]]) -> None:
        try:
            async with _embedding_semaphore:
                response = await create_embeddings(
                    model=settings.FOUNDATION_EMBEDDING_MODEL,
                    input=[text for _, text in chunk],
                )
        except Exception:
            logger.exception(
                "Embedding request failed for batch of size %s", len(chunk)
            )
            return

        if not response.data:
            logger.warning("Empty embedding response for batch of size %s", len(chunk))
            return

        ordered = sorted(response.data, key=lambda item: item.index)
        for (position, _), item in zip(chunk, ordered):
            results[position] = item.embedding

    enumerated = list(enumerate(sequences))
    tasks = [
        _run_chunk(enumerated[i : i + batch_size])
        for i in range(0, len(enumerated), batch_size)
    ]
    await asyncio.gather(*tasks)
    return results


async def analyze_text_async(
    text: str, embedding: Optional[List[float]] = None
) -> Dict[str, Any]:
    if not _llm_available():
        return _fallback_analysis(text)

    local_embedding = embedding
    if local_embedding is None:
        vectors = await generate_embeddings_async([text])
        local_embedding = vectors[0] if vectors else None

    last_error: Optional[Exception] = None
    prompt = (
        "Ты аналитик, изучающий отзывы клиентов банка. "
        "Проанализируй текст отзыва ниже и ответь строго JSON без пояснений с ключами "
        "sentiment, sentiment_score, summary, highlights. "
        "sentiment — одно из значений: positive, negative, neutral. "
        "sentiment_score — число от -1 до 1. summary — краткое описание до 40 слов. "
        "highlights — список ключевых тезисов (короткие строки).\n\n"
        f"Отзыв: "
        f"""{text}"""
    )

    retries = max(1, settings.FOUNDATION_CHAT_RETRIES)
    for attempt in range(retries):
        try:
            async with _chat_semaphore:
                completion = await create_chat_completion(
                    model=settings.FOUNDATION_CHAT_MODEL,
                    max_tokens=500,
                    temperature=0.3,
                    top_p=0.9,
                    presence_penalty=0,
                    messages=[{"role": "user", "content": prompt}],
                )
            content = completion.choices[0].message.content or ""
            payload = _parse_payload(content)
            return {
                "sentiment": payload.sentiment,
                "sentiment_score": payload.sentiment_score,
                "summary": payload.summary,
                "embedding": local_embedding,
                "highlights": payload.highlights,
            }
        except (APIConnectionError, APITimeoutError, APIStatusError, RateLimitError) as exc:
            last_error = exc
            delay = settings.FOUNDATION_CHAT_BACKOFF_SECONDS * (attempt + 1)
            logger.warning(
                "Chat completion attempt %s failed (%s). Retrying in %.2fs",
                attempt + 1,
                exc.__class__.__name__,
                delay,
            )
            await asyncio.sleep(delay)
            continue
        except (ValidationError, ValueError, json.JSONDecodeError) as exc:
            logger.warning("Invalid LLM payload structure: %s", exc)
            break
        except Exception as exc:
            last_error = exc
            logger.exception("Chat completion sentiment analysis failed")
            break

    if last_error and not isinstance(last_error, ValidationError):
        logger.warning(
            "Falling back to heuristic sentiment due to LLM error: %s", last_error
        )
    result = _fallback_analysis(text)
    if local_embedding is not None:
        result["embedding"] = local_embedding
    return result


def analyze_text(text: str, *, embedding: Optional[List[float]] = None) -> Dict[str, Any]:
    return asyncio.run(analyze_text_async(text, embedding=embedding))
