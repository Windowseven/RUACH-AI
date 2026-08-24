from dataclasses import replace
from pathlib import Path
from typing import Any

import tomllib

from ruach_setup.capability import (
    DeviceCapabilityProfile,
    GiB,
    KiB,
    TierConfig,
    analyze,
    build_profile,
    compute_safe_memory_budget,
    load_tier_config,
)
from ruach_setup.device import RawEnvironment, _parse_meminfo, normalize_architecture


def make_raw(**overrides: Any) -> RawEnvironment:
    raw = RawEnvironment(
        platform_name="Linux",
        termux_prefix="/data/data/com.termux/files/usr",
        termux_version="0.118.3",
        android_build_prop_exists=True,
        machine="aarch64",
        cpu_cores=8,
        mem_total_kb=8 * GiB // KiB,
        mem_available_kb=int(4.6 * GiB) // KiB,
        home_path="/data/data/com.termux/files/home",
        storage_total_bytes=64 * GiB,
        storage_free_bytes=30 * GiB,
        python_version="3.14.6",
    )
    return replace(raw, **overrides)


def assessment_for(**raw_overrides):
    return analyze(build_profile(make_raw(**raw_overrides)))


def test_arm64_midrange_is_balanced_with_positive_budget():
    result = assessment_for()
    assert result.profile.architecture == "arm64"
    assert result.profile.abi == "arm64-v8a"
    assert result.tier == "balanced"
    assert result.safe_memory_budget_bytes is not None
    assert result.safe_memory_budget_bytes > 0
    assert result.warnings == ()


def test_arm32_2gb_is_light():
    result = assessment_for(
        machine="armv7l", mem_total_kb=2 * GiB // KiB, mem_available_kb=900 * 1024
    )
    assert result.profile.architecture == "arm32"
    assert result.profile.abi == "armeabi-v7a"
    assert result.tier == "light"
    assert result.warnings == ()


def test_arm32_real_device_budget_insufficient():
    result = assessment_for(
        machine="armv7l",
        mem_total_kb=1_872_060,
        mem_available_kb=640_700,
        storage_free_bytes=31 * GiB,
    )
    assert result.tier == "light"
    assert result.safe_memory_budget_bytes == 0
    assert "MEMORY_BUDGET_INSUFFICIENT" in result.warnings


def test_x86_64_high_memory_is_performance():
    result = assessment_for(machine="x86_64", mem_available_kb=12 * GiB // KiB)
    assert result.tier == "performance"


def test_unknown_architecture_flagged():
    result = assessment_for(machine="sparc")
    assert result.profile.architecture == "unknown"
    assert not result.profile.architecture_supported
    assert "ARCHITECTURE_UNSUPPORTED" in result.warnings


def test_low_storage_warns():
    result = assessment_for(storage_free_bytes=512 * 1024 * 1024)
    assert "STORAGE_LOW" in result.warnings


def test_unknown_ram_blocks_budget_and_tier():
    result = assessment_for(mem_total_kb=None, mem_available_kb=None)
    assert result.tier == "unknown"
    assert result.safe_memory_budget_bytes is None
    assert "RAM_UNKNOWN" in result.warnings


def test_termux_missing_detected():
    result = assessment_for(
        termux_prefix=None,
        termux_version=None,
        android_build_prop_exists=False,
    )
    assert not result.profile.termux_detected
    assert not result.profile.android_detected
    assert "TERMUX_NOT_DETECTED" in result.warnings
    assert "ANDROID_NOT_DETECTED" in result.warnings


def test_android_without_termux():
    result = assessment_for(termux_prefix=None, termux_version=None)
    assert not result.profile.termux_detected
    assert result.profile.android_detected
    assert "TERMUX_NOT_DETECTED" in result.warnings
    assert "ANDROID_NOT_DETECTED" not in result.warnings


def test_meminfo_parser_prefers_memavailable_falls_back_to_memfree():
    text = (
        "MemTotal:       1872060 kB\n"
        "MemFree:          640700 kB\n"
        "MemAvailable:     800000 kB\n"
        "HugePages_Total:       0\n"
        "garbage line without number colon\n"
    )
    total, available = _parse_meminfo(text)
    assert total == 1_872_060
    assert available == 800_000

    fallback_total, fallback_available = _parse_meminfo("MemTotal: 100 kB\nMemFree: 40 kB\n")
    assert (fallback_total, fallback_available) == (100, 40)


def test_normalize_architecture_table():
    assert normalize_architecture("aarch64") == ("arm64", "arm64-v8a", True)
    assert normalize_architecture("ARMv7l") == ("arm32", "armeabi-v7a", True)
    assert normalize_architecture("x86_64") == ("x86_64", "x86_64", True)
    assert normalize_architecture("i686") == ("x86", "i386", True)
    assert normalize_architecture("riscv") == ("unknown", "unknown", False)


def test_budget_formula_matches_documented_heuristic():
    config = TierConfig(
        light_max_bytes=2 * GiB,
        balanced_max_bytes=6 * GiB,
        reserve_bytes=100,
        kv_cache_estimate_bytes=50,
        margin_percent=10,
    )
    expected = 1000 - 100 - 50 - (1000 * 10 // 100)
    assert compute_safe_memory_budget(1000, config) == expected
    assert compute_safe_memory_budget(None, config) == 0


def test_load_tier_config_from_shipped_file():
    data_dir = Path(__file__).parents[1] / "ruach_setup" / "data"
    config = load_tier_config(data_dir / "tiers.toml")
    assert config.reserve_bytes > 0
    assert config.light_max_bytes < config.balanced_max_bytes
    with open(data_dir / "tiers.toml", "rb") as handle:
        raw = tomllib.load(handle)
    assert raw["tiers"]["balanced_max"] == config.balanced_max_bytes


def test_profile_carries_python_version_and_cores():
    profile = build_profile(make_raw())
    assert isinstance(profile, DeviceCapabilityProfile)
    assert profile.python_version == "3.14.6"
    assert profile.cpu_cores == 8
    assert profile.ram_total_bytes == 8 * GiB


def test_macbook_classified_as_development_host():
    result = assessment_for(
        platform_name="Darwin",
        termux_prefix="/usr/local",
        termux_version=None,
        android_build_prop_exists=False,
        machine="x86_64",
        home_path="/Users/dev",
    )
    assert result.environment_status == "development_host"
    assert "TERMUX_NOT_DETECTED" in result.warnings


def test_termux_classified_as_target_device():
    result = assessment_for(machine="armv7l")
    assert result.environment_status == "target_device"


def test_android_without_termux_is_unknown_environment():
    result = assessment_for(termux_prefix=None, termux_version=None)
    assert result.environment_status == "unknown"
