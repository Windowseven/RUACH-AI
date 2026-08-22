"""Configuration generation (ARCH-009 §33).

Turns setup results into the exact RUACH_* keys backend settings already
understand. Pure string building plus atomic file write; nothing here knows
about llama.cpp beyond the key names.
"""

import os
from pathlib import Path


def build_env_content(entries: dict[str, str]) -> str:
    lines = [f"{key}={value}" for key, value in sorted(entries.items())]
    return "\n".join(lines) + "\n"


def write_env(path: Path, entries: dict[str, str]) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(build_env_content(entries), encoding="utf-8")
    os.replace(tmp_path, path)
    return path


def env_entries_for_model(
    runtime_id: str,
    model_name: str,
    model_path: Path,
    server_url: str,
    timeout_seconds: float,
) -> dict[str, str]:
    return {
        "RUACH_MODEL_RUNTIME": runtime_id,
        "RUACH_MODEL_NAME": model_name,
        "RUACH_MODEL_PATH": str(model_path),
        "RUACH_MODEL_SERVER_URL": server_url,
        "RUACH_INFERENCE_TIMEOUT_SECONDS": str(timeout_seconds),
    }
