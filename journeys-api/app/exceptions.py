class FlightEventsUnavailable(Exception):
    """flight-events-api is unreachable or returned a connection error."""


class FlightEventsTimeout(Exception):
    """flight-events-api did not respond within the allowed timeout."""


class FlightEventsBadResponse(Exception):
    """flight-events-api returned an unexpected HTTP error status."""

    def __init__(self, status_code: int) -> None:
        self.status_code = status_code
        super().__init__(f"flight-events-api responded with {status_code}")
