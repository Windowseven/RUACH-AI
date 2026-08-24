"""Doctor engine tests (docs/15 §4/§29/§31/§32, docs/16 §5-§6/§17)."""

from __future__ import annotations

import json
import stat
from pathlib import Path

from bootstrap.doctor_engine import (
    render_concise,
    render_verbose,
    run_doctor,
)


def _no_tools(name: str) -> str | None:
    return None


def _failing_runner(argv):
    raise AssertionError("runner must not be called when nothing is found")


def test_run_doctor_completes_on_empty_home(tmp_path: Path) -> None:
    """Doctor must work on a bare environment without crashing."""
    report = run_doctor(
        home=tmp_path,
        run_dir=tmp_path / "run",
        probe_network_enabled=False,
        runner=_failing_runner,
        lookup=_no_tools,
    )
    assert report.status in {"READY", "DEGRADED", "BLOCKED"}
    assert report.matrix, "capability matrix must be populated"
    assert report.decision["profile"]
    assert report.plan is not None
    levels = {entry.level for entry in report.verification}
    assert {"Environment", "Toolchain", "Runtime", "Model", "API"} <= levels
    # Inference stays NOT_TESTED unless explicitly requested.
    inference = next(entry for entry in report.verification if entry.level == "Inference")
    assert inference.status.value == "UNKNOWN"


def test_doctor_json_is_serializable_and_structured(tmp_path: Path) -> None:
    report = run_doctor(
        home=tmp_path,
        run_dir=tmp_path / "run",
        probe_network_enabled=False,
        runner=_failing_runner,
        lookup=_no_tools,
    )
    data = json.loads(json.dumps(report.to_json()))
    for key in ("device", "toolchain", "python", "capabilities", "matrix",
                "decision", "plan", "verification", "status"):
        assert key in data, key
    assert data["decision"]["reason"], "docs/15 §23 requires explainable output"


def test_doctor_writes_operation_log(tmp_path: Path) -> None:
    run_doctor(
        home=tmp_path,
        run_dir=tmp_path / "run",
        probe_network_enabled=False,
        runner=_failing_runner,
        lookup=_no_tools,
    )
    log_dir = tmp_path / ".ruach" / "logs" / "doctor"
    assert log_dir.is_dir()
    logs = list(log_dir.glob("*-scan.log"))
    assert logs, "doctor scan must leave a timestamped log"
    content = logs[0].read_text(encoding="utf-8")
    assert "operation: scan" in content
    assert "profile:" in content


def test_concise_render_matches_docs_block(tmp_path: Path) -> None:
    report = run_doctor(
        home=tmp_path,
        run_dir=tmp_path / "run",
        probe_network_enabled=False,
        runner=_failing_runner,
        lookup=_no_tools,
    )
    text = render_concise(report)
    for line_prefix in ("Status:", "Profile:", "Inference:", "API:", "Model storage:", "Warnings:"):
        assert any(line.startswith(line_prefix) for line in text.splitlines()), line_prefix


def test_verbose_render_shows_matrix_reasons_verification(tmp_path: Path) -> None:
    report = run_doctor(
        home=tmp_path,
        run_dir=tmp_path / "run",
        probe_network_enabled=False,
        runner=_failing_runner,
        lookup=_no_tools,
    )
    text = render_verbose(report)
    assert "Capability matrix" in text
    assert "Why this profile" in text
    assert "Verification" in text
    assert "Installation plan" in text


def test_check_runtime_executes_configured_binary(tmp_path: Path) -> None:
    binary = tmp_path / "bin" / "llama-server"
    binary.parent.mkdir(parents=True)
    script = chr(10).join(["#!/bin/sh", 'echo "llama-server b4000"', "exit 0"])
    binary.write_text(script)
    mode = binary.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
    binary.chmod(mode)

    config_dir = tmp_path / ".ruach" / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "ruach.env").write_text(
        f"RUACH_LLAMA_SERVER_BIN={binary}" + chr(10), encoding="utf-8"
    )

    report = run_doctor(
        home=tmp_path,
        run_dir=tmp_path / "run",
        probe_network_enabled=False,
        runner=_failing_runner,
        lookup=_no_tools,
        check_runtime=True,
    )
    runtime_entry = next(entry for entry in report.verification if entry.level == "Runtime")
    assert runtime_entry.status.value == "PASS"
    assert "executes" in runtime_entry.detail


def test_check_inference_reports_failure_when_server_down(tmp_path: Path) -> None:
    report = run_doctor(
        home=tmp_path,
        run_dir=tmp_path / "run",
        probe_network_enabled=False,
        runner=_failing_runner,
        lookup=_no_tools,
        check_inference=True,
    )
    inference = next(entry for entry in report.verification if entry.level == "Inference")
    assert inference.status.value == "FAIL"
    assert "not answering" in inference.detail


def test_doctor_never_modifies_outside_logs(tmp_path: Path) -> None:
    """Scan must not create config/models/state — only its own log area."""
    run_doctor(
        home=tmp_path,
        run_dir=tmp_path / "run",
        probe_network_enabled=False,
        runner=_failing_runner,
        lookup=_no_tools,
    )
    ruach_root = tmp_path / ".ruach"
    created = {item.name for item in ruach_root.iterdir()}
    assert created == {"logs"}, f"scan created unexpected entries: {created}"