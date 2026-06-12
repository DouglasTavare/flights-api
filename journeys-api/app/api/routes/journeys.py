from datetime import date

import redis.asyncio as aioredis
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from app.logger import get_logger
from app.services.flight_events import get_flight_event_index
from app.services.journey_search import search_journeys

logger = get_logger(__name__)
router = APIRouter()


@router.get("/journeys/search")
async def search(
    request: Request,
    date: date = Query(..., description="Departure date (YYYY-MM-DD)"),
    from_: str = Query(..., alias="from", min_length=3, max_length=3),
    to: str = Query(..., min_length=3, max_length=3),
) -> JSONResponse:
    origin = from_.upper()
    destination = to.upper()

    if origin == destination:
        raise HTTPException(
            status_code=400,
            detail="'from' and 'to' must be different cities.",
        )

    logger.info(
        "Journey search request",
        extra={"date": str(date), "origin": origin, "destination": destination},
    )

    redis_client: aioredis.Redis = request.app.state.redis
    index = await get_flight_event_index(redis_client, date)
    journeys = search_journeys(index, date, origin, destination)
    return JSONResponse(content=[j.model_dump() for j in journeys])
