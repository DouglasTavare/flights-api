import httpx
import redis.asyncio as aioredis
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.config import settings
from app.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()


@router.get("/health")
async def health(request: Request) -> JSONResponse:
    status = {"redis": "ok", "flight_events_api": "ok"}
    http_status = 200

    try:
        redis_client: aioredis.Redis = request.app.state.redis
        await redis_client.ping()
    except Exception as e:
        logger.warning("Health check: Redis unavailable", extra={"error": str(e)})
        status["redis"] = "unavailable"
        http_status = 503

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{settings.flight_events_api_url}/flight-events",
                timeout=5.0,
            )
            response.raise_for_status()
    except Exception as e:
        logger.warning(
            "Health check: flight-events-api unavailable", extra={"error": str(e)}
        )
        status["flight_events_api"] = "unavailable"
        http_status = 503

    return JSONResponse(status_code=http_status, content=status)
