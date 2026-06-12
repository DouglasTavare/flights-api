# flights-api

Monorepo containing two services:

| Service | Responsibility | Port |
|---|---|---|
| `journeys-api` | Searches and combines flight journeys | 8000 |
| `flight-events-api` | Stub repository of individual flight events | 8001 |

---

## How it works

The `journeys-api` exposes a single endpoint:

```
GET /journeys/search?date=YYYY-MM-DD&from=XXX&to=XXX
```

It fetches all flight events from `flight-events-api`, caches them in Redis (scoped by date), and runs a bidirectional search algorithm to find all valid journeys — direct or with one layover — that satisfy:

- Departure on the requested date (UTC)
- Total journey duration ≤ 24 hours
- Layover time between segments: 0 < wait ≤ 4 hours

### Search algorithm

A nested loop iterating over all `(first_leg, second_leg)` pairs has **O(N²)** complexity. As the number of flight events grows, the cost grows quadratically — checking pairs that will never produce a valid result.

The algorithm avoids this by reducing candidates at each step before any pairing happens, combining three techniques: **pre-indexing**, **bidirectional filtering**, and **binary search**.

**Step 1 — Pre-indexing** (O(N log N), done once at cache load)

Events are organized into two sorted dictionaries:
```
departures[city] → events departing from city, sorted by departure_datetime
arrivals[city]   → events arriving at city,   sorted by departure_datetime
```

**Step 2 — Filter cheapest constraints first**

```
R1: first_legs  = departures[origin]      WHERE departure_date == date
R3: second_legs = arrivals[destination]   WHERE arrival <= earliest_departure + 24h
```

**Step 3 — Bidirectional intersection**

Rather than expanding blindly from the origin, the algorithm constrains from both ends simultaneously:

```
intermediate_cities = { f.arrival_city   for f in first_legs  }
                    ∩ { s.departure_city  for s in second_legs }
```

Only cities reachable from the origin **and** with a flight to the destination survive.

```mermaid
flowchart TD
    input["Query: BUE → PMI on 2026-06-12"]

    subgraph left ["Left side — departures from BUE (R1)"]
        L1["XX1234  BUE→MAD  12:00→00:00"]
        L2["XX4567  BUE→GRU  10:00→12:00"]
        L3["XX7890  BUE→LIS  14:00→03:00"]
        L4["XX9000  BUE→PMI  08:00→06:00"]
    end

    subgraph right ["Right side — arrivals at PMI within 24h (R3)"]
        R1["XX2345  MAD→PMI  02:00→03:00"]
        R2["XX3456  MAD→PMI  05:30→06:30"]
        R3["XX8901  LIS→PMI  05:00→06:30"]
        R4["XX9000  BUE→PMI  08:00→06:00"]
    end

    input --> left
    input --> right

    subgraph intersection ["Intersection — valid intermediate cities"]
        MAD["MAD"]
        LIS["LIS"]
        DIRECT["direct: BUE→PMI"]
    end

    L1 -->|"arrival_city = MAD"| MAD
    L3 -->|"arrival_city = LIS"| LIS
    L4 -->|"arrival_city = PMI = destination"| DIRECT
    R4 -->|"same flight as L4"| DIRECT
    R1 -->|"departure_city = MAD"| MAD
    R2 -->|"departure_city = MAD"| MAD
    R3 -->|"departure_city = LIS"| LIS
    L2 -->|"arrival_city = GRU — not in right side"| discarded["discarded"]

    subgraph bsearch ["Binary search per first_leg — connection window R2"]
        BS1_valid["XX1234 + XX2345\narrival 00:00 → departure 02:00\nwait = 2h ≤ 4h ✓"]
        BS1_invalid["XX1234 + XX3456\narrival 00:00 → departure 05:30\nwait = 5h30 > 4h ✗ discarded"]
        BS2["XX7890 + XX8901\narrival 03:00 → departure 05:00\nwait = 2h ≤ 4h ✓"]
    end

    MAD --> BS1_valid
    MAD --> BS1_invalid
    LIS --> BS2

    subgraph results ["Results"]
        J1["connections: 0 — XX9000 BUE→PMI"]
        J2["connections: 1 — XX1234 BUE→MAD + XX2345 MAD→PMI"]
        J4["connections: 1 — XX7890 BUE→LIS + XX8901 LIS→PMI"]
    end

    DIRECT --> J1
    BS1_valid --> J2
    BS2 --> J4
```

**Step 4 — Binary search for the connection window (R2)**

For each surviving `first_leg`, `bisect.bisect_right` locates the first valid `second_leg` in O(log k) instead of scanning from the beginning. Iteration stops as soon as `departure_datetime > arrival + 4h`.

**Complexity summary**

| Phase | Cost |
|---|---|
| Build index + sort | O(N log N) — once per cache TTL |
| Filter first legs (R1) | O(F) |
| Filter second legs (R3) | O(S) |
| Bidirectional intersection | O(F + S) |
| Binary search per first leg (R2) | O(F · log k) |
| **Total per search** | **O(F · log k + results)** |

For a detailed walkthrough see [`journeys-api/README.md`](journeys-api/README.md).

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

---

## Manual testing with curl

```bash
# Direct flight
curl "http://localhost:8000/journeys/search?date=2026-06-12&from=BUE&to=PMI"

# Journey with layover
curl "http://localhost:8000/journeys/search?date=2026-06-12&from=BUE&to=MAD"

# Multiple intermediate cities
curl "http://localhost:8000/journeys/search?date=2026-06-12&from=GRU&to=PMI"

# No results
curl "http://localhost:8000/journeys/search?date=2026-06-12&from=BUE&to=NYC"

# 400 — same origin and destination
curl "http://localhost:8000/journeys/search?date=2026-06-12&from=BUE&to=BUE"

# 422 — missing parameter
curl "http://localhost:8000/journeys/search?from=BUE&to=PMI"

# Raw flight events (stub)
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
│   │   ├── logger.py      # Structured JSON logging
│   │   ├── api/routes/
│   │   │   ├── journeys.py
│   │   │   └── health.py
│   │   ├── services/
│   │   │   ├── flight_events.py   # Fetch + Redis cache + index
│   │   │   └── journey_search.py  # Bidirectional search algorithm
│   │   └── models/
│   │       ├── flight_event.py
│   │       └── journey.py
│   ├── tests/
│   │   ├── unit/          # Algorithm tests (no I/O)
│   │   ├── integration/   # Endpoint tests (fakeredis + mocked API)
│   │   └── e2e/           # Full stack tests (requires docker compose up)
│   ├── pyproject.toml
│   └── README.md          # Algorithm deep-dive
├── flight-events-api/     # Flight events stub
│   ├── app/main.py
│   ├── data.json
│   └── pyproject.toml
├── docker-compose.yml
├── flights-api.postman_collection.json
└── README.md              # This file
```
