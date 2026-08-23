"""P12 tests: RuntimeResolver (§7), lifecycle states (§9), stage classes (§8)."""

from __future__ import annotations

import os
import stat
from pathlib import Path

from bootstrap.runtime import read_lifecycle, set_lifecycle, status
from bootstrap.runtime_resolver import (
    ResolvedRuntime,
    resolve_llama_server,
)
from bootstrap.verify import build_stages


def _make_executable(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\n")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


def test_resolver_prefers_explicit_config(tmp_path: Path) -> None:
    configured = _make_executable(tmp_path / "configured" / "llama-server")
    resolved = resolve_llama_server(
        explicit=str(configured),
        home=tmp_path / "home",
        project_root=tmp_path / "proj",
        path_lookup=lambda name: None,
    )
    assert resolved.path == configured and resolved.source == "config"


def test_resolver_order_user_then_project_then_path(tmp_path: Path) -> None:
    home = tmp_path / "home"
    project = tmp_path / "proj"
    on_path = tmp_path / "pathbin"

    user_bin = _make_executable(home / ".ruach" / "runtime" / "llama-server")
    project_bin = _make_executable(project / ".build" / "runtime" / "llama-server")
    path_bin = _make_executable(on_path / "llama-server")

    def lookup(name: str) -> str | None:
        return str(path_bin)

    # 1. user-local wins over everything below it
    resolved = resolve_llama_server(
        home=home, project_root=project, path_lookup=lookup
    )
    assert resolved.source == "user" and resolved.path == user_bin

    # 2. no user install -> project build
    os.remove(user_bin)
    resolved = resolve_llama_server(home=home, project_root=project, path_lookup=lookup)
    assert resolved.source == "project" and resolved.path == project_bin

    # 3. neither -> PATH
    os.remove(project_bin)
    resolved = resolve_llama_server(home=home, project_root=project, path_lookup=lookup)
    assert resolved.source == "path" and resolved.path == path_bin

    # 4. nothing anywhere -> honest missing, never a guess
    resolved = resolve_llama_server(
        home=home, project_root=project, path_lookup=lambda name: None
    )
    assert resolved.found is False and resolved.source == "missing"


def test_resolver_rejects_non_executable_files(tmp_path: Path) -> None:
    home = tmp_path / "home"
    not_executable = home / ".ruach" / "runtime" / "llama-server"
    not_executable.parent.mkdir(parents=True)
    not_executable.write_text("junk")  # no +x

    fallback = _make_executable(tmp_path / "bin" / "llama-server")
    resolved = resolve_llama_server(
        home=home,
        project_root=tmp_path / "proj",
        path_lookup=lambda name: str(fallback),
    )
    assert resolved.source == "path"


def test_lifecycle_transitions_are_recorded_and_default_to_stopped(
    tmp_path: Path,
) -> None:
    assert read_lifecycle(tmp_path)["state"] == "STOPPED"
    set_lifecycle(tmp_path, "STARTING", base_url="http://127.0.0.1:9001")
    set_lifecycle(tmp_path, "HEALTHY")
    state = read_lifecycle(tmp_path)
    assert state["state"] == "HEALTHY"
    assert state["base_url"] == "http://127.0.0.1:9001", "URL carried for probes"
    set_lifecycle(tmp_path, "STOPPING")
    set_lifecycle(tmp_path, "STOPPED")
    assert read_lifecycle(tmp_path)["state"] == "STOPPED"


def test_status_reports_unresponsive_when_pid_alive_but_product_silent(
    tmp_path: Path, monkeypatch
) -> None:
    import time as time_module

    monkeypatch.setattr(
        "bootstrap.runtime.read_pid", lambda run_dir, name: 4242 if name == "backend" else None
    )
    monkeypatch.setattr("bootstrap.runtime._alive", lambda pid: pid == 4242)
    monkeypatch.setattr(
        "bootstrap.runtime._http_json", lambda url, timeout: (0, None)
    )
    monkeypatch.setattr(time_module, "strftime", lambda fmt: "now")
    set_lifecycle(tmp_path, "HEALTHY", base_url="http://127.0.0.1:9999")
    report = status(run_dir=tmp_path)
    assert report["lifecycle"]["state"] == "UNRESPONSIVE"
    assert report["backend"]["process_alive"] is True
    assert report["backend"]["running"] is False, "alive PID is not health proof"


def test_stage_classification_keeps_core_honest() -> None:
    stages = {stage.name: stage for stage in build_stages(include_live=True)}
    assert stages["doctor"].klass == "CORE"
    dev_stages = {name for name, s in stages.items() if s.klass != "CORE"}
    assert dev_stages == {
        "backend-unit",
        "bootstrap-tests",
        "fresh-install-twice-from-zero",
        "ui-build",
        "browser-e2e",
        "live-model-smoke",
    }


def test_browser_e2e_skips_gracefully_without_playwright(monkeypatch) -> None:
    import sys

    stages = {stage.name: stage for stage in build_stages(include_live=False)}
    monkeypatch.setitem(sys.modules, "playwright", None)  # import raises ImportError
    reason = stages["browser-e2e"].unavailable_reason()
    assert reason is not None and "playwright" in reason


def test_resolved_runtime_dataclass_defaults() -> None:
    missing = ResolvedRuntime(None, "missing")
    assert missing.found is False
