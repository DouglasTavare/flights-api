import asyncio
import json
from unittest.mock import patch

import fakeredis.aioredis
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.flight_events import _cache_key

SEARCH_DATE_STR = "2024-09-12"
CACHE_KEY = _cache_key(__import__("datetime").date(2024, 9, 12))

FLIGHT_EVENTS = [
    {
        "flight_number": "XX1234",
        "departure_city": "BUE",
        "arrival_city": "MAD",
        "departure_datetime": "2024-09-12T12:00:00Z",
        "arrival_datetime": "2024-09-13T00:00:00Z",
    },
    {
        "flight_number": "XX2345",
        "departure_city": "MAD",
        "arrival_city": "PMI",
        "departure_datetime": "2024-09-13T02:00:00Z",
        "arrival_datetime": "2024-09-13T03:00:00Z",
    },
    {
        "flight_number": "XX9000",
        "departure_city": "BUE",
        "arrival_city": "PMI",
        "departure_datetime": "2024-09-12T08:00:00Z",
        "arrival_datetime": "2024-09-13T06:00:00Z",
    },
]


@pytest.fixture()
def fake_redis():
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


@pytest.fixture()
def client(fake_redis):
    with patch("app.main.aioredis.from_url", return_value=fake_redis):
        with TestClient(app) as c:
            yield c


@pytest.fixture()
def client_with_cache(fake_redis):
    asyncio.run(fake_redis.set(CACHE_KEY, json.dumps(FLIGHT_EVENTS)))
    with patch("app.main.aioredis.from_url", return_value=fake_redis):
        with TestClient(app) as c:
            yield c
