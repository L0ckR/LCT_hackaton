import asyncio
from typing import Iterable, List

from app.services.ml import analyze_text_async, generate_embeddings_async


async def process_reviews(texts: Iterable[str]) -> List[dict]:
    items = list(texts)
    if not items:
        return []
    embeddings = await generate_embeddings_async(items)
    tasks = [analyze_text_async(text, embedding) for text, embedding in zip(items, embeddings)]
    return await asyncio.gather(*tasks)
