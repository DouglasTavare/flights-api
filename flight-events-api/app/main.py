import json
from pathlib import Path

from fastapi import FastAPI

app = FastAPI(title="Flight Events API", version="0.0.1")

_data_path = Path(__file__).parent.parent / "data.json"
_flight_events: list = json.loads(_data_path.read_text())


@app.get("/flight-events")
def get_flight_events() -> list:
    return _flight_events
