import asyncio
import logging
from typing import Iterable, List, Optional

from app.services.embeddings import batcher
from app.services.ml import analyze_text_async, generate_embeddings_async

logger = logging.getLogger(__name__)


async def ensure_batcher_started() -> None:
    await batcher.start()


async def process_reviews(texts: Iterable[str]) -> List[dict]:
    texts = list(texts)
    if not texts:
        return []

    loop = asyncio.get_running_loop()
    if batcher.loop and batcher.loop is not loop:
        embeddings = await generate_embeddings_async(texts)
    else:
        await ensure_batcher_started()
        embeddings = []
        for text in texts:
            await batcher.enqueue(text)
        while len(embeddings) < len(texts):
            embeddings.extend(await batcher.get_embeddings())

    analyses: List[dict] = []
    for text, embedding in zip(texts, embeddings):
        result = await analyze_text_async(text, embedding=embedding)
        analyses.append(result)
    return analyses
