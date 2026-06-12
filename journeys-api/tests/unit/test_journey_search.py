from datetime import date

import pytest

from app.models.flight_event import FlightEvent
from app.services.flight_events import FlightEventIndex
from app.services.journey_search import search_journeys

SEARCH_DATE = date(2024, 9, 12)


def make_event(
    flight_number: str,
    departure_city: str,
    arrival_city: str,
    departure_datetime: str,
    arrival_datetime: str,
) -> FlightEvent:
    return FlightEvent(
        flight_number=flight_number,
        departure_city=departure_city,
        arrival_city=arrival_city,
        departure_datetime=departure_datetime,
        arrival_datetime=arrival_datetime,
    )


def build_index(events: list[FlightEvent]) -> FlightEventIndex:
    return FlightEventIndex.build(events)


class TestDirectJourney:
    def test_finds_direct_flight(self):
        events = [
            make_event("XX1000", "BUE", "MAD", "2024-09-12T12:00:00Z", "2024-09-13T00:00:00Z"),
        ]
        index = build_index(events)
        result = search_journeys(index, SEARCH_DATE, "BUE", "MAD")

        assert len(result) == 1
        assert result[0].connections == 0
        assert result[0].path[0].flight_number == "XX1000"

    def test_no_direct_flight_returns_empty(self):
        events = [
            make_event("XX1000", "BUE", "MAD", "2024-09-12T12:00:00Z", "2024-09-13T00:00:00Z"),
        ]
        index = build_index(events)
        result = search_journeys(index, SEARCH_DATE, "BUE", "PMI")

        assert result == []

    def test_wrong_date_returns_empty(self):
        events = [
            make_event("XX1000", "BUE", "MAD", "2024-09-13T12:00:00Z", "2024-09-14T00:00:00Z"),
        ]
        index = build_index(events)
        result = search_journeys(index, SEARCH_DATE, "BUE", "MAD")

        assert result == []

    def test_departure_time_includes_utc_suffix(self):
        events = [
            make_event("XX1000", "BUE", "MAD", "2024-09-12T12:00:00Z", "2024-09-13T00:00:00Z"),
        ]
        index = build_index(events)
        result = search_journeys(index, SEARCH_DATE, "BUE", "MAD")

        assert result[0].path[0].departure_time.endswith("UTC")
        assert result[0].path[0].arrival_time.endswith("UTC")


class TestConnectingJourney:
    def test_finds_connecting_flight_within_4h(self):
        events = [
            make_event("XX1234", "BUE", "MAD", "2024-09-12T12:00:00Z", "2024-09-13T00:00:00Z"),
            make_event("XX2345", "MAD", "PMI", "2024-09-13T02:00:00Z", "2024-09-13T03:00:00Z"),
        ]
        index = build_index(events)
        result = search_journeys(index, SEARCH_DATE, "BUE", "PMI")

        assert len(result) == 1
        assert result[0].connections == 1
        assert result[0].path[0].flight_number == "XX1234"
        assert result[0].path[1].flight_number == "XX2345"

    def test_connection_exactly_4h_is_valid(self):
        events = [
            make_event("XX1234", "BUE", "MAD", "2024-09-12T12:00:00Z", "2024-09-13T00:00:00Z"),
            make_event("XX2345", "MAD", "PMI", "2024-09-13T04:00:00Z", "2024-09-13T05:00:00Z"),
        ]
        index = build_index(events)
        result = search_journeys(index, SEARCH_DATE, "BUE", "PMI")

        assert len(result) == 1
        assert result[0].connections == 1

    def test_connection_over_4h_is_rejected(self):
        events = [
            make_event("XX1234", "BUE", "MAD", "2024-09-12T12:00:00Z", "2024-09-13T00:00:00Z"),
            make_event("XX2345", "MAD", "PMI", "2024-09-13T04:01:00Z", "2024-09-13T05:01:00Z"),
        ]
        index = build_index(events)
        result = search_journeys(index, SEARCH_DATE, "BUE", "PMI")

        assert result == []

    def test_second_leg_departing_before_first_leg_arrives_is_rejected(self):
        events = [
            make_event("XX1234", "BUE", "MAD", "2024-09-12T12:00:00Z", "2024-09-13T00:00:00Z"),
            make_event("XX2345", "MAD", "PMI", "2024-09-12T23:00:00Z", "2024-09-13T00:00:00Z"),
        ]
        index = build_index(events)
        result = search_journeys(index, SEARCH_DATE, "BUE", "PMI")

        assert result == []

    def test_total_duration_exactly_24h_is_valid(self):
        events = [
            make_event("XX1234", "BUE", "MAD", "2024-09-12T12:00:00Z", "2024-09-13T00:00:00Z"),
            make_event("XX2345", "MAD", "PMI", "2024-09-13T02:00:00Z", "2024-09-13T12:00:00Z"),
        ]
        index = build_index(events)
        result = search_journeys(index, SEARCH_DATE, "BUE", "PMI")

        assert len(result) == 1

    def test_total_duration_over_24h_is_rejected(self):
        events = [
            make_event("XX1234", "BUE", "MAD", "2024-09-12T12:00:00Z", "2024-09-13T00:00:00Z"),
            make_event("XX2345", "MAD", "PMI", "2024-09-13T02:00:00Z", "2024-09-13T12:01:00Z"),
        ]
        index = build_index(events)
        result = search_journeys(index, SEARCH_DATE, "BUE", "PMI")

        assert result == []


