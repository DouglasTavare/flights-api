"""
End-to-end tests that run against the full Docker Compose stack.

Requirements:
    docker compose up --build   (from the monorepo root)

Run with:
    poetry run pytest tests/e2e -v -m e2e
"""

import pytest
import httpx

BASE_URL = "http://localhost:8000"
DATE = "2026-06-12"


@pytest.mark.e2e
class TestE2EJourneySearch:
    def test_health_returns_ok(self):
        response = httpx.get(f"{BASE_URL}/health", timeout=5)
        assert response.status_code == 200
        body = response.json()
        assert body["redis"] == "ok"
        assert body["flight_events_api"] == "ok"

    def test_direct_journey_bue_to_pmi(self):
        response = httpx.get(
            f"{BASE_URL}/journeys/search",
            params={"date": DATE, "from": "BUE", "to": "PMI"},
            timeout=10,
        )
        assert response.status_code == 200
        journeys = response.json()
        assert len(journeys) > 0
        direct = [j for j in journeys if j["connections"] == 0]
        assert len(direct) > 0
        assert direct[0]["path"][0]["from"] == "BUE"
        assert direct[0]["path"][0]["to"] == "PMI"

    def test_connecting_journey_bue_to_pmi(self):
        response = httpx.get(
            f"{BASE_URL}/journeys/search",
            params={"date": DATE, "from": "BUE", "to": "PMI"},
            timeout=10,
        )
        assert response.status_code == 200
        journeys = response.json()
        connecting = [j for j in journeys if j["connections"] == 1]
        assert len(connecting) > 0
        for journey in connecting:
            assert len(journey["path"]) == 2
            assert journey["path"][0]["from"] == "BUE"
            assert journey["path"][-1]["to"] == "PMI"

    def test_datetime_fields_have_utc_suffix(self):
        response = httpx.get(
            f"{BASE_URL}/journeys/search",
            params={"date": DATE, "from": "BUE", "to": "PMI"},
            timeout=10,
        )
        journeys = response.json()
        for journey in journeys:
            for leg in journey["path"]:
                assert leg["departure_time"].endswith("UTC"), \
                    f"Expected UTC suffix: {leg['departure_time']}"
                assert leg["arrival_time"].endswith("UTC"), \
                    f"Expected UTC suffix: {leg['arrival_time']}"

    def test_no_results_for_unknown_destination(self):
        response = httpx.get(
            f"{BASE_URL}/journeys/search",
            params={"date": DATE, "from": "BUE", "to": "NYC"},
            timeout=10,
        )
        assert response.status_code == 200
        assert response.json() == []

    def test_same_origin_and_destination_returns_400(self):
        response = httpx.get(
            f"{BASE_URL}/journeys/search",
            params={"date": DATE, "from": "BUE", "to": "BUE"},
            timeout=10,
        )
        assert response.status_code == 400

    def test_missing_parameter_returns_422(self):
        response = httpx.get(
            f"{BASE_URL}/journeys/search",
            params={"from": "BUE", "to": "PMI"},
            timeout=10,
        )
        assert response.status_code == 422

    def test_second_search_hits_cache(self):
        params = {"date": DATE, "from": "BUE", "to": "MAD"}
        first = httpx.get(f"{BASE_URL}/journeys/search", params=params, timeout=10)
        second = httpx.get(f"{BASE_URL}/journeys/search", params=params, timeout=10)
        assert first.status_code == 200
        assert second.status_code == 200
        assert first.json() == second.json()
