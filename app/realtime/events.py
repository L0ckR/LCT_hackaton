import asyncio
from typing import Any, Dict

_event_queue: "asyncio.Queue[Dict[str, Any]]" = asyncio.Queue()


async def publish_event(message: Dict[str, Any]) -> None:
    await _event_queue.put(message)


async def event_stream():
    while True:
        message = await _event_queue.get()
        yield message
