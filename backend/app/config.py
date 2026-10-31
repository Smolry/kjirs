from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Wind Forecast Decision Monitor"
    elexon_base_url: str = "https://data.elexon.co.uk/bmrs/api/v1"
    # Decision dates (the day the purchase is made). Delivery is the following day.
    decision_start_date: str = "2026-01-01"
    decision_end_date: str = "2026-01-31"
    # Default decision time (UK local, HH:MM): EPEX GB day-ahead gate closure.
    decision_cutoff: str = "09:20"
    cache_mode: str = "memory"
    cache_dir: str = "./data/cache"
    cache_ttl_seconds: int = 21600
    cors_origins: str = "http://localhost:5173"
    http_timeout_seconds: float = 30.0

    @property
    def allowed_origins(self) -> list[str]:
        return [x.strip() for x in self.cors_origins.split(",") if x.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
