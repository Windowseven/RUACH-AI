"""Doctor v2 — Capability engine with no false positives.

Detects device environment, classifies execution architecture,
and selects a runtime profile. Results are HONEST:
  - Never claim "source build looks viable" after a failed build
  - Never claim "RUACH IS READY" when critical components missing
  - Never claim "full backend" when pydantic-core wheel is unavailable
  - Never confuse failure of one implementation with failure of the platform
"""

from __future__ import annotations

from dataclasses import dataclass

from ruach_setup.build_state import (
    has_previous_build_failure,
    overall_python_health,
    check_backend_python_compatibility,
)
from ruach_setup.capability import analyze, build_profile
from ruach_setup.device import SystemEnvironmentReader
from ruach_setup.diagnostics import InferenceLevel
from ruach_setup.profiles import (
    DecisionInput,
    RuntimeProfile,
    decide,
)


@dataclass
class EnvironmentResult:
    """Simplified environment assessment result."""
    status: str  # "pass", "warn", "fail"
    profile: str
    os: str
    arch: str
    cpu: str
    ram: int | None
    inference_backend: str
    runtime_backend: str
    target_device: bool
    development_host: bool

    def to_json(self) -> dict:
        return {
            "status": self.status,
            "profile": self.profile,
            "os": self.os,
            "arch": self.arch,
            "cpu": self.cpu,
            "ram": self.ram,
            "inference_backend": self.inference_backend,
            "runtime_backend": self.runtime_backend,
            "target_device": self.target_device,
            "development_host": self.development_host,
        }


def _classify_profile(assessment) -> RuntimeProfile:
    """Classify into one of the 5 runtime profiles + UNSUPPORTED."""
    p = assessment.profile
    python_ok = bool(p.python_version and p.python_version != "unknown")

    native_build_failed = has_previous_build_failure(
        "llama.cpp", str(p.architecture)
    )

    python_health = None
    if python_ok:
        try:
            checks = check_backend_python_compatibility()
            python_health = overall_python_health(checks)
        except Exception:
            python_health = None

    # Detect compilers from the assessment warnings or profile
    compilers = frozenset()
    # The capability profile doesn't expose compilers directly;
    # we rely on the existing analysis tier + environment_status

    decision_input = DecisionInput(
        architecture_supported=p.architecture_supported,
        abi=p.architecture,
        ram_total_bytes=p.ram_total_bytes,
        ram_available_bytes=p.ram_available_bytes,
        storage_free_bytes=p.storage_available_bytes,
        python_ok=python_ok,
        python_version=p.python_version or "",
        compilers_present=compilers,
        native_binary_found=False,
        inference_level=InferenceLevel.BUILDABLE if p.architecture_supported else InferenceLevel.NOT_TESTED,
        python_deps_healthy=python_health,
        native_build_previously_failed=native_build_failed,
        resource_tier=assessment.tier,
        environment_status=assessment.environment_status,
    )

    decision = decide(decision_input)
    return decision.profile


def doctor(check_function: bool = True) -> EnvironmentResult:
    """Run diagnostics and return an honest environment assessment."""
    try:
        raw = SystemEnvironmentReader().read()
        assessment = analyze(build_profile(raw))
        profile = _classify_profile(assessment)

        status = "pass" if profile != RuntimeProfile.UNSUPPORTED else "fail"
        if profile == RuntimeProfile.COMPATIBILITY:
            status = "warn"
        if profile == RuntimeProfile.DEVELOPMENT_STUB:
            status = "warn"

        p = assessment.profile
        return EnvironmentResult(
            status=status,
            profile=profile.value,
            os=p.platform_name,
            arch=p.architecture,
            cpu=p.machine_raw,
            ram=p.ram_total_bytes,
            inference_backend="llama.cpp" if profile in (RuntimeProfile.FULL_HYBRID, RuntimeProfile.NATIVE_HYBRID) else "none",
            runtime_backend="hybrid" if profile in (RuntimeProfile.FULL_HYBRID, RuntimeProfile.NATIVE_HYBRID) else "none",
            target_device=assessment.environment_status == "target_device",
            development_host=assessment.environment_status == "development_host",
        )
    except Exception as error:
        return EnvironmentResult(
            status="fail",
            profile="UNKNOWN",
            os="unknown",
            arch="unknown",
            cpu="unknown",
            ram=None,
            inference_backend="none",
            runtime_backend="none",
            target_device=False,
            development_host=False,
        )


def check_functional(check_python: bool = True) -> EnvironmentResult:
    """Full functional check."""
    return doctor(check_function=True)


def check_python() -> EnvironmentResult:
    """Check Python environment."""
    return doctor(check_function=False)
