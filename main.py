"""
main.py
-------
Starts the Jarvis FastAPI server.
  - Mounts Twilio voice webhook routes
  - Starts the background scheduler
  - Serves a health-check endpoint
"""

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from loguru import logger

from voice.twilio_handler import router as twilio_router
from scheduler.jobs import start_scheduler, stop_scheduler
from config.settings import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Starting {settings.jarvis_name}...")
    start_scheduler()
    yield
    logger.info(f"Shutting down {settings.jarvis_name}...")
    stop_scheduler()


app = FastAPI(
    title=f"{settings.jarvis_name} — Personal AI Assistant",
    lifespan=lifespan,
)

app.include_router(twilio_router)


@app.get("/health")
async def health():
    return {"status": "online", "assistant": settings.jarvis_name}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.port,
        reload=False,
        log_level="info",
    )
