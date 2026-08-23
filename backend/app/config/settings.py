from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_database_url() -> str:
    return f"sqlite:///{Path.home() / '.ruach' / 'data' / 'ruach.db'}"


def _default_workspace_path() -> Path:
    return Path.home() / ".ruach" / "workspace"


def _default_audit_log_path() -> Path:
    return Path.home() / ".ruach" / "data" / "audit.jsonl"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="RUACH_")

    app_name: str = "RUACH"
    host: str = "127.0.0.1"
    port: int = 8018
    database_url: str = Field(default_factory=_default_database_url)
    model_runtime: str = "llama_cpp"
    model_name: str = "qwen3"
    model_path: str = ""
    model_server_url: str = "http://127.0.0.1:8080"
    inference_timeout_seconds: float = 120.0
    workspace_path: Path = Field(default_factory=_default_workspace_path)
    audit_log_path: Path = Field(default_factory=_default_audit_log_path)


@lru_cache
def get_settings() -> Settings:
    return Settings()
