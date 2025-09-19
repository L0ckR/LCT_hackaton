import asyncio
from typing import Any, Dict, Set

from fastapi import WebSocket


class DashboardEventManager:
    def __init__(self) -> None:
        self._connections: Set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections.add(websocket)

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            self._connections.discard(websocket)

    async def broadcast(self, message: Dict[str, Any]) -> None:
        async with self._lock:
            targets = list(self._connections)
        dead: Set[WebSocket] = set()
        for websocket in targets:
            try:
                await websocket.send_json(message)
            except Exception:
                dead.add(websocket)
        if dead:
            async with self._lock:
                for websocket in dead:
                    self._connections.discard(websocket)


dashboard_events = DashboardEventManager()


async def broadcast_refresh() -> None:
    message = {"type": "reviews_updated"}
    await dashboard_events.broadcast(message)
    try:
        from app.realtime.pubsub import publish_event_sync

        publish_event_sync(message)
    except Exception:  # pragma: no cover - defensive
        pass
