"""Build result persistence and Python wheel compatibility detection.

Records the outcome of native build attempts so Doctor can report
honest results without repeatedly wasting time rebuilding.

Detects Python package wheel availability to determine whether the
full backend stack can actually be installed on this device.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import subprocess
import sysconfig
from dataclasses import dataclass, field
from pathlib import Path

from ruach_setup.diagnostics import DependencyState

# Packages required for the full Python backend
REQUIRED_BACKEND_PACKAGES: tuple[str, ...] = (
    "fastapi",
    "uvicorn",
    "sqlalchemy",
    "alembic",
    "pydantic",
    "pydantic_settings",
    "pydantic_core",
)

# Packages that are known to require native compilation
NATIVE_DEPENDENCY_PACKAGES: tuple[str, ...] = ("pydantic_core",)

DEFAULT_STATE_DIR = Path.home() / ".ruach" / "state"
BUILD_RESULTS_FILE = "build-results.json"


@dataclass(frozen=True)
class BuildResult:
    """Record of a build attempt for a specific runtime."""
    runtime: str
    architecture: str
    python_version: str
    timestamp: str
    success: bool
    failure_summary: str = ""
    build_fingerprint: str = ""

    def to_dict(self) -> dict:
        return {
            "runtime": self.runtime,
            "architecture": self.architecture,
            "python_version": self.python_version,
            "timestamp": self.timestamp,
            "success": self.success,
            "failure_summary": self.failure_summary,
            "build_fingerprint": self.build_fingerprint,
        }

    @classmethod
    def from_dict(cls, data: dict) -> BuildResult:
        return cls(
            runtime=data["runtime"],
            architecture=data["architecture"],
            python_version=data["python_version"],
            timestamp=data["timestamp"],
            success=data["success"],
            failure_summary=data.get("failure_summary", ""),
            build_fingerprint=data.get("build_fingerprint", ""),
        )


@dataclass(frozen=True)
class WheelCheckResult:
    """Result of checking wheel availability for a package."""
    package: str
    state: DependencyState
    version: str = ""
    detail: str = ""


def _build_fingerprint() -> str:
    """Unique identifier for this build environment."""
    parts = [
        sysconfig.get_platform(),
        sysconfig.get_python_version(),
        str(sys.version_info),
    ]
    return "-".join(parts)


def load_build_results(state_dir: Path | None = None) -> list[BuildResult]:
    """Load previously recorded build results."""
    path = (state_dir or DEFAULT_STATE_DIR) / BUILD_RESULTS_FILE
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return [BuildResult.from_dict(item) for item in data.get("results", [])]
    except (ValueError, KeyError, TypeError):
        return []


def save_build_result(result: BuildResult, state_dir: Path | None = None) -> None:
    """Persist a build result. Appends to existing results."""
    directory = state_dir or DEFAULT_STATE_DIR
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / BUILD_RESULTS_FILE

    existing = load_build_results(state_dir)
    # Replace result for same runtime+architecture if exists
    filtered = [
        r for r in existing
        if not (r.runtime == result.runtime and r.architecture == result.architecture)
    ]
    filtered.append(result)

    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(
        json.dumps({"results": [r.to_dict() for r in filtered]}, indent=2),
        encoding="utf-8",
    )
    os.replace(tmp_path, path)


def has_previous_build_failure(
    runtime: str, architecture: str, state_dir: Path | None = None
) -> bool:
    """Check if a build for this runtime+arch has previously failed."""
    results = load_build_results(state_dir)
    return any(
        r.runtime == runtime and r.architecture == architecture and not r.success
        for r in results
    )


def get_build_failure_summary(
    runtime: str, architecture: str, state_dir: Path | None = None
) -> str | None:
    """Get the failure summary from a previous build, or None."""
    results = load_build_results(state_dir)
    for r in results:
        if r.runtime == runtime and r.architecture == architecture and not r.success:
            return r.failure_summary
    return None


def clear_build_results(
    runtime: str, architecture: str, state_dir: Path | None = None
) -> None:
    """Clear build results for a specific runtime+architecture."""
    results = load_build_results(state_dir)
    filtered = [
        r for r in results
        if not (r.runtime == runtime and r.architecture == architecture)
    ]
    directory = state_dir or DEFAULT_STATE_DIR
    path = directory / BUILD_RESULTS_FILE
    if path.is_file():
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        tmp_path.write_text(
            json.dumps({"results": [r.to_dict() for r in filtered]}, indent=2),
            encoding="utf-8",
        )
        os.replace(tmp_path, path)


def check_wheel_availability(package: str) -> WheelCheckResult:
    """Check if a compatible wheel exists for this platform.

    Uses `pip download --dry-run --only-binary=:all:` to check without
    actually downloading anything.
    """
    try:
        result = subprocess.run(
            [
                sys.executable, "-m", "pip", "download",
                "--dry-run",
                "--only-binary=:all:",
                "--no-deps",
                package,
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if result.returncode == 0:
            # Check if a wheel was found (not a source dist)
            if "Skipping link" not in result.stderr and ".tar.gz" not in result.stdout:
                return WheelCheckResult(
                    package=package,
                    state=DependencyState.AVAILABLE_WHEEL,
                    detail="compatible wheel found",
                )
            return WheelCheckResult(
                package=package,
                state=DependencyState.SOURCE_BUILD_REQUIRED,
                detail="no wheel; source distribution available",
            )
        # Check if it's a "no matching distribution" error
        if "no matching distribution" in result.stderr.lower():
            return WheelCheckResult(
                package=package,
                state=DependencyState.UNAVAILABLE,
                detail="no compatible distribution found",
            )
        return WheelCheckResult(
            package=package,
            state=DependencyState.UNKNOWN,
            detail=result.stderr.strip()[:200],
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return WheelCheckResult(
            package=package,
            state=DependencyState.UNKNOWN,
            detail="pip not available or timed out",
        )


def check_backend_python_compatibility() -> list[WheelCheckResult]:
    """Check wheel availability for all required backend packages."""
    results: list[WheelCheckResult] = []
    for package in REQUIRED_BACKEND_PACKAGES:
        results.append(check_wheel_availability(package))
    return results


def classify_python_dependency_state(
    package: str,
    installed: bool = False,
    wheel_check: WheelCheckResult | None = None,
) -> DependencyState:
    """Classify the state of a Python dependency.

    Priority:
      1. Already installed → AVAILABLE_WHEEL (it works)
      2. Wheel check result → whatever pip reports
      3. Fallback → UNKNOWN
    """
    if installed:
        return DependencyState.AVAILABLE_WHEEL
    if wheel_check is not None:
        return wheel_check.state
    return DependencyState.UNKNOWN


def overall_python_health(checks: list[WheelCheckResult]) -> bool | None:
    """Overall Python backend health assessment.

    Returns:
      True  — all required packages have wheels available
      False — at least one critical package is unavailable
      None  — could not determine (unknown state)
    """
    if not checks:
        return None

    has_failure = False
    has_unknown = False

    for check in checks:
        if check.state in (DependencyState.AVAILABLE_WHEEL, DependencyState.SOURCE_BUILDABLE):
            continue
        if check.state == DependencyState.UNAVAILABLE:
            has_failure = True
        elif check.state == DependencyState.SOURCE_BUILD_REQUIRED:
            # Source build required but might work
            pass
        elif check.state == DependencyState.SOURCE_BUILD_BLOCKED:
            has_failure = True
        else:
            has_unknown = True

    if has_failure:
        return False
    if has_unknown:
        return None
    return True
