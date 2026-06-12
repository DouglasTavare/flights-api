# flights-api

Monorepo containing two services:

| Service | Responsibility | Port |
|---|---|---|
| `journeys-api` | Searches and combines flight journeys | 8000 |
| `flight-events-api` | Stub repository of individual flight events | 8001 |

---

## Requirements

- [Docker](https://docs.docker.com/get-docker/) and Docker Compose
- [Poetry](https://python-poetry.org/docs/#installation) (for running tests locally)
- Python 3.12+

---

## Running with Docker Compose

From the repository root:

```bash
docker compose up --build
```

All three services (`journeys-api`, `flight-events-api`, `redis`) start together. The `journeys-api` waits for both `redis` and `flight-events-api` to be healthy before accepting requests.

| Service | URL | Interactive docs |
|---|---|---|
| journeys-api | http://localhost:8000 | http://localhost:8000/docs |
| flight-events-api | http://localhost:8001 | http://localhost:8001/docs |

To stop:

```bash
docker compose down
```

To stop and remove volumes (clears Redis cache):

```bash
docker compose down -v
```

---

## Running tests

Tests live inside `journeys-api/` and require no running infrastructure — Redis is replaced by `fakeredis` and the external API is mocked.

```bash
cd journeys-api

# Install dependencies (first time only)
poetry install

# Run all tests with verbose output
poetry run pytest -v

# Run only unit tests
poetry run pytest tests/unit -v

# Run only integration tests
poetry run pytest tests/integration -v
```

Expected output:

```
29 passed in ~0.3s
```

---

## Manual testing with curl

### Search for a direct flight

```bash
curl "http://localhost:8000/journeys/search?date=2026-06-12&from=BUE&to=PMI"
```

### Search for a journey with a layover

```bash
curl "http://localhost:8000/journeys/search?date=2026-06-12&from=BUE&to=MAD"
```

### Search with multiple intermediate cities

```bash
curl "http://localhost:8000/journeys/search?date=2026-06-12&from=GRU&to=PMI"
```

### Search that returns no results

```bash
curl "http://localhost:8000/journeys/search?date=2026-06-12&from=BUE&to=NYC"
```

### Trigger a 400 — same origin and destination

```bash
curl "http://localhost:8000/journeys/search?date=2026-06-12&from=BUE&to=BUE"
```

### Trigger a 422 — missing parameter

```bash
curl "http://localhost:8000/journeys/search?from=BUE&to=PMI"
```

### Inspect raw flight events (stub)

```bash
curl "http://localhost:8001/flight-events"
```

---

## Environment variables (journeys-api)

| Variable | Default | Description |
|---|---|---|
| `FLIGHT_EVENTS_API_URL` | `http://localhost:8001` | Base URL of the flight events service |
| `REDIS_URL` | `redis://localhost:6379` | Redis connection string |
| `CACHE_TTL` | `3600` | Cache time-to-live in seconds |

These are set automatically when running via Docker Compose. Override them in a `.env` file inside `journeys-api/` for local development without Docker.

---

## Project structure

```
flights-api/
├── journeys-api/          # Journey search API
│   ├── app/
│   │   ├── main.py        # FastAPI app + lifespan + exception handlers
│   │   ├── config.py      # Settings from environment variables
│   │   ├── exceptions.py  # Custom exception classes
│   │   ├── api/routes/
│   │   │   └── journeys.py
│   │   ├── services/
│   │   │   ├── flight_events.py   # Fetch + Redis cache + index
│   │   │   └── journey_search.py  # Bidirectional search algorithm
│   │   └── models/
│   │       ├── flight_event.py
│   │       └── journey.py
│   ├── tests/
│   │   ├── unit/          # Algorithm tests (no I/O)
│   │   └── integration/   # Endpoint tests (fakeredis + mocked API)
│   ├── pyproject.toml
│   └── README.md          # Algorithm deep-dive
├── flight-events-api/     # Flight events stub
│   ├── app/main.py
│   ├── data.json
│   └── pyproject.toml
├── docker-compose.yml
└── README.md              # This file
```
