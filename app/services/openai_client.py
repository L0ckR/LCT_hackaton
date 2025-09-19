import asyncio
from functools import lru_cache
from typing import Any, Dict, List

from openai import AsyncOpenAI

from app.core.config import settings

_CHAT_SEMAPHORE = asyncio.Semaphore(max(1, getattr(settings, "FOUNDATION_CHAT_CONCURRENCY", 3)))
_EMBED_SEMAPHORE = asyncio.Semaphore(max(1, getattr(settings, "FOUNDATION_EMBEDDING_CONCURRENCY", 5)))


@lru_cache(maxsize=1)
def get_async_client() -> AsyncOpenAI:
    return AsyncOpenAI(
        api_key=settings.FOUNDATION_API_KEY,
        base_url=settings.FOUNDATION_API_BASE_URL,
    )


async def create_chat_completion(**kwargs: Any) -> Any:
    client = get_async_client()
    async with _CHAT_SEMAPHORE:
        return await client.chat.completions.create(**kwargs)


async def create_embeddings(**kwargs: Any) -> Any:
    client = get_async_client()
    async with _EMBED_SEMAPHORE:
        return await client.embeddings.create(**kwargs)
