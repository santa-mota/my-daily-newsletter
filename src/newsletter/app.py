"""ASGI entrypoint."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from newsletter.api.routes import router
from newsletter.db.base import init_db
from newsletter.jobs.scheduler import shutdown_scheduler, start_scheduler

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    start_scheduler()
    yield
    shutdown_scheduler()


app = FastAPI(title="My Daily Newsletter", lifespan=lifespan)
app.include_router(router)


@app.get("/")
def root() -> dict[str, str]:
    return {"service": "my-daily-newsletter", "docs": "/docs"}
