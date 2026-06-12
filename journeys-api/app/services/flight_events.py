import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date

import httpx
import redis.asyncio as aioredis
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.config import settings
from app.exceptions import (
    FlightEventsBadResponse,
    FlightEventsTimeout,
    FlightEventsUnavailable,
)
from app.logger import get_logger
from app.models.flight_event import FlightEvent

logger = get_logger(__name__)


def _cache_key(search_date: date) -> str:
    # Scoped by date so each day has an independent TTL — important for the
    # connection matrix use case where multiple dates are queried in parallel.
    return f"flight_events:{search_date.isoformat()}"


@dataclass
class FlightEventIndex:
    """
    Pre-built search index over all flight events.

    departures[city] → events leaving that city, sorted by departure_datetime.
    arrivals[city]   → events arriving at that city, sorted by departure_datetime.
    """

    departures: dict[str, list[FlightEvent]] = field(
        default_factory=lambda: defaultdict(list)
    )
    arrivals: dict[str, list[FlightEvent]] = field(
        default_factory=lambda: defaultdict(list)
    )

    @classmethod
    def build(cls, events: list[FlightEvent]) -> "FlightEventIndex":
        index = cls()
        for event in events:
            index.departures[event.departure_city].append(event)
            index.arrivals[event.arrival_city].append(event)

        for city in index.departures:
            index.departures[city].sort(key=lambda e: e.departure_datetime)
        for city in index.arrivals:
            index.arrivals[city].sort(key=lambda e: e.departure_datetime)

        return index


@retry(
    retry=retry_if_exception_type(httpx.TransportError),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    reraise=False,
)
async def _fetch_from_api() -> list[FlightEvent]:
    try:
        logger.info("Fetching flight events from external API")
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{settings.flight_events_api_url}/flight-events", timeout=10.0
            )
            response.raise_for_status()
    except httpx.TimeoutException as e:
        logger.error("flight-events-api timed out")
        raise FlightEventsTimeout() from e
    except httpx.ConnectError as e:
        logger.error("flight-events-api is unreachable", extra={"error": str(e)})
        raise FlightEventsUnavailable() from e
    except httpx.HTTPStatusError as e:
        logger.error(
            "flight-events-api returned unexpected status",
            extra={"status_code": e.response.status_code},
        )
        raise FlightEventsBadResponse(e.response.status_code) from e

    events = [FlightEvent.model_validate(item) for item in response.json()]
    logger.info("Fetched flight events from API", extra={"count": len(events)})
    return events


async def get_flight_event_index(
    redis_client: aioredis.Redis, search_date: date
) -> FlightEventIndex:
    key = _cache_key(search_date)

    try:
        cached = await redis_client.get(key)
    except Exception as e:
        # Redis is unavailable — degrade gracefully by fetching directly from the API
        logger.warning("Redis unavailable, fetching from API directly", extra={"error": str(e)})
        cached = None

    if cached:
        logger.info("Cache hit", extra={"key": key})
        raw = json.loads(cached)
        events = [FlightEvent.model_validate(item) for item in raw]
    else:
        logger.info("Cache miss", extra={"key": key})
        events = await _fetch_from_api()
        try:
            serialized = json.dumps(
                [e.model_dump(mode="json") for e in events], default=str
            )
            await redis_client.setex(key, settings.cache_ttl, serialized)
            logger.info("Cache populated", extra={"key": key, "ttl": settings.cache_ttl})
        except Exception as e:
            # Redis write failure is non-fatal: the response is still served
            logger.warning("Failed to write to Redis cache", extra={"error": str(e)})

    return FlightEventIndex.build(events)
