import asyncio
import logging
from contextlib import suppress

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
    ]
)

logging.getLogger('app.services.review_parser').setLevel(logging.DEBUG)

from app.api.routes import analytics, auth, parser, reviews, widgets
from app.db.base import Base
from app.db.session import engine, ensure_extensions, wait_for_db
from app.web import router as web_router, ws_router as web_ws_router
from app.realtime import start_pubsub_listener

logger = logging.getLogger(__name__)

wait_for_db()
ensure_extensions()
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Review Analytics Service")

app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(auth.router)
app.include_router(reviews.router)
app.include_router(widgets.router)
app.include_router(analytics.router)
app.include_router(parser.router)
app.include_router(web_router)
app.include_router(web_ws_router)


@app.on_event("startup")
async def on_startup() -> None:
    app.state.pubsub_task = asyncio.create_task(start_pubsub_listener())


@app.on_event("shutdown")
async def on_shutdown() -> None:
    task = getattr(app.state, "pubsub_task", None)
    if task:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
