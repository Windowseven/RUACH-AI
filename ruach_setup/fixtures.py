"""Synthetic device fixtures for Doctor testing.

Doctor MUST be testable independently from real hardware. Each fixture is
a complete DecisionInput snapshot representing a documented device class,
plus the profile the decision engine is expected to select. Fixtures are
data only — no probing happens here.

Profiles (v2):
  FULL_HYBRID     — Python backend + native inference (best experience)
  NATIVE_HYBRID   — native inference + lightweight orchestration
  PYTHON_HYBRID   — Python backend + alternative inference provider
  COMPATIBILITY   — constrained device, no full inference, still useful
  DEVELOPMENT_STUB — dev/testing only, no real inference
  UNSUPPORTED     — nothing works
"""

from __future__ import annotations

from dataclasses import dataclass

from ruach_setup.diagnostics import InferenceLevel
from ruach_setup.profiles import DecisionInput, RuntimeProfile

GiB = 1024**3


@dataclass(frozen=True)
class DeviceFixture:
    name: str
    description: str
    capabilities: DecisionInput
    expected_profile: RuntimeProfile


def _fixture(
    name: str,
    description: str,
    *,
    arch_supported: bool,
    abi: str,
    ram_total: int | None,
    ram_available: int | None,
    storage_free: int | None,
    python_ok: bool,
    python_version: str,
    compilers: tuple[str, ...],
    rust: bool,
    binary_found: bool,
    inference_level: InferenceLevel,
    deps_healthy: bool | None,
    tier: str,
    environment: str,
    expected: RuntimeProfile,
    native_build_failed: bool = False,
) -> DeviceFixture:
    return DeviceFixture(
        name=name,
        description=description,
        capabilities=DecisionInput(
            architecture_supported=arch_supported,
            abi=abi,
            ram_total_bytes=ram_total,
            ram_available_bytes=ram_available,
            storage_free_bytes=storage_free,
            python_ok=python_ok,
            python_version=python_version,
            compilers_present=frozenset(compilers),
            rust_available=rust,
            native_binary_found=binary_found,
            inference_level=inference_level,
            python_deps_healthy=deps_healthy,
            native_build_previously_failed=native_build_failed,
            resource_tier=tier,
            environment_status=environment,
        ),
        expected_profile=expected,
    )


# ---- FULL_HYBRID: Python full stack + native inference viable ----

ANDROID_ARM64_CAPABLE = _fixture(
    "android_arm64_capable",
    "Capable Android phone: ARM64, 8 GB RAM, healthy Python wheels, "
    "llama.cpp buildable.",
    arch_supported=True,
    abi="arm64-v8a",
    ram_total=8 * GiB,
    ram_available=5 * GiB,
    storage_free=64 * GiB,
    python_ok=True,
    python_version="3.12.3",
    compilers=("clang", "make", "cmake", "ninja", "git"),
    rust=True,
    binary_found=False,
    inference_level=InferenceLevel.BUILDABLE,
    deps_healthy=True,
    tier="performance",
    environment="target_device",
    expected=RuntimeProfile.FULL_HYBRID,
)

LINUX_X86_64_DESKTOP = _fixture(
    "linux_x86_64_desktop",
    "Desktop Linux x86_64: everything supported.",
    arch_supported=True,
    abi="x86_64",
    ram_total=16 * GiB,
    ram_available=12 * GiB,
    storage_free=200 * GiB,
    python_ok=True,
    python_version="3.12.4",
    compilers=("clang", "gcc", "make", "cmake", "ninja", "git"),
    rust=True,
    binary_found=False,
    inference_level=InferenceLevel.BUILDABLE,
    deps_healthy=True,
    tier="performance",
    environment="development_host",
    expected=RuntimeProfile.FULL_HYBRID,
)

