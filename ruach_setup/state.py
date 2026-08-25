"""Setup installation state (v2).

Tracks pipeline progress in ~/.ruach/setup_state.json so `./ruach setup`
can resume after interruption and stay idempotent across reruns.

New state machine (v2):
  NEW → DISCOVERING → PLANNED → INSTALLING → VERIFYING → READY
                                                         → DEGRADED
                                                         → BLOCKED
                                        any stage  → FAILED

Backward compatible: old stage names (not_initialized, environment_ready,
etc.) are mapped to v2 equivalents on load.
"""

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

STAGES = (
    "new",
    "discovering",
    "planned",
    "installing",
    "verifying",
    "ready",
    "degraded",
    "blocked",
)
_STAGE_ORDER = {name: index for index, name in enumerate(STAGES)}

# Backward compatibility: map old stage names to v2
_OLD_TO_NEW: dict[str, str] = {
    "not_initialized": "new",
    "environment_ready": "discovering",
    "runtime_installed": "installing",
    "model_installed": "installing",
    "configured": "verifying",
    "healthy": "ready",
}


class SetupStateError(Exception):
    """Invalid stage transition or corrupt state file."""


@dataclass
class SetupState:
    stage: str = "new"
    profile: str | None = None  # RuntimeProfile value
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
        # Backward compatibility: map old stage names
        stage = _OLD_TO_NEW.get(stage, stage)
        if stage not in _STAGE_ORDER:
            raise SetupStateError(f"Unknown stage: {stage}")
        current = _STAGE_ORDER.get(self.stage, 0) if self.stage != "failed" else 0
        target = _STAGE_ORDER[stage]
        if self.stage == "failed":
            if target != 0:
                raise SetupStateError(
                    "Cannot resume from failed state except to new"
                )
        elif target < current:
            raise SetupStateError(
                f"Cannot move backwards from '{self.stage}' to '{stage}'"
            )
        self.stage = stage
        for key, value in fields.items():
            setattr(self, key, value)

    @property
    def is_terminal(self) -> bool:
        return self.stage in ("ready", "degraded", "blocked", "failed")

    @property
    def completed_stages(self) -> list[str]:
        """Stages that have been successfully completed."""
        if self.stage == "failed":
            return []
        idx = _STAGE_ORDER.get(self.stage, 0)
        return [s for s in STAGES[:idx] if s not in ("ready", "degraded", "blocked")]

    @property
    def remaining_stages(self) -> list[str]:
        """Stages yet to be completed."""
        if self.stage in ("ready", "degraded", "blocked", "failed"):
            return []
        idx = _STAGE_ORDER.get(self.stage, 0)
        return [s for s in STAGES[idx:] if s not in ("ready", "degraded", "blocked")]


def load_state(path: Path) -> SetupState:
    """Load state; a missing or empty file yields a fresh NEW state.

    Old stage names are mapped to v2 equivalents for backward compatibility.
    """
    if not path.is_file():
        return SetupState()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        stage = raw["stage"]
        # Backward compatibility: map old stage names
        stage = _OLD_TO_NEW.get(stage, stage)
        return SetupState(
            stage=stage,
            profile=raw.get("profile"),
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
                "profile": state.profile,
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
