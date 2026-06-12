import json
from unittest.mock import AsyncMock, patch

import pytest

from app.services.flight_events import _cache_key
from tests.integration.conftest import CACHE_KEY, FLIGHT_EVENTS


class TestEndpointValidation:
    def test_missing_date_returns_422(self, client):
        response = client.get("/journeys/search?from=BUE&to=PMI")
        assert response.status_code == 422

    def test_missing_from_returns_422(self, client):
        response = client.get("/journeys/search?date=2024-09-12&to=PMI")
        assert response.status_code == 422

    def test_missing_to_returns_422(self, client):
        response = client.get("/journeys/search?date=2024-09-12&from=BUE")
        assert response.status_code == 422

    def test_invalid_date_format_returns_422(self, client):
        response = client.get("/journeys/search?date=12-09-2024&from=BUE&to=PMI")
        assert response.status_code == 422

    def test_same_origin_and_destination_returns_400(self, client):
        response = client.get("/journeys/search?date=2024-09-12&from=BUE&to=BUE")
        assert response.status_code == 400
        assert "different" in response.json()["detail"].lower()


class TestEndpointWithCache:
    def test_returns_200(self, client_with_cache):
        response = client_with_cache.get(
            "/journeys/search?date=2024-09-12&from=BUE&to=PMI"
        )
        assert response.status_code == 200

    def test_returns_list(self, client_with_cache):
        response = client_with_cache.get(
            "/journeys/search?date=2024-09-12&from=BUE&to=PMI"
        )
        assert isinstance(response.json(), list)

    def test_finds_direct_and_connecting(self, client_with_cache):
        response = client_with_cache.get(
            "/journeys/search?date=2024-09-12&from=BUE&to=PMI"
        )
        journeys = response.json()
        connections_counts = {j["connections"] for j in journeys}
        assert 0 in connections_counts
        assert 1 in connections_counts

    def test_journey_response_shape(self, client_with_cache):
        response = client_with_cache.get(
            "/journeys/search?date=2024-09-12&from=BUE&to=PMI"
        )
        journeys = response.json()
        assert len(journeys) > 0

        journey = journeys[0]
        assert "connections" in journey
        assert "path" in journey
        assert isinstance(journey["path"], list)

        leg = journey["path"][0]
        assert "flight_number" in leg
        assert "from" in leg
        assert "to" in leg
        assert "departure_time" in leg
        assert "arrival_time" in leg

    def test_datetime_fields_include_utc(self, client_with_cache):
        response = client_with_cache.get(
            "/journeys/search?date=2024-09-12&from=BUE&to=PMI"
        )
        journeys = response.json()
        for journey in journeys:
            for leg in journey["path"]:
                assert leg["departure_time"].endswith("UTC")
                assert leg["arrival_time"].endswith("UTC")

    def test_no_results_returns_empty_list(self, client_with_cache):
        response = client_with_cache.get(
            "/journeys/search?date=2024-09-12&from=BUE&to=NYC"
        )
        assert response.status_code == 200
        assert response.json() == []

    def test_city_codes_are_case_insensitive(self, client_with_cache):
        response_upper = client_with_cache.get(
            "/journeys/search?date=2024-09-12&from=BUE&to=PMI"
        )
        response_lower = client_with_cache.get(
            "/journeys/search?date=2024-09-12&from=bue&to=pmi"
        )
        assert response_upper.json() == response_lower.json()


class TestEndpointCacheMiss:
    def test_fetches_from_api_on_cache_miss(self, client):
        with patch(
            "app.services.flight_events._fetch_from_api",
            new_callable=AsyncMock,
            return_value=[],
        ) as mock_fetch:
            response = client.get("/journeys/search?date=2024-09-12&from=BUE&to=PMI")
            assert response.status_code == 200
            mock_fetch.assert_called_once()

    def test_populates_cache_after_api_call(self, client, fake_redis):
        import asyncio

        from app.models.flight_event import FlightEvent

        events = [FlightEvent.model_validate(e) for e in FLIGHT_EVENTS]

        with patch(
            "app.services.flight_events._fetch_from_api",
            new_callable=AsyncMock,
            return_value=events,
        ):
            client.get("/journeys/search?date=2024-09-12&from=BUE&to=PMI")

        cached = asyncio.run(fake_redis.get(CACHE_KEY))
        assert cached is not None

    def test_cache_key_is_scoped_by_date(self, client, fake_redis):
        import asyncio

        from app.models.flight_event import FlightEvent

        events = [FlightEvent.model_validate(e) for e in FLIGHT_EVENTS]

        with patch(
            "app.services.flight_events._fetch_from_api",
            new_callable=AsyncMock,
            return_value=events,
        ):
            client.get("/journeys/search?date=2024-09-12&from=BUE&to=PMI")

        # A different date must not hit the same cache key
        other_key = _cache_key(__import__("datetime").date(2024, 9, 13))
        cached_other = asyncio.run(fake_redis.get(other_key))
        assert cached_other is None


class TestExternalServiceErrors:
    def test_flight_events_api_unavailable_returns_503(self, client):
        from app.exceptions import FlightEventsUnavailable

        with patch(
            "app.services.flight_events._fetch_from_api",
            new_callable=AsyncMock,
            side_effect=FlightEventsUnavailable(),
        ):
            response = client.get("/journeys/search?date=2024-09-12&from=BUE&to=PMI")
        assert response.status_code == 503

    def test_flight_events_api_timeout_returns_504(self, client):
        from app.exceptions import FlightEventsTimeout

        with patch(
            "app.services.flight_events._fetch_from_api",
            new_callable=AsyncMock,
            side_effect=FlightEventsTimeout(),
        ):
            response = client.get("/journeys/search?date=2024-09-12&from=BUE&to=PMI")
        assert response.status_code == 504

    def test_flight_events_api_bad_response_returns_502(self, client):
        from app.exceptions import FlightEventsBadResponse

        with patch(
            "app.services.flight_events._fetch_from_api",
            new_callable=AsyncMock,
            side_effect=FlightEventsBadResponse(500),
        ):
            response = client.get("/journeys/search?date=2024-09-12&from=BUE&to=PMI")
        assert response.status_code == 502


class TestHealthEndpoint:
    def test_health_returns_ok_when_dependencies_up(self, client):
        with patch("app.api.routes.health.httpx.AsyncClient") as mock_http:
            mock_response = AsyncMock()
            mock_response.raise_for_status = lambda: None
            mock_http.return_value.__aenter__ = AsyncMock(return_value=mock_http.return_value)
            mock_http.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_http.return_value.get = AsyncMock(return_value=mock_response)

            response = client.get("/health")

        assert response.status_code == 200
        body = response.json()
        assert body["redis"] == "ok"
