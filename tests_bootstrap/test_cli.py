import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
RUACH = ROOT / "ruach"


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(RUACH), *args],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=str(ROOT),
        check=False,
    )


def test_version_reports():
    result = run_cli("--version")
    assert result.returncode == 0
    assert "ruach" in result.stdout + result.stderr


def test_help_lists_commands():
    result = run_cli("--help")
    assert result.returncode == 0
    assert "setup" in result.stdout
    assert "doctor" in result.stdout


def test_setup_runs_and_prints_environment():
    result = run_cli("setup")
    assert result.returncode == 0
    assert "RUACH SETUP" in result.stdout
    assert "Platform" in result.stdout
    assert "Environment    :" in result.stdout
    assert any(
        label in result.stdout for label in ("Development Host", "Termux Target Device", "Unknown")
    )


def test_setup_on_non_termux_never_claims_target_verified():
    result = run_cli("setup")
    if "Environment    : Termux Target Device" not in result.stdout:
        assert "has not yet been verified" in result.stdout


def test_doctor_exits_clean_when_repo_intact():
    result = run_cli("doctor")
    assert result.returncode == 0
    assert "RUACH is healthy." in result.stdout


def test_unknown_command_fails():
    result = run_cli("fly")
    assert result.returncode != 0