LINUX_ARM64 = _fixture(
    "linux_arm64",
    "Linux ARM64 SBC-class host with working toolchain and Python stack.",
    arch_supported=True,
    abi="arm64-v8a",
    ram_total=8 * GiB,
    ram_available=6 * GiB,
    storage_free=100 * GiB,
    python_ok=True,
    python_version="3.12.4",
    compilers=("gcc", "make", "cmake", "ninja", "git"),
    rust=True,
    binary_found=False,
    inference_level=InferenceLevel.BUILDABLE,
    deps_healthy=True,
    tier="performance",
    environment="unknown",
    expected=RuntimeProfile.FULL_HYBRID,
)

MACOS_DEVELOPMENT_HOST = _fixture(
    "macos_development_host",
    "macOS development machine: full Python stack and a working "
    "toolchain; selects FULL_HYBRID once a runtime is built or resolved.",
    arch_supported=True,
    abi="x86_64",
    ram_total=16 * GiB,
    ram_available=10 * GiB,
    storage_free=120 * GiB,
    python_ok=True,
    python_version="3.12.6",
    compilers=("clang", "make", "cmake", "git"),
    rust=False,
    binary_found=False,
    inference_level=InferenceLevel.BUILDABLE,
    deps_healthy=True,
    tier="performance",
    environment="development_host",
    expected=RuntimeProfile.FULL_HYBRID,
)

# ---- NATIVE_HYBRID: native inference works, Python limited ----

ANDROID_ARMV7_LOW_MEMORY = _fixture(
    "android_armv7_low_memory",
    "Reference Android ARMv7 device (itel A6611L class): ~1.87 GB RAM, "
    "~594 MB available, full LLVM toolchain, no Rust, pydantic-core "
    "wheel unavailable.",
    arch_supported=True,
    abi="armeabi-v7a",
    ram_total=int(1.87 * GiB),
    ram_available=594 * 1024 * 1024,
    storage_free=31 * GiB,
    python_ok=True,
    python_version="3.14.6",
    compilers=("clang", "make", "cmake", "ninja", "git"),
    rust=False,
    binary_found=False,
    inference_level=InferenceLevel.BUILDABLE,
    deps_healthy=False,
    tier="light",
    environment="target_device",
    expected=RuntimeProfile.NATIVE_HYBRID,
)

ANDROID_ARM64_CONSTRAINED = _fixture(
    "android_arm64_constrained",
    "Constrained Android phone: ARM64, ~2 GB RAM available, dependency "
    "health unknown pending measurement.",
    arch_supported=True,
    abi="arm64-v8a",
    ram_total=4 * GiB,
    ram_available=2 * GiB,
    storage_free=16 * GiB,
    python_ok=True,
    python_version="3.12.1",
    compilers=("clang", "make", "cmake", "ninja", "git"),
    rust=False,
    binary_found=False,
    inference_level=InferenceLevel.BUILDABLE,
    deps_healthy=None,
    tier="balanced",
    environment="target_device",
    expected=RuntimeProfile.NATIVE_HYBRID,
)

NATIVE_ONLY_DEVICE = _fixture(
    "native_only_device",
    "Appliance-class ARM64 board: llama.cpp buildable but no usable "
    "Python 3.11+ runtime; CLI-first native installation.",
    arch_supported=True,
    abi="arm64-v8a",
    ram_total=4 * GiB,
    ram_available=2 * GiB,
    storage_free=32 * GiB,
    python_ok=False,
    python_version="3.8.10",
    compilers=("clang", "make", "cmake", "ninja", "git"),
    rust=False,
    binary_found=False,
    inference_level=InferenceLevel.BUILDABLE,
    deps_healthy=None,
    tier="balanced",
    environment="unknown",
    expected=RuntimeProfile.NATIVE_HYBRID,
)

# ---- PYTHON_HYBRID: Python healthy but no native inference ----

