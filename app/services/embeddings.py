import asyncio
import logging
from typing import Iterable, List, Optional

from app.core.config import settings
from app.services.ml import generate_embeddings

logger = logging.getLogger(__name__)


class EmbeddingBatcher:
    def __init__(self, batch_size: int, interval: float = 0.5) -> None:
        self.batch_size = batch_size
        self.interval = interval
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._result_queue: asyncio.Queue[List[Optional[List[float]]]] = asyncio.Queue()
        self._started = False
        self.loop: Optional[asyncio.AbstractEventLoop] = None

    async def start(self) -> None:
        if self._started:
            return
        self._started = True
        self.loop = asyncio.get_running_loop()
        asyncio.create_task(self._runner())

    async def _runner(self) -> None:
        while True:
            batch = await self._collect_batch()
            if not batch:
                continue
            try:
                embeddings = generate_embeddings(batch)
            except Exception:
                logger.exception("Embedding batch failed")
                embeddings = [None] * len(batch)
            await self._result_queue.put(embeddings)

    async def _collect_batch(self) -> List[str]:
        texts: List[str] = []
        try:
            first = await asyncio.wait_for(self._queue.get(), timeout=self.interval)
            texts.append(first)
        except asyncio.TimeoutError:
            return []
        while len(texts) < self.batch_size:
            try:
                texts.append(self._queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        return texts

    async def enqueue(self, text: str) -> None:
        await self._queue.put(text)

    async def get_embeddings(self) -> List[Optional[List[float]]]:
        return await self._result_queue.get()


batcher = EmbeddingBatcher(batch_size=settings.FOUNDATION_EMBEDDING_BATCH_SIZE)
