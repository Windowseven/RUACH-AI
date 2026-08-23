"""Tests for `ruach start/stop/status` bring-up (roadmap row 11).

The end-to-end tests spawn the REAL uvicorn child (stub model runtime,
isolated DB/workspace/audit via extra_env) and prove honest readiness:
the stack reports ready only when /api/v1/ready says so, then stop()
cleans every process and pid file.
"""

from __future__ import annotations

import http.server
import json
import os
import socket
import socketserver
import subprocess
import threading
from pathlib import Path

import pytest

from bootstrap.runtime import (
    AlreadyRunning,
    load_config,
    merged_environment,
    parse_env_file,
    port_of,
    start,
    status,
    stop,
    wait_for_backend,
    wait_for_inference,
)


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def test_parse_env_file_handles_comments_blanks_and_values_with_equals() -> None:
    text = (
        "# a comment\n"
        "\n"
        "RUACH_MODEL_RUNTIME=llama_cpp\n"
        "RUACH_MODEL_SERVER_URL=http://127.0.0.1:8080\n"
        "WEIRD=value=with=equals"
    )
    parsed = parse_env_file(text)
    assert parsed == {
        "RUACH_MODEL_RUNTIME": "llama_cpp",
        "RUACH_MODEL_SERVER_URL": "http://127.0.0.1:8080",
        "WEIRD": "value=with=equals",
    }


def test_load_config_missing_file_is_empty(tmp_path: Path) -> None:
    assert load_config(tmp_path / "nope.env") == {}


def test_process_environment_wins_over_generated_file(monkeypatch) -> None:
    monkeypatch.setenv("RUACH_MODEL_NAME", "from-shell")
    env = merged_environment({"RUACH_MODEL_NAME": "from-file", "RUACH_PORT": "8018"})
    assert env["RUACH_MODEL_NAME"] == "from-shell"
    assert env["RUACH_PORT"] == "8018"


def test_port_of_rejects_url_without_port() -> None:
    with pytest.raises(Exception, match="no explicit port"):
        port_of("http://127.0.0.1")


class _FakeLlamaHandler(http.server.BaseHTTPRequestHandler):
    mode = "loading"  # class attribute; flipped by tests

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        self.rfile.read(length)
        if type(self).mode == "ready":
            body = json.dumps(
                {"choices": [{"message": {"role": "assistant", "content": "!"}}]}
            ).encode()
        else:
            body = b"{}"
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args) -> None:
        pass


@pytest.fixture()
def fake_llama():
    handler = type("Handler", (_FakeLlamaHandler,), {"mode": "loading"})
    with socketserver.TCPServer(("127.0.0.1", 0), handler) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        url = f"http://127.0.0.1:{server.server_address[1]}"
        yield url, handler
        server.shutdown()


def test_inference_readiness_requires_a_real_completion(fake_llama) -> None:
    url, handler = fake_llama

    # An ok-shaped response while still loading must NOT count as ready.
    assert wait_for_inference(url, timeout=1.5) is False

    handler.mode = "ready"  # type: ignore[attr-defined]
    assert wait_for_inference(url, timeout=3.0) is True


def _migrate(db_path: Path) -> None:
    subprocess.run(
        [".venv/bin/python", "-m", "alembic", "-c", "backend/alembic.ini", "upgrade", "head"],
        check=True,
        capture_output=True,
        env={**os.environ, "RUACH_DATABASE_URL": f"sqlite:///{db_path}"},
    )


def _install_env(root: Path) -> dict[str, str]:
    workspace = root / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    return {
        "RUACH_DATABASE_URL": f"sqlite:///{root / 'ruach.db'}",
        "RUACH_WORKSPACE_PATH": str(workspace),
        "RUACH_AUDIT_LOG_PATH": str(root / "audit.jsonl"),
    }


def test_start_stub_stack_end_to_end_then_stop(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "install"
    config_path = root / "ruach.env"
    config_path.parent.mkdir(parents=True)
    config_path.write_text("RUACH_MODEL_RUNTIME=stub\n", encoding="utf-8")
    run_dir = root / "run"

    monkeypatch.delenv("RUACH_MODEL_RUNTIME", raising=False)
    extra_env = _install_env(root)
    _migrate(root / "ruach.db")

    stack = start(
        config_path=root / "missing.env",
        run_dir=run_dir,
        backend_port=_free_port(),
        stub=True,
        browser=False,
        extra_env=extra_env,
    )
    try:
        state = status(run_dir=run_dir)
        assert state["backend"]["running"] is True
        # The readiness contract held before start() returned; re-prove it.
        assert wait_for_backend(stack.base_url, timeout=10.0) is True
    finally:
        stop_code = stop(run_dir=run_dir, echo=lambda *_: None)
    assert stop_code == 0
    assert stack.backend.poll() is not None
    assert status(run_dir=run_dir)["backend"]["running"] is False
    assert not (run_dir / "backend.pid").exists()


def test_start_migrates_a_virgin_database_itself(tmp_path: Path, monkeypatch) -> None:
    """Fresh install: start() must reach ready WITHOUT any manual migration."""
    import sqlite3

    root = tmp_path / "install"
    run_dir = root / "run"
    monkeypatch.delenv("RUACH_MODEL_RUNTIME", raising=False)
    extra_env = _install_env(root)
    db = root / "ruach.db"  # deliberately NOT migrated

    stack = start(
        config_path=root / "missing.env",
        run_dir=run_dir,
        backend_port=_free_port(),
        stub=True,
        browser=False,
        extra_env=extra_env,
    )
    try:
        assert wait_for_backend(stack.base_url, timeout=10.0) is True
    finally:
        stop(run_dir=run_dir, echo=lambda *_: None)

    with sqlite3.connect(db) as connection:
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    assert {"conversations", "messages", "approval_requests", "alembic_version"} <= tables


def test_double_start_refused_while_running(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "install"
    run_dir = root / "run"
    monkeypatch.delenv("RUACH_MODEL_RUNTIME", raising=False)
    extra_env = _install_env(root)
    _migrate(root / "ruach.db")

    start(
        config_path=root / "missing.env",
        run_dir=run_dir,
        backend_port=_free_port(),
        stub=True,
        browser=False,
        extra_env=extra_env,
    )
    try:
        with pytest.raises(AlreadyRunning):
            start(
                config_path=root / "missing.env",
                run_dir=run_dir,
                backend_port=_free_port(),
                stub=True,
                browser=False,
                extra_env=extra_env,
            )
    finally:
        stop(run_dir=run_dir, echo=lambda *_: None)


def test_stop_when_nothing_runs_is_clean(tmp_path: Path) -> None:
    assert stop(run_dir=tmp_path, echo=lambda *_: None) == 0
