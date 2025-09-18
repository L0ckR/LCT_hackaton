import asyncio
import logging
from typing import Iterable, List, Optional

from app.core.config import settings
from app.realtime import publish_event
from app.services.embeddings import batcher
from app.services.ml import analyze_text, generate_embeddings

logger = logging.getLogger(__name__)


async def ensure_batcher_started() -> None:
    await batcher.start()


async def process_reviews(texts: Iterable[str]) -> List[dict]:
    texts = list(texts)
    if not texts:
        return []

    loop = asyncio.get_running_loop()
    if batcher.loop and batcher.loop is not loop:
        embeddings = generate_embeddings(texts)
    else:
        await ensure_batcher_started()
        embeddings = []
        for text in texts:
            await batcher.enqueue(text)
        while len(embeddings) < len(texts):
            embeddings.extend(await batcher.get_embeddings())

    analyses: List[dict] = []
    for text, embedding in zip(texts, embeddings):
        result = analyze_text(text, embedding=embedding)
        analyses.append(result)
    await publish_event({"type": "analysis_completed", "count": len(analyses)})
    return analyses
