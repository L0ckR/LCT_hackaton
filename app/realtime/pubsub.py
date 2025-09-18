import asyncio
import json
import logging
from contextlib import asynccontextmanager

from redis import Redis
from redis.asyncio import from_url as async_redis_from_url

from app.core.config import settings
from app.realtime.dashboard import dashboard_events

logger = logging.getLogger(__name__)
CHANNEL = "dashboard_events"


def publish_event_sync(message: dict) -> None:
    try:
        client = Redis.from_url(settings.REDIS_URL)
        client.publish(CHANNEL, json.dumps(message))
    except Exception:  # pragma: no cover - defensive
        logger.exception("Failed to publish realtime event")


@asynccontextmanager
async def redis_pubsub():
    client = async_redis_from_url(settings.REDIS_URL)
    try:
        pubsub = client.pubsub()
        await pubsub.subscribe(CHANNEL)
        yield pubsub
    finally:
        await pubsub.close()
        await client.close()


async def start_pubsub_listener() -> None:
    while True:
        try:
            async with redis_pubsub() as pubsub:
                async for message in pubsub.listen():
                    if message.get("type") != "message":
                        continue
                    data = message.get("data")
                    if isinstance(data, bytes):
                        data = data.decode("utf-8")
                    try:
                        payload = json.loads(data)
                    except Exception:
                        logger.warning("Received malformed realtime payload: %s", data)
                        continue
                    await dashboard_events.broadcast(payload)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Realtime listener crashed; retrying in 2s")
            await asyncio.sleep(2)
