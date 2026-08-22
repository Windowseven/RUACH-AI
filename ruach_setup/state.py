"""Setup installation state (ARCH-009 §46).

Tracks pipeline progress in ~/.ruach/setup_state.json so `./ruach setup`
can resume after interruption and stay idempotent across reruns.

Platform-independent: pure JSON file handling with atomic writes. The path
is always injected, so tests use temporary directories.
"""

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

STAGES = (
    "not_initialized",
    "environment_ready",
    "runtime_installed",
    "model_installed",
    "configured",
    "healthy",
)
_STAGE_ORDER = {name: index for index, name in enumerate(STAGES)}


class SetupStateError(Exception):
    """Invalid stage transition or corrupt state file."""


@dataclass
class SetupState:
    stage: str = "not_initialized"
    runtime_id: str | None = None
    runtime_version: str | None = None
    model_id: str | None = None
    model_sha256: str | None = None
    last_error: str | None = None
    extras: dict[str, str] = field(default_factory=dict)

    def mark(self, stage: str, **fields: str | None) -> None:
        if stage == "failed":
            self.stage = "failed"
            for key, value in fields.items():
                setattr(self, key, value)
            return
        if stage not in _STAGE_ORDER:
            raise SetupStateError(f"Unknown stage: {stage}")
        current = _STAGE_ORDER[self.stage] if self.stage != "failed" else 0
        target = _STAGE_ORDER[stage]
        if self.stage == "failed":
            if target != 1:
                raise SetupStateError("Cannot resume from failed state except to environment_ready")
        elif target < current:
            raise SetupStateError(f"Cannot move backwards from '{self.stage}' to '{stage}'")
        self.stage = stage
        for key, value in fields.items():
            setattr(self, key, value)


def load_state(path: Path) -> SetupState:
    """Load state; a missing or empty file yields a fresh NOT_INITIALIZED state."""
    if not path.is_file():
        return SetupState()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return SetupState(
            stage=raw["stage"],
            runtime_id=raw.get("runtime_id"),
            runtime_version=raw.get("runtime_version"),
            model_id=raw.get("model_id"),
            model_sha256=raw.get("model_sha256"),
            last_error=raw.get("last_error"),
            extras=dict(raw.get("extras", {})),
        )
    except (ValueError, KeyError, TypeError) as error:
        raise SetupStateError(f"Corrupt setup state at {path}: {error}") from error


def save_state(state: SetupState, path: Path) -> None:
    """Atomically persist state: write sibling temp file, then rename over target."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(
        json.dumps(
            {
                "stage": state.stage,
                "runtime_id": state.runtime_id,
                "runtime_version": state.runtime_version,
                "model_id": state.model_id,
                "model_sha256": state.model_sha256,
                "last_error": state.last_error,
                "extras": state.extras,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    os.replace(tmp_path, path)
