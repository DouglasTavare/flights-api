from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.routes.health import router as health_router
from app.api.routes.journeys import router as journeys_router
from app.config import settings
from app.exceptions import (
    FlightEventsBadResponse,
    FlightEventsTimeout,
    FlightEventsUnavailable,
)
from app.logger import get_logger, setup_logging

setup_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up — connecting to Redis", extra={"url": settings.redis_url})
    app.state.redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    yield
    logger.info("Shutting down — closing Redis connection")
    await app.state.redis.aclose()


app = FastAPI(title="Journeys API", version="1.0.0", lifespan=lifespan)
app.include_router(journeys_router)
app.include_router(health_router)


@app.exception_handler(FlightEventsUnavailable)
async def flight_events_unavailable_handler(
    request: Request, exc: FlightEventsUnavailable
) -> JSONResponse:
    logger.error("flight-events-api unavailable")
    return JSONResponse(
        status_code=503,
        content={"detail": "Flight events service is currently unavailable."},
    )


@app.exception_handler(FlightEventsTimeout)
async def flight_events_timeout_handler(
    request: Request, exc: FlightEventsTimeout
) -> JSONResponse:
    logger.error("flight-events-api timed out")
    return JSONResponse(
        status_code=504,
        content={"detail": "Flight events service timed out. Please try again."},
    )


@app.exception_handler(FlightEventsBadResponse)
async def flight_events_bad_response_handler(
    request: Request, exc: FlightEventsBadResponse
) -> JSONResponse:
    logger.error(
        "flight-events-api bad response",
        extra={"status_code": exc.status_code},
    )
    return JSONResponse(
        status_code=502,
        content={
            "detail": f"Flight events service returned an unexpected error (HTTP {exc.status_code})."
        },
    )
