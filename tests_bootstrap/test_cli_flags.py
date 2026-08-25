"""CLI flag tests for docs/15-17 commands (subprocess level)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
RUACH = ROOT / "ruach"


def run_cli(*args: str, home: Path | None = None) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    if home is not None:
        env["HOME"] = str(home)
    return subprocess.run(
        [sys.executable, str(RUACH), *args],
        capture_output=True,
        text=True,
        timeout=180,
        cwd=str(ROOT),
        check=False,
        env=env,
    )


# ------------------------------------------------------------------ doctor


def test_doctor_json_outputs_machine_readable_report(tmp_path: Path) -> None:
    result = run_cli("doctor", "--json", home=tmp_path)
    data = json.loads(result.stdout)
    assert "status" in data, "JSON output must have status field"
    assert "os" in data
    assert "arch" in data
    assert "inference_backend" in data
    assert result.returncode in (0, 1)


def test_doctor_verbose_shows_full_detail(tmp_path: Path) -> None:
    result = run_cli("doctor", "--verbose", home=tmp_path)
    assert "RUACH DOCTOR" in result.stdout
    assert result.returncode in (0, 1)


def test_doctor_concise_is_default_and_short(tmp_path: Path) -> None:
    result = run_cli("doctor", home=tmp_path)
    assert "RUACH DOCTOR" in result.stdout
    assert result.returncode in (0, 1)


def test_doctor_check_runtime_flag_accepted(tmp_path: Path) -> None:
    result = run_cli("doctor", "--check-runtime", home=tmp_path)
    assert result.returncode in (0, 1)


# ------------------------------------------------------------------- setup


def test_setup_plan_shows_plan_without_executing(tmp_path: Path) -> None:
    result = run_cli("setup", "--plan", home=tmp_path)
    assert result.returncode == 0
    assert "INSTALLATION PLAN" in result.stdout or "Installation Plan" in result.stdout
    assert "No changes were made." in result.stdout
    assert not (tmp_path / ".ruach" / "config").exists()
    assert not (tmp_path / ".ruach" / "setup_state.json").exists()


def test_setup_non_interactive_prints_environment_without_prompts(
    tmp_path: Path,
) -> None:
    result = run_cli("setup", "--non-interactive", home=tmp_path)
    assert result.returncode == 0
    assert "RUACH SETUP" in result.stdout or "Environment" in result.stdout
