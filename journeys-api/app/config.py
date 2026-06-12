from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    flight_events_api_url: str = "http://localhost:8001"
    redis_url: str = "redis://localhost:6379"
    cache_ttl: int = 3600

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