class TestMultipleResults:
    def test_returns_all_valid_combinations(self):
        events = [
            make_event("XX1234", "BUE", "MAD", "2024-09-12T12:00:00Z", "2024-09-13T00:00:00Z"),
            make_event("XX2345", "MAD", "PMI", "2024-09-13T02:00:00Z", "2024-09-13T03:00:00Z"),
            make_event("XX3456", "MAD", "PMI", "2024-09-13T03:00:00Z", "2024-09-13T04:00:00Z"),
        ]
        index = build_index(events)
        result = search_journeys(index, SEARCH_DATE, "BUE", "PMI")

        assert len(result) == 2
        flight_pairs = [
            (j.path[0].flight_number, j.path[1].flight_number) for j in result
        ]
        assert ("XX1234", "XX2345") in flight_pairs
        assert ("XX1234", "XX3456") in flight_pairs

    def test_returns_direct_and_connecting_when_both_exist(self):
        events = [
            make_event("XX9000", "BUE", "PMI", "2024-09-12T08:00:00Z", "2024-09-13T06:00:00Z"),
            make_event("XX1234", "BUE", "MAD", "2024-09-12T12:00:00Z", "2024-09-13T00:00:00Z"),
            make_event("XX2345", "MAD", "PMI", "2024-09-13T02:00:00Z", "2024-09-13T03:00:00Z"),
        ]
        index = build_index(events)
        result = search_journeys(index, SEARCH_DATE, "BUE", "PMI")

        connections_counts = {j.connections for j in result}
        assert 0 in connections_counts
        assert 1 in connections_counts

    def test_multiple_intermediate_cities(self):
        events = [
            make_event("XX1234", "BUE", "MAD", "2024-09-12T12:00:00Z", "2024-09-13T00:00:00Z"),
            make_event("XX7890", "BUE", "LIS", "2024-09-12T14:00:00Z", "2024-09-13T03:00:00Z"),
            make_event("XX2345", "MAD", "PMI", "2024-09-13T02:00:00Z", "2024-09-13T03:00:00Z"),
            make_event("XX8901", "LIS", "PMI", "2024-09-13T05:00:00Z", "2024-09-13T06:30:00Z"),
        ]
        index = build_index(events)
        result = search_journeys(index, SEARCH_DATE, "BUE", "PMI")

        assert len(result) == 2
        intermediate_cities = {j.path[0].to for j in result}
        assert "MAD" in intermediate_cities
        assert "LIS" in intermediate_cities

    def test_no_events_returns_empty(self):
        index = build_index([])
        result = search_journeys(index, SEARCH_DATE, "BUE", "PMI")
        assert result == []
