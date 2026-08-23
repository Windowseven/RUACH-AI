"""Runtime bring-up for `ruach start` (roadmap row 11, P12 §9–§10).

Loads the generated env config (~/.ruach/config/ruach.env), resolves the
model runtime through RuntimeResolver (no hardcoded paths), spawns it
when configured, launches uvicorn serving UI+API, and verifies readiness
HONESTLY:

- llama-server /health can report ok while the model is still loading,
  so inference readiness is proven by a real one-token completion.
- backend readiness is the same endpoint the boot screen uses
  (GET /api/v1/ready -> data.status == "ready"), not a bare TCP check.

Process lifecycle (P12 §9): a lifecycle state file records
STARTING -> HEALTHY -> STOPPING -> STOPPED / FAILED transitions; `status`
combines that with live PID liveness and an HTTP probe. PIDs are never
trusted as proof of health — environments exist where processes can be
terminated unexpectedly.

Timeouts (P12 §10): defaults are DEVELOPMENT-HOST values, tunable via
RUACH_MODEL_READY_TIMEOUT_SECONDS / RUACH_BACKEND_READY_TIMEOUT_SECONDS.
Target-device defaults will be set from real benchmarks later — they are
NOT guessed here.

Stdlib-only.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path
from urllib.parse import urlsplit

from bootstrap.runtime_resolver import (
    configured_binary_override,
    resolve_llama_server,
)

ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = ROOT / "backend"
DEFAULT_CONFIG_PATH = Path.home() / ".ruach" / "config" / "ruach.env"
DEFAULT_RUN_DIR = Path.home() / ".ruach" / "run"

# Development-host defaults; benchmark-derived target defaults come later.
INFERENCE_READY_TIMEOUT = 180.0
BACKEND_READY_TIMEOUT = 60.0


def _timeout(env: dict[str, str], key: str, default: float) -> float:
    try:
        value = float(env.get(key, ""))
        return value if value > 0 else default
    except ValueError:
        return default


class StartError(RuntimeError):
    """Raised with an actionable message when bring-up cannot proceed."""


class AlreadyRunning(StartError):
    pass


# ------------------------------------------------------------------ config


def parse_env_file(text: str) -> dict[str, str]:
    entries: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        entries[key] = value
    return entries


def load_config(config_path: Path) -> dict[str, str]:
    if not config_path.is_file():
        return {}
    return parse_env_file(config_path.read_text(encoding="utf-8"))


def merged_environment(config: dict[str, str]) -> dict[str, str]:
    """Generated file fills gaps; variables already in the environment win."""
    env = dict(os.environ)
    for key, value in config.items():
        env.setdefault(key, value)
    return env


def port_of(server_url: str) -> int:
    port = urlsplit(server_url).port
    if port is None:
        raise StartError(f"RUACH_MODEL_SERVER_URL has no explicit port: {server_url}")
    return port


# ------------------------------------------------------------- readiness


def _http_json(url: str, timeout: float, payload: dict | None = None) -> tuple[int, dict | None]:
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"} if data else {},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read()
            status_code = response.status
    except urllib.error.HTTPError as error:
        return error.code, None
    except (urllib.error.URLError, OSError):
        return 0, None  # not up yet / refused / reset: keep polling
    try:
        return status_code, json.loads(body)  # type: ignore[arg-type]
    except ValueError:
        return status_code, None


def wait_for_inference(base_url: str, timeout: float, clock=time.monotonic) -> bool:
    """True only when the model server completes a real one-token request.

    A bare /health poll lies during model load; this does not.
    """
    deadline = clock() + timeout
    while clock() < deadline:
        code, body = _http_json(
            f"{base_url.rstrip('/')}/v1/chat/completions",
            timeout=5.0,
            payload={
                "max_tokens": 1,
                "messages": [{"role": "user", "content": "ping"}],
            },
        )
        if code == 200 and isinstance(body, dict):
            choices = body.get("choices")
            if isinstance(choices, list) and choices:
                return True
        time.sleep(min(1.0, max(0.05, deadline - clock())))
    return False


def wait_for_backend(base_url: str, timeout: float, clock=time.monotonic) -> bool:
    """Same honesty contract as the boot screen: /ready must say ready."""
    deadline = clock() + timeout
    while clock() < deadline:
        code, body = _http_json(f"{base_url.rstrip('/')}/api/v1/ready", timeout=5.0)
        if code == 200 and isinstance(body, dict):
            data = body.get("data")
            if isinstance(data, dict) and data.get("status") == "ready":
                return True
        time.sleep(min(1.0, max(0.05, deadline - clock())))
    return False


# ----------------------------------------------------------------- pids


def _pid_path(run_dir: Path, name: str) -> Path:
    return run_dir / f"{name}.pid"


def _write_pid(run_dir: Path, name: str, pid: int) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    _pid_path(run_dir, name).write_text(str(pid), encoding="utf-8")


def read_pid(run_dir: Path, name: str) -> int | None:
    path = _pid_path(run_dir, name)
    if not path.is_file():
        return None
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except ValueError:
        return None


def _alive(pid: int | None) -> bool:
    if pid is None or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def clear_pid(run_dir: Path, name: str) -> None:
    _pid_path(run_dir, name).unlink(missing_ok=True)


# ------------------------------------------------------------- lifecycle

LIFECYCLE_STATES = ("STARTING", "HEALTHY", "STOPPING", "STOPPED", "FAILED")


def set_lifecycle(
    run_dir: Path,
    state: str,
    detail: str = "",
    *,
    base_url: str | None = None,
) -> None:
    if state not in LIFECYCLE_STATES:
        raise ValueError(f"unknown lifecycle state: {state}")
    run_dir.mkdir(parents=True, exist_ok=True)
    payload = {"state": state, "detail": detail}
    if base_url is not None:
        payload["base_url"] = base_url
    previous = read_lifecycle(run_dir)
    if not base_url and previous.get("base_url"):
        payload["base_url"] = previous["base_url"]
    payload["at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    (run_dir / "state.json").write_text(json.dumps(payload), encoding="utf-8")


def read_lifecycle(run_dir: Path) -> dict[str, str]:
    path = run_dir / "state.json"
    if not path.is_file():
        return {"state": "STOPPED", "detail": "never started here", "at": "", "base_url": ""}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return {"state": "STOPPED", "detail": "unreadable state file", "at": "", "base_url": ""}
    return {
        "state": str(data.get("state", "STOPPED")),
        "detail": str(data.get("detail", "")),
        "at": str(data.get("at", "")),
        "base_url": str(data.get("base_url", "")),
    }


# ----------------------------------------------------------------- stack


def _migrate(env: dict[str, str]) -> None:
    """Idempotent `alembic upgrade head` — the ONLY sanctioned schema path.

    The backend refuses to boot on an unmigrated database by design (P5);
    a fresh install therefore migrates here, from source-controlled
    migrations. Never create_all.
    """
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "-c",
            str(BACKEND_DIR / "alembic.ini"),
            "upgrade",
            "head",
        ],
        cwd=str(BACKEND_DIR),
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise StartError(f"Migration failed:\n{result.stderr[-800:]}")


class RuntimeStack:
    def __init__(
        self,
        backend: subprocess.Popen,
        model_server: subprocess.Popen | None,
        base_url: str,
        run_dir: Path,
    ) -> None:
        self.backend = backend
        self.model_server = model_server
        self.base_url = base_url
        self.run_dir = run_dir

    @property
    def ui_url(self) -> str:
        return self.base_url + "/"

    def shutdown(self) -> None:
        for proc in (self.backend, self.model_server):
            if proc is None or proc.poll() is not None:
                continue
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
        clear_pid(self.run_dir, "backend")
        clear_pid(self.run_dir, "model_server")


def start(
    *,
    config_path: Path = DEFAULT_CONFIG_PATH,
    run_dir: Path = DEFAULT_RUN_DIR,
    backend_port: int | None = None,
    stub: bool = False,
    browser: bool = True,
    extra_env: dict[str, str] | None = None,
    echo=print,
) -> RuntimeStack:
    """Bring up the full local stack; returns once the backend says ready."""
    existing = read_pid(run_dir, "backend")
    if _alive(existing):
        raise AlreadyRunning(
            f"RUACH backend already running (pid {existing}). Use `ruach stop` first."
        )

    env = merged_environment(load_config(config_path))
    if extra_env:
        env.update(extra_env)

    _migrate(env)

    runtime = env.get("RUACH_MODEL_RUNTIME", "llama_cpp")
    model_server: subprocess.Popen | None = None

    if stub:
        env["RUACH_MODEL_RUNTIME"] = "stub"
        runtime = "stub"

    if runtime == "llama_cpp":
        model_path = Path(env.get("RUACH_MODEL_PATH", ""))
        if not model_path.is_file():
            raise StartError(
                f"Model file not found: {model_path}. Run `./ruach setup --install-model`."
            )
        resolved = resolve_llama_server(
            explicit=configured_binary_override(env),
            project_root=ROOT,
        )
        if not resolved.found:
            raise StartError(
                "llama-server binary not found. Searched: RUACH_LLAMA_SERVER_BIN, "
                "~/.ruach/runtime/, .build/runtime/, PATH. "
                "Build llama.cpp or set RUACH_LLAMA_SERVER_BIN (docs/12 Priority 8)."
            )
        server_port = port_of(env.get("RUACH_MODEL_SERVER_URL", "http://127.0.0.1:8080"))
        run_dir.mkdir(parents=True, exist_ok=True)
        model_log = open(run_dir / "model_server.log", "ab")
        echo(
            f"[start] model runtime : llama-server on 127.0.0.1:{server_port} "
            f"(resolved: {resolved.source})"
        )
        echo(f"[start] model         : {model_path.name} (loading; honest readiness probe)")
        model_server = subprocess.Popen(
            [
                str(resolved.path),
                "-m",
                str(model_path),
                "--host",
                "127.0.0.1",
                "--port",
                str(server_port),
                "--temp",
                env.get("RUACH_INFERENCE_TEMPERATURE", "0.2"),
            ],
            stdout=model_log,
            stderr=subprocess.STDOUT,
        )
        _write_pid(run_dir, "model_server", model_server.pid)
        if not wait_for_inference(
            env.get("RUACH_MODEL_SERVER_URL", "http://127.0.0.1:8080"),
            _timeout(env, "RUACH_MODEL_READY_TIMEOUT_SECONDS", INFERENCE_READY_TIMEOUT),
        ):
            model_server.terminate()
            clear_pid(run_dir, "model_server")
            raise StartError("Model runtime did not become ready within the timeout.")

    host = env.get("RUACH_HOST", "127.0.0.1")
    port = backend_port if backend_port is not None else int(env.get("RUACH_PORT", "8018"))
    base_url = f"http://{host}:{port}"

    run_dir.mkdir(parents=True, exist_ok=True)
    set_lifecycle(run_dir, "STARTING", base_url=base_url)
    backend_log = open(run_dir / "backend.log", "ab")
    echo(f"[start] backend       : uvicorn on {base_url}")
    backend = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            host,
            "--port",
            str(port),
        ],
        cwd=str(BACKEND_DIR),
        env={**env, "PYTHONUNBUFFERED": "1"},
        stdout=backend_log,
        stderr=subprocess.STDOUT,
    )
    _write_pid(run_dir, "backend", backend.pid)

    try:
        if not wait_for_backend(
            base_url,
            _timeout(env, "RUACH_BACKEND_READY_TIMEOUT_SECONDS", BACKEND_READY_TIMEOUT),
        ):
            set_lifecycle(run_dir, "FAILED", "backend never reported ready")
            raise StartError(
                f"Backend did not report ready within {BACKEND_READY_TIMEOUT:.0f}s. "
                f"See {run_dir / 'backend.log'}"
            )
    except BaseException:
        backend.terminate()
        clear_pid(run_dir, "backend")
        if model_server is not None:
            model_server.terminate()
            clear_pid(run_dir, "model_server")
        raise

    set_lifecycle(run_dir, "HEALTHY", base_url=base_url)

    if browser:
        try:
            webbrowser.open(base_url + "/")
        except Exception:  # noqa: BLE001 - headless boxes must not crash start
            echo("[start] could not open a browser automatically")

    return RuntimeStack(backend, model_server, base_url, run_dir)


# ------------------------------------------------------------ stop/status


def _terminate_by_pid(run_dir: Path, name: str) -> str:
    pid = read_pid(run_dir, name)
    if not _alive(pid):
        clear_pid(run_dir, name)
        return "stopped" if pid is None else "cleaned stale pid"
    assert pid is not None
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        clear_pid(run_dir, name)
        return "already gone"
    for _ in range(50):
        if not _alive(pid):
            break
        time.sleep(0.1)
    else:
        os.kill(pid, signal.SIGKILL)
    clear_pid(run_dir, name)
    return f"stopped (pid {pid})"


def stop(run_dir: Path = DEFAULT_RUN_DIR, echo=print) -> int:
    set_lifecycle(run_dir, "STOPPING")
    backend_state = _terminate_by_pid(run_dir, "backend")
    model_state = _terminate_by_pid(run_dir, "model_server")
    set_lifecycle(run_dir, "STOPPED")
    echo(f"[stop] backend      : {backend_state}")
    echo(f"[stop] model server : {model_state}")
    return 0


def record_failed(run_dir: Path, detail: str) -> None:
    set_lifecycle(run_dir, "FAILED", detail)


def status(run_dir: Path = DEFAULT_RUN_DIR) -> dict[str, object]:
    """Liveness + lifecycle. A live PID alone is NOT proof of health."""
    backend_pid = read_pid(run_dir, "backend")
    model_pid = read_pid(run_dir, "model_server")
    lifecycle = read_lifecycle(run_dir)
    state = str(lifecycle["state"])

    pid_alive = _alive(backend_pid)
    responsive: bool | None = None
    base_url = lifecycle["base_url"]
    if pid_alive and state in {"STARTING", "HEALTHY"} and base_url:
        code, body = _http_json(f"{base_url.rstrip('/')}/api/v1/ready", timeout=2.0)
        ready = code == 200 and isinstance(body, dict) and isinstance(
            body.get("data"), dict
        )
        responsive = ready
        if state == "HEALTHY" and not ready:
            # Process alive but the product is not answering honestly.
            state = "UNRESPONSIVE"
        elif state == "STARTING":
            state = "HEALTHY" if ready else "STARTING"

    return {
        "lifecycle": {
            "state": state,
            "detail": lifecycle["detail"],
            "at": lifecycle["at"],
            "responsive": responsive,
        },
        "backend": {
            "pid": backend_pid,
            "process_alive": pid_alive,
            "running": pid_alive and state in {"STARTING", "HEALTHY"},
        },
        "model_server": {
            "pid": model_pid,
            "running": _alive(model_pid),
        },
    }
