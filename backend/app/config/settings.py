from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_database_url() -> str:
    return f"sqlite:///{Path.home() / '.ruach' / 'data' / 'ruach.db'}"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="RUACH_")

    app_name: str = "RUACH"
    host: str = "127.0.0.1"
    port: int = 8018
    database_url: str = Field(default_factory=_default_database_url)


@lru_cache
def get_settings() -> Settings:
    return Settings()
