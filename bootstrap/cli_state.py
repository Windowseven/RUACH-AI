"""CLI state resolution (docs/12 P16 §3/§16).

Reads ACTUAL persisted/config/runtime state — setup_state.json, generated
config, pid/lifecycle files, database presence — and maps it onto the
product state model. Coarse signals only: `./ruach doctor` remains the
authoritative deep diagnostic; this layer decides WHICH experience the
entrypoint shows.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from bootstrap.runtime import (
    DEFAULT_RUN_DIR,
    load_config,
    merged_environment,
)
from bootstrap.runtime import (
    status as runtime_status,
)
from bootstrap.runtime_resolver import (
    configured_binary_override,
    resolve_llama_server,
)

SETUP_COMPLETE_STAGES = {"configured", "healthy", "verifying", "ready", "degraded", "blocked"}


class CliState(str, Enum):
    FIRST_RUN = "FIRST_RUN"
    SETUP_INCOMPLETE = "SETUP_INCOMPLETE"
    READY = "READY"
    RUNNING = "RUNNING"
    DEGRADED = "DEGRADED"
    ERROR = "ERROR"


@dataclass
class ResolvedCliState:
    state: CliState
    reasons: list[str] = field(default_factory=list)
    setup_stage: str | None = None
    base_url: str | None = None
    # Tri-state health signals: True/False measured, None = not assessed.
    config_present: bool | None = None
    model_ok: bool | None = None
    binary_ok: bool | None = None
    db_ready: bool | None = None

    @property
    def recommendation(self) -> str:
        if self.state is CliState.FIRST_RUN:
            return "./ruach setup"
        if self.state is CliState.SETUP_INCOMPLETE:
            return "./ruach setup   # resumes where it left off"
        if self.state is CliState.DEGRADED:
            return "./ruach doctor"
        if self.state is CliState.ERROR:
            return "./ruach doctor"
        return ""


def _db_ready(home: Path) -> bool:
    db_path = home / ".ruach" / "data" / "ruach.db"
    if not db_path.is_file():
        return False
    try:
        import sqlite3

        connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            rows = connection.execute("select count(*) from alembic_version").fetchone()
        finally:
            connection.close()
        return bool(rows and rows[0] >= 1)
    except Exception:  # noqa: BLE001 - unreadable db is a degraded signal
        return False


def _model_ok(env: dict[str, str]) -> tuple[bool, str]:
    runtime_kind = env.get("RUACH_MODEL_RUNTIME", "llama_cpp")
    if runtime_kind == "stub":
        return True, ""
    raw = env.get("RUACH_MODEL_PATH", "").strip()
    if not raw:
        return False, "no model path configured"
    path = Path(raw).expanduser()
    if not path.is_file():
        return False, f"model file missing: {path}"
    return True, ""


def resolve_state(
    *,
    home: Path | None = None,
    config_path: Path | None = None,
    run_dir: Path = DEFAULT_RUN_DIR,
) -> ResolvedCliState:
    home = home if home is not None else Path.home()
    if config_path is None:
        config_path = home / ".ruach" / "config" / "ruach.env"

    # 1) RUNNING wins: never offer a second start over a live instance.
    info = runtime_status(run_dir)
    backend_raw = info.get("backend", {}) if isinstance(info, dict) else {}
    lifecycle_raw = info.get("lifecycle", {}) if isinstance(info, dict) else {}
    backend = backend_raw if isinstance(backend_raw, dict) else {}
    lifecycle = lifecycle_raw if isinstance(lifecycle_raw, dict) else {}
    base_url_value = lifecycle.get("base_url", "")
    base_url = str(base_url_value).strip() or None
    if backend.get("running"):
        config_present = (config_path).is_file()
        if lifecycle.get("state") == "UNRESPONSIVE":
            return ResolvedCliState(
                state=CliState.DEGRADED,
                reasons=[
                    "A RUACH process is running but not answering readiness checks."
                ],
                base_url=base_url,
                config_present=config_present,
            )
        return ResolvedCliState(
            state=CliState.RUNNING, base_url=base_url, config_present=config_present
        )

    ruach_root = home / ".ruach"

    # 2) FIRST_RUN: nothing persisted yet.
    if not ruach_root.exists():
        return ResolvedCliState(state=CliState.FIRST_RUN)

    # 3) SETUP_INCOMPLETE: pipeline started but did not finish (resume).
    state_file = ruach_root / "setup_state.json"
    setup_stage: str | None = None
    if state_file.is_file():
        try:
            from ruach_setup.state import load_state

            setup_stage = load_state(state_file).stage
        except Exception as error:  # noqa: BLE001 - corrupt state is recoverable
            return ResolvedCliState(
                state=CliState.ERROR,
                reasons=[f"Setup state file is unreadable: {error}"],
            )
        if setup_stage not in SETUP_COMPLETE_STAGES:
            return ResolvedCliState(
                state=CliState.SETUP_INCOMPLETE,
                setup_stage=setup_stage,
                config_present=config_path.is_file(),
            )

    # 4) Configured world: verify coarse health signals.
    config_present = config_path.is_file() or bool(_user_env_config(home))
    env: dict[str, str] = {}
    effective_config = config_path if config_path.is_file() else _user_env_config(home)
    if effective_config is not None:
        try:
            env = merged_environment(load_config(effective_config))
        except Exception as error:  # noqa: BLE001
            return ResolvedCliState(
                state=CliState.ERROR,
                reasons=[f"Generated config could not be read: {error}"],
            )

    reasons: list[str] = []
    model_ok, model_reason = _model_ok(env)
    binary_ok = resolve_llama_server(
        explicit=configured_binary_override(env), home=home
    ).found
    db_ok = _db_ready(home)

    if not config_present:
        reasons.append("No generated configuration found.")
    if not model_ok:
        reasons.append(model_reason or "Model artifact unavailable.")
    if not binary_ok:
        reasons.append(
            "llama-server binary not found (searched config, ~/.ruach/runtime/, "
            "project .build/runtime/, PATH)."
        )
    if not db_ok:
        reasons.append("Database not initialized at ~/.ruach/data/ruach.db.")

    if not reasons:
        return ResolvedCliState(
            state=CliState.READY,
            config_present=config_present,
            model_ok=model_ok,
            binary_ok=binary_ok,
            db_ready=db_ok,
            setup_stage=setup_stage,
        )

    # A configured-but-unfinished environment is a resume case; everything
    # else is degradation of an otherwise-complete install.
    if not config_present or (setup_stage is not None):
        return ResolvedCliState(
            state=CliState.SETUP_INCOMPLETE,
            setup_stage=setup_stage,
            reasons=reasons,
            config_present=config_present,
            model_ok=model_ok,
            binary_ok=binary_ok,
            db_ready=db_ok,
        )
    return ResolvedCliState(
        state=CliState.DEGRADED,
        reasons=reasons,
        config_present=config_present,
        model_ok=model_ok,
        binary_ok=binary_ok,
        db_ready=db_ok,
    )


def _user_env_config(home: Path) -> Path | None:
    candidate = home / ".ruach" / "config" / "ruach.env"
    return candidate if candidate.is_file() else None
