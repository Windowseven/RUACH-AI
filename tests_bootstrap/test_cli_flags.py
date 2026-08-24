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
    assert "decision" in data and "matrix" in data and "plan" in data
    assert data["decision"]["reason"], "explainable selection required"
    assert data["status"] in {"READY", "DEGRADED", "BLOCKED"}
    assert result.returncode in (0, 1)


def test_doctor_verbose_shows_full_detail(tmp_path: Path) -> None:
    result = run_cli("doctor", "--verbose", home=tmp_path)
    assert "Capability matrix" in result.stdout
    assert "Why this profile" in result.stdout
    assert "Verification" in result.stdout


def test_doctor_concise_is_default_and_short(tmp_path: Path) -> None:
    result = run_cli("doctor", home=tmp_path)
    assert "Status:" in result.stdout
    assert "Profile:" in result.stdout
    assert "Capability matrix" not in result.stdout, "no info dump by default"


def test_doctor_check_runtime_flag_accepted(tmp_path: Path) -> None:
    result = run_cli("doctor", "--check-runtime", home=tmp_path)
    assert result.returncode in (0, 1)


# ------------------------------------------------------------------- setup


def test_setup_plan_shows_plan_without_executing(tmp_path: Path) -> None:
    """docs/15 §25: --plan MUST show the plan without executing it."""
    result = run_cli("setup", "--plan", home=tmp_path)
    assert result.returncode == 0
    assert "Installation Plan" in result.stdout
    assert "No changes were made." in result.stdout
    assert not (tmp_path / ".ruach" / "config").exists()
    assert not (tmp_path / ".ruach" / "setup_state.json").exists()


def test_setup_non_interactive_prints_environment_without_prompts(
    tmp_path: Path,
) -> None:
    result = run_cli("setup", "--non-interactive", home=tmp_path)
    assert result.returncode == 0
    assert "RUACH SETUP" in result.stdout
    assert "Environment" in result.stdout
    assert "Continue?" not in result.stdout


def test_setup_rejects_unknown_mode() -> None:
    result = run_cli("setup", "--mode", "bogus")
    assert result.returncode != 0


def test_setup_mode_validation_reports_available_modes(tmp_path: Path) -> None:
    """docs/16 §18: invalid mode lists what IS available."""
    # A fresh HOME has no configured model; native mode needs the full
    # dependency stack, so it must be rejected with alternatives listed.
    result = run_cli("setup", "--non-interactive", "--mode", "native", home=tmp_path)
    if result.returncode == 2:
        assert "unavailable on this device" in result.stdout
        assert "Available modes:" in result.stdout
    else:
        # On hosts where the full stack IS viable, native is legitimately allowed.
        assert result.returncode == 0


# ------------------------------------------------------------------ status


def test_status_human_block_matches_docs_format(tmp_path: Path) -> None:
    """docs/16 §19 status block."""
    result = run_cli("status", home=tmp_path)
    assert "RUACH STATUS" in result.stdout
    for label in ("Runtime", "Backend", "Inference", "Model", "API", "Storage"):
        assert f"{label:<14}:" in result.stdout or f"{label} " in result.stdout
    assert "Overall" in result.stdout
    assert result.returncode in (0, 1)


def test_status_json_flag_keeps_machine_output(tmp_path: Path) -> None:
    result = run_cli("status", "--json", home=tmp_path)
    data = json.loads(result.stdout)
    assert "backend" in data and "lifecycle" in data