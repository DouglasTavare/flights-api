import bisect
from datetime import date, datetime, timedelta, timezone

from app.logger import get_logger
from app.models.flight_event import FlightEvent
from app.models.journey import Journey, JourneyLeg
from app.services.flight_events import FlightEventIndex

logger = get_logger(__name__)

_MAX_CONNECTION_HOURS = timedelta(hours=4)
_MAX_TOTAL_HOURS = timedelta(hours=24)


def _to_leg(event: FlightEvent) -> JourneyLeg:
    # Append UTC suffix so consumers know the timezone unambiguously
    fmt = "%Y-%m-%d %H:%M UTC"
    return JourneyLeg(
        flight_number=event.flight_number,
        from_=event.departure_city,
        to=event.arrival_city,
        departure_time=event.departure_datetime.strftime(fmt),
        arrival_time=event.arrival_datetime.strftime(fmt),
    )


def _departure_keys(events: list[FlightEvent]) -> list[datetime]:
    """Sorted departure datetimes for bisect lookups."""
    return [e.departure_datetime for e in events]


def search_journeys(
    index: FlightEventIndex,
    search_date: date,
    origin: str,
    destination: str,
) -> list[Journey]:
    journeys: list[Journey] = []

    # R1 — filter first_legs: depart from origin on the requested date (UTC)
    first_legs = [
        e
        for e in index.departures.get(origin, [])
        if e.departure_datetime.astimezone(timezone.utc).date() == search_date
    ]

    if not first_legs:
        logger.info(
            "No first legs found",
            extra={"origin": origin, "date": str(search_date)},
        )
        return journeys

    # Earliest possible departure of first_leg (for R3 upper bound on second_legs)
    earliest_departure = min(e.departure_datetime for e in first_legs)

    # R3 — pre-filter second_legs: arrive at destination within 24h of earliest first_leg departure
    second_leg_pool = [
        e
        for e in index.arrivals.get(destination, [])
        if e.arrival_datetime <= earliest_departure + _MAX_TOTAL_HOURS
    ]

    # Bidirectional intersection: only intermediate cities reachable from both sides
    first_leg_cities = {e.arrival_city for e in first_legs}
    second_leg_cities = {e.departure_city for e in second_leg_pool}
    intermediate_cities = first_leg_cities & second_leg_cities

    for first_leg in first_legs:
        # Direct journey — connections = 0 (no layovers)
        if first_leg.arrival_city == destination:
            journeys.append(Journey(connections=0, path=[_to_leg(first_leg)]))
            continue

        if first_leg.arrival_city not in intermediate_cities:
            continue

        # Connecting journeys through this intermediate city — connections = 1 (one layover)
        candidates = [
            e for e in second_leg_pool if e.departure_city == first_leg.arrival_city
        ]
        if not candidates:
            continue

        departure_keys = _departure_keys(candidates)

        # R2 — connection window: (arrival, arrival + 4h]
        window_start = first_leg.arrival_datetime
        window_end = first_leg.arrival_datetime + _MAX_CONNECTION_HOURS

        # Binary search: first candidate with departure_datetime > window_start
        lo = bisect.bisect_right(departure_keys, window_start)

        for i in range(lo, len(candidates)):
            second_leg = candidates[i]
            if second_leg.departure_datetime > window_end:
                break

            # R3 — per-pair total duration check
            total_duration = second_leg.arrival_datetime - first_leg.departure_datetime
            if total_duration > _MAX_TOTAL_HOURS:
                continue

            journeys.append(
                Journey(connections=1, path=[_to_leg(first_leg), _to_leg(second_leg)])
            )

    logger.info(
        "Search complete",
        extra={
            "origin": origin,
            "destination": destination,
            "date": str(search_date),
            "results": len(journeys),
        },
    )
    return journeys
