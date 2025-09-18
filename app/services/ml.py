import json
import logging
import re
from functools import lru_cache
from typing import Any, Dict, Iterable, List, Optional

from openai import OpenAI
from openai import APIConnectionError
from textblob import TextBlob

from app.core.config import settings

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _get_client() -> Optional[OpenAI]:
    api_key = settings.FOUNDATION_API_KEY
    if not api_key:
        logger.info("Foundation API key not configured; falling back to TextBlob sentiment")
        return None
    try:
        return OpenAI(api_key=api_key, base_url=settings.FOUNDATION_API_BASE_URL)
    except Exception:  # pragma: no cover - defensive
        logger.exception("Failed to initialize OpenAI client, falling back to TextBlob")
        return None


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
    # Remove common code fences like ```json ... ```
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


def generate_embeddings(texts: Iterable[str]) -> List[Optional[List[float]]]:
    texts = list(texts)
    if not texts:
        return []
    client = _get_client()
    if not client:
        return [None] * len(texts)

    batch_size = max(1, settings.FOUNDATION_EMBEDDING_BATCH_SIZE)
    embeddings: List[Optional[List[float]]] = []
    try:
        for start in range(0, len(texts), batch_size):
            chunk = texts[start : start + batch_size]
            response = client.embeddings.create(
                model=settings.FOUNDATION_EMBEDDING_MODEL,
                input=chunk,
            )
            ordered = sorted(response.data, key=lambda item: item.index)
            embeddings.extend([item.embedding for item in ordered])
    except Exception:
        logger.exception("Embedding generation failed; continuing without embeddings")
        missing = len(texts) - len(embeddings)
        embeddings.extend([None] * max(0, missing))

    if len(embeddings) < len(texts):
        embeddings.extend([None] * (len(texts) - len(embeddings)))
    return embeddings


def analyze_text(text: str, *, embedding: Optional[List[float]] = None) -> Dict[str, Any]:
    client = _get_client()
    if not client:
        return _fallback_analysis(text)

    local_embedding = embedding
    if local_embedding is None:
        try:
            embed_response = client.embeddings.create(
                model=settings.FOUNDATION_EMBEDDING_MODEL,
                input=[text],
            )
            local_embedding = embed_response.data[0].embedding
        except Exception:
            logger.exception("Embedding generation failed; continuing without embeddings")
            local_embedding = None

    try:
        prompt = (
            "You are an analyst for banking customer feedback. "
            "Summarize the sentiment of the review below and respond strictly as JSON with keys "
            "sentiment (one of positive, negative, neutral), sentiment_score (float from -1 to 1), "
            "summary (<=40 words), highlights (list of short bullet strings).\n\n"
            f"Review: "
            f"""{text}"""
        )
        completion = client.chat.completions.create(
            model=settings.FOUNDATION_CHAT_MODEL,
            max_tokens=500,
            temperature=0.3,
            top_p=0.9,
            presence_penalty=0,
            messages=[{"role": "user", "content": prompt}],
        )
        content = completion.choices[0].message.content
        data = _parse_model_response(content)
        sentiment = data.get("sentiment")
        score = data.get("sentiment_score")
        summary = data.get("summary")
        highlights = data.get("highlights") or []
        if isinstance(summary, (list, dict)):
            summary = json.dumps(summary)
        if not isinstance(highlights, list):
            highlights = [str(highlights)] if highlights else []
        if sentiment not in {"positive", "negative", "neutral"}:
            raise ValueError("Invalid sentiment label")
        return {
            "sentiment": sentiment,
            "sentiment_score": float(score) if score is not None else None,
            "summary": summary,
            "embedding": local_embedding,
            "highlights": highlights,
        }
    except APIConnectionError:
        logger.warning("Chat completion request failed due to connection error; using fallback")
        result = _fallback_analysis(text)
        if local_embedding is not None:
            result["embedding"] = local_embedding
        return result
    except Exception:
        logger.exception("Chat completion sentiment analysis failed; using fallback")
        result = _fallback_analysis(text)
        if local_embedding is not None:
            result["embedding"] = local_embedding
        return result
