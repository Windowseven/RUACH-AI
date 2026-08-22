from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="RUACH_")

    app_name: str = "RUACH"
    host: str = "127.0.0.1"
    port: int = 8018


@lru_cache
def get_settings() -> Settings:
    return Settings()
