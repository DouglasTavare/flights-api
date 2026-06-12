from pydantic import BaseModel


class JourneyLeg(BaseModel):
    flight_number: str
    from_: str
    to: str
    departure_time: str
    arrival_time: str

    model_config = {"populate_by_name": True}

    def model_dump(self, **kwargs):
        data = super().model_dump(**kwargs)
        data["from"] = data.pop("from_")
        return data


class Journey(BaseModel):
    connections: int
    path: list[JourneyLeg]

    def model_dump(self, **kwargs):
        return {
            "connections": self.connections,
            "path": [leg.model_dump(**kwargs) for leg in self.path],
        }
