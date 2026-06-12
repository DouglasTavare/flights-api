from datetime import datetime

from pydantic import BaseModel, field_validator


class FlightEvent(BaseModel):
    flight_number: str
    departure_city: str
    arrival_city: str
    departure_datetime: datetime
    arrival_datetime: datetime

    @field_validator("departure_datetime", "arrival_datetime", mode="before")
    @classmethod
    def parse_datetime(cls, v: str | datetime) -> datetime:
        if isinstance(v, datetime):
            return v
        return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
