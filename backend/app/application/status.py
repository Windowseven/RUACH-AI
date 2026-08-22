from importlib import metadata
from typing import Literal

RUACH_PACKAGE_NAME = "ruach-backend"
API_VERSION = "v1"

ComponentState = Literal["available", "unavailable"]


def inference_state() -> ComponentState:
    return "unavailable"


def database_state() -> ComponentState:
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
