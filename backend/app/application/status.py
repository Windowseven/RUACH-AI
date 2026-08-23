from importlib import metadata
from typing import Literal
from urllib.error import URLError
from urllib.request import urlopen

from sqlalchemy import text

from app.config.settings import get_settings
from app.infrastructure.db import create_session_factory

RUACH_PACKAGE_NAME = "ruach-backend"
API_VERSION = "v1"

ComponentState = Literal["available", "unavailable"]


def inference_state() -> ComponentState:
    settings = get_settings()
    if settings.model_runtime == "stub":
        return "available"
    health_url = settings.model_server_url.rstrip("/") + "/health"
    try:
        with urlopen(health_url, timeout=1.5) as response:
            return "available" if response.status == 200 else "unavailable"
    except (URLError, OSError, ValueError):
        return "unavailable"


def database_state() -> ComponentState:
    try:
        session = create_session_factory(get_settings().database_url)()
        try:
            session.execute(text("SELECT 1"))
            return "available"
        finally:
            session.close()
    except Exception:  # noqa: BLE001 - status probes must never raise
        return "unavailable"


def overall_status(
    inference: str,
    database: str,
) -> Literal["ready", "not_ready", "degraded"]:
    if inference == "available" and database == "available":
        return "ready"
    return "not_ready"


def package_version() -> str:
    try:
        return metadata.version(RUACH_PACKAGE_NAME)
    except metadata.PackageNotFoundError:
        return "unknown"