LINUX_MINIMAL_NO_TOOLCHAIN = _fixture(
    "linux_minimal_no_toolchain",
    "Minimal Linux container: healthy pure-Python stack but no C "
    "compiler or build tools; inference must come from an adapter.",
    arch_supported=True,
    abi="x86_64",
    ram_total=4 * GiB,
    ram_available=3 * GiB,
    storage_free=20 * GiB,
    python_ok=True,
    python_version="3.12.1",
    compilers=("git",),
    rust=False,
    binary_found=False,
    inference_level=InferenceLevel.NOT_TESTED,
    deps_healthy=True,
    tier="balanced",
    environment="unknown",
    expected=RuntimeProfile.PYTHON_HYBRID,
)

# ---- COMPATIBILITY: severely constrained ----

SEVERELY_CONSTRAINED_NATIVE = _fixture(
    "severely_constrained_native",
    "Very low-memory device with a working toolchain and no Python: "
    "native inference is still viable despite constraints.",
    arch_supported=True,
    abi="arm64-v8a",
    ram_total=1 * GiB,
    ram_available=512 * 1024 * 1024,
    storage_free=8 * GiB,
    python_ok=False,
    python_version="3.8.10",
    compilers=("clang", "make", "cmake", "git"),
    rust=False,
    binary_found=False,
    inference_level=InferenceLevel.BUILDABLE,
    deps_healthy=None,
    tier="light",
    environment="target_device",
    expected=RuntimeProfile.NATIVE_HYBRID,
)

# ---- UNSUPPORTED: nothing works ----

UNSUPPORTED_DEVICE = _fixture(
    "unsupported_device",
    "No Python, no inference, architecture unsupported.",
    arch_supported=False,
    abi="unknown",
    ram_total=None,
    ram_available=None,
    storage_free=None,
    python_ok=False,
    python_version="3.7.0",
    compilers=(),
    rust=False,
    binary_found=False,
    inference_level=InferenceLevel.NOT_TESTED,
    deps_healthy=None,
    tier="unknown",
    environment="unknown",
    expected=RuntimeProfile.UNSUPPORTED,
)

# ---- NATIVE_HYBRID with previously failed build ----

BUILD_FAILED_DEVICE = _fixture(
    "build_failed_device",
    "Device where llama.cpp build was previously attempted and failed. "
    "Engine honestly reports COMPATIBILITY, not NATIVE_HYBRID.",
    arch_supported=True,
    abi="armeabi-v7a",
    ram_total=int(1.87 * GiB),
    ram_available=594 * 1024 * 1024,
    storage_free=31 * GiB,
    python_ok=True,
    python_version="3.14.6",
    compilers=("clang", "make", "cmake", "ninja", "git"),
    rust=False,
    binary_found=False,
    inference_level=InferenceLevel.BUILDABLE,
    deps_healthy=False,
    native_build_failed=True,
    tier="light",
    environment="target_device",
    expected=RuntimeProfile.COMPATIBILITY,
)

ALL_FIXTURES: tuple[DeviceFixture, ...] = (
    ANDROID_ARMV7_LOW_MEMORY,
    ANDROID_ARM64_CAPABLE,
    ANDROID_ARM64_CONSTRAINED,
    LINUX_ARM64,
    LINUX_X86_64_DESKTOP,
    MACOS_DEVELOPMENT_HOST,
    LINUX_MINIMAL_NO_TOOLCHAIN,
    NATIVE_ONLY_DEVICE,
    SEVERELY_CONSTRAINED_NATIVE,
    UNSUPPORTED_DEVICE,
    BUILD_FAILED_DEVICE,
)


__all__ = [
    "ALL_FIXTURES",
    "ANDROID_ARM64_CAPABLE",
    "ANDROID_ARM64_CONSTRAINED",
    "ANDROID_ARMV7_LOW_MEMORY",
    "BUILD_FAILED_DEVICE",
    "LINUX_ARM64",
    "LINUX_MINIMAL_NO_TOOLCHAIN",
    "LINUX_X86_64_DESKTOP",
    "MACOS_DEVELOPMENT_HOST",
    "NATIVE_ONLY_DEVICE",
    "SEVERELY_CONSTRAINED_NATIVE",
    "UNSUPPORTED_DEVICE",
    "DeviceFixture",
]
