import asyncio
import json
import logging
import re
from typing import Any, Dict, Iterable, List, Optional

from openai import APIConnectionError, APIStatusError, APITimeoutError, RateLimitError
from pydantic import BaseModel, Field, ValidationError
from textblob import TextBlob

from app.core.config import settings
from app.services.openai_client import create_chat_completion, create_embeddings

logger = logging.getLogger(__name__)


class SentimentPayload(BaseModel):
    sentiment: str
    sentiment_score: Optional[float] = None
    summary: Optional[str] = None
    highlights: List[str] = Field(default_factory=list)

    @staticmethod
    def clean(data: Dict[str, Any]) -> "SentimentPayload":
        payload = SentimentPayload.model_validate(data)
        if payload.sentiment not in {"positive", "negative", "neutral"}:
            raise ValidationError(
                [
                    {
                        "loc": ("sentiment",),
                        "msg": "invalid label",
                        "type": "value_error",
                    }
                ],
                SentimentPayload,
            )
        return payload


def _llm_available() -> bool:
    return bool(settings.FOUNDATION_API_KEY)


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


def _parse_model_response(content: str) -> Dict[str, Any]:
    if not content:
        raise ValueError("Empty response")
    stripped = content.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```[a-zA-Z0-9]*", "", stripped)
        stripped = re.sub(r"```$", "", stripped).strip()

    candidates = [stripped]
    match = re.search(r"\{.*\}", stripped, re.S)
    if match:
        candidates.append(match.group(0))

    for candidate in candidates:
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    raise ValueError("Unable to parse JSON sentiment response")


async def generate_embeddings_async(texts: Iterable[str]) -> List[Optional[List[float]]]:
    texts = list(texts)
    if not texts:
        return []
    if not _llm_available():
        return [None] * len(texts)

    batch_size = max(1, settings.FOUNDATION_EMBEDDING_BATCH_SIZE)
    embeddings: List[Optional[List[float]]] = []
    try:
        for start in range(0, len(texts), batch_size):
            chunk = texts[start : start + batch_size]
            try:
                response = await create_embeddings(
                    model=settings.FOUNDATION_EMBEDDING_MODEL,
                    input=chunk,
                )
            except Exception:
                logger.exception("Embedding batch failed; continuing without vectors")
                embeddings.extend([None] * len(chunk))
                continue
            ordered = sorted(response.data, key=lambda item: item.index)
            embeddings.extend([item.embedding for item in ordered])
    except Exception:
        logger.exception("Embedding generation failed; continuing without embeddings")
        missing = len(texts) - len(embeddings)
        embeddings.extend([None] * max(0, missing))

    if len(embeddings) < len(texts):
        embeddings.extend([None] * (len(texts) - len(embeddings)))
    return embeddings


async def analyze_text_async(
    text: str, *, embedding: Optional[List[float]] = None
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
        "Проанализируй текст ниже и верни строго JSON со следующими полями: "
        "sentiment (одно из значений: positive, negative, neutral), "
        "sentiment_score (число от -1 до 1), summary (краткое описание до 40 слов), "
        "highlights (список из ключевых тезисов, короткие строки).\n\n"
        f"Отзыв: "
        f"""{text}"""
    )

    schema = {
        "name": "sentiment_payload",
        "schema": {
            "type": "object",
            "properties": {
                "sentiment": {"type": "string"},
                "sentiment_score": {"type": ["number", "null"]},
                "summary": {"type": ["string", "null"]},
                "highlights": {
                    "type": "array",
                    "items": {"type": "string"},
                },
            },
            "required": ["sentiment"],
            "additionalProperties": False,
        },
    }

    retries = max(1, settings.FOUNDATION_CHAT_RETRIES)
    for attempt in range(retries):
        try:
            completion = await create_chat_completion(
                model=settings.FOUNDATION_CHAT_MODEL,
                max_tokens=500,
                temperature=0.3,
                top_p=0.9,
                presence_penalty=0,
                response_format={"type": "json_schema", "json_schema": schema},
                messages=[{"role": "user", "content": prompt}],
            )
            content = completion.choices[0].message.content
            raw = _parse_model_response(content)
            payload = SentimentPayload.clean(raw)
            summary = payload.summary
            if isinstance(summary, (list, dict)):
                summary = json.dumps(summary)
            return {
                "sentiment": payload.sentiment,
                "sentiment_score": payload.sentiment_score,
                "summary": summary,
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
        except ValidationError as exc:
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
