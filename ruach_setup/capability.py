"""Capability analysis: profile building, tier classification, memory budget.

The analyzer consumes a DeviceCapabilityProfile and produces a
CapabilityAssessment carrying everything later selectors need — they must
never re-scan the device.

All numeric thresholds are PROVISIONAL calibration values loaded from
data/tiers.toml and must be replaced with benchmark-derived data (doc 10 §6).
"""

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from ruach_setup.device import RawEnvironment, normalize_architecture

KiB = 1024
GiB = 1024**3

Tier = Literal["light", "balanced", "performance", "unknown"]

EnvironmentStatus = Literal["target_device", "development_host", "unknown"]

DEFAULT_TIERS_PATH = Path(__file__).parent / "data" / "tiers.toml"


@dataclass(frozen=True)
class DeviceCapabilityProfile:
    platform_name: str
    android_detected: bool
    termux_detected: bool
    termux_version: str | None
    architecture: str
    abi: str
    machine_raw: str
    architecture_supported: bool
    cpu_cores: int | None
    ram_total_bytes: int | None
    ram_available_bytes: int | None
    storage_total_bytes: int | None
    storage_available_bytes: int | None
    python_version: str


@dataclass(frozen=True)
class TierConfig:
    light_max_bytes: int
    balanced_max_bytes: int
    reserve_bytes: int
    kv_cache_estimate_bytes: int
    margin_percent: int


@dataclass(frozen=True)
class CapabilityAssessment:
    profile: DeviceCapabilityProfile
    tier: Tier
    safe_memory_budget_bytes: int | None
    warnings: tuple[str, ...]
    environment_status: EnvironmentStatus = "unknown"


def classify_environment(profile: DeviceCapabilityProfile) -> EnvironmentStatus:
    """Distinguish where setup is running.

    The MacBook is a DEVELOPMENT HOST; Android+Termux is the TARGET DEVICE.
    The two must never be conflated (ARCH-009 clarification §5).
    """
    if profile.termux_detected:
        return "target_device"
    if not profile.android_detected:
        return "development_host"
    return "unknown"


def load_tier_config(path: Path | None = None) -> TierConfig:
    config_path = path or DEFAULT_TIERS_PATH
    with open(config_path, "rb") as handle:
        raw = tomllib.load(handle)
    memory = raw["memory"]
    tiers = raw["tiers"]
    return TierConfig(
        light_max_bytes=int(tiers["light_max"]),
        balanced_max_bytes=int(tiers["balanced_max"]),
        reserve_bytes=int(memory["reserve_bytes"]),
        kv_cache_estimate_bytes=int(memory["kv_cache_estimate_bytes"]),
        margin_percent=int(memory["margin_percent"]),
    )


def build_profile(raw: RawEnvironment) -> DeviceCapabilityProfile:
    architecture, abi, recognized = normalize_architecture(raw.machine)
    termux_detected = raw.termux_version is not None or (
        raw.termux_prefix is not None and "com.termux" in raw.termux_prefix
    )
    android_detected = termux_detected or raw.android_build_prop_exists
    ram_total = raw.mem_total_kb * KiB if raw.mem_total_kb is not None else None
    ram_available = raw.mem_available_kb * KiB if raw.mem_available_kb is not None else None
    return DeviceCapabilityProfile(
        platform_name=raw.platform_name,
        android_detected=android_detected,
        termux_detected=termux_detected,
        termux_version=raw.termux_version,
        architecture=architecture,
        abi=abi,
        machine_raw=raw.machine,
        architecture_supported=recognized,
        cpu_cores=raw.cpu_cores,
        ram_total_bytes=ram_total,
        ram_available_bytes=ram_available,
        storage_total_bytes=raw.storage_total_bytes,
        storage_available_bytes=raw.storage_free_bytes,
        python_version=raw.python_version,
    )


def compute_safe_memory_budget(ram_available_bytes: int | None, config: TierConfig) -> int:
    """Return budget in bytes; 0 means insufficient / unknown-unsafe.

    Provisional heuristic:
        available - system/application reserve - estimated KV cache - margin%
    Constants are calibration placeholders until benchmark evidence exists.
    """
    if ram_available_bytes is None:
        return 0
    margin = ram_available_bytes * config.margin_percent // 100
    budget = ram_available_bytes - config.reserve_bytes - config.kv_cache_estimate_bytes - margin
    return max(budget, 0)


def classify_tier(ram_available_bytes: int | None, config: TierConfig) -> Tier:
    if ram_available_bytes is None:
        return "unknown"
    if ram_available_bytes <= config.light_max_bytes:
        return "light"
    if ram_available_bytes <= config.balanced_max_bytes:
        return "balanced"
    return "performance"


def analyze(
    profile: DeviceCapabilityProfile,
    config: TierConfig | None = None,
) -> CapabilityAssessment:
    active_config = config or load_tier_config()
    warnings: list[str] = []

    if not profile.architecture_supported:
        warnings.append("ARCHITECTURE_UNSUPPORTED")
    if not profile.android_detected:
        warnings.append("ANDROID_NOT_DETECTED")
    if not profile.termux_detected:
        warnings.append("TERMUX_NOT_DETECTED")
    if profile.ram_available_bytes is None:
        warnings.append("RAM_UNKNOWN")
    if profile.storage_available_bytes is None:
        warnings.append("STORAGE_UNKNOWN")
    elif profile.storage_available_bytes < 1 * GiB:
        warnings.append("STORAGE_LOW")

    tier = classify_tier(profile.ram_available_bytes, active_config)
    budget = compute_safe_memory_budget(profile.ram_available_bytes, active_config)
    if budget == 0 and profile.ram_available_bytes is not None:
        warnings.append("MEMORY_BUDGET_INSUFFICIENT")

    return CapabilityAssessment(
        profile=profile,
        tier=tier,
        safe_memory_budget_bytes=budget if profile.ram_available_bytes else None,
        warnings=tuple(warnings),
        environment_status=classify_environment(profile),
    )
