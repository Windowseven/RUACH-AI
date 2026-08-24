"""Probe tests: discovery layers tolerate missing info, never crash.

docs/15 §5-§13 (discovery), §33 (offline-first), docs/16 §4, §11.
"""

from __future__ import annotations

from pathlib import Path

from ruach_setup.diagnostics import UNKNOWN, DependencyState, InferenceLevel, Status
from ruach_setup.probes import (
    CommandOutcome,
    classify_dependency,
    first_version_line,
    parse_meminfo,
    probe_memory,
    probe_model,
    probe_native_runtime,
    probe_network,
    probe_platform,
    probe_python_dependency,
    probe_storage,
    probe_toolchain,
)

MEMINFO_FULL = """MemTotal:       1872060 kB
MemFree:          594332 kB
MemAvailable:     812000 kB
Cached:           320112 kB
SwapTotal:       2097148 kB
SwapFree:              0 kB
"""

MEMINFO_NO_SWAP_FREE = """MemTotal:       1872060 kB
MemAvailable:     812000 kB
SwapTotal:       2097148 kB
"""


# ---------------------------------------------------------------- memory


def test_parse_meminfo_distinguishes_fields() -> None:
    fields = parse_meminfo(MEMINFO_FULL)
    assert fields["MemTotal"] == 1872060
    assert fields["MemAvailable"] == 812000
    assert fields["Cached"] == 320112
    assert fields["SwapTotal"] == 2097148
    assert fields["SwapFree"] == 0


def test_memory_probe_reports_swap_configured_vs_usable() -> None:
    """docs/15 §7: SwapTotal does NOT automatically mean usable swap."""
    results = probe_memory(MEMINFO_FULL)
    swap = next(item for item in results if item.capability == "memory.swap")
    assert swap.details["swap_total_bytes"] == str(2097148 * 1024)
    assert swap.details["swap_usable_bytes"] == "0"
    assert "verified" in swap.technical_reason


def test_memory_probe_reports_unverifiable_swap_without_swapfree() -> None:
    results = probe_memory(MEMINFO_NO_SWAP_FREE)
    swap = next(item for item in results if item.capability == "memory.swap")
    assert swap.status is Status.WARN
    assert swap.details["swap_usable_bytes"] == UNKNOWN
    assert "unverifiable" in swap.technical_reason


def test_memory_probe_empty_text_is_unknown_not_crash() -> None:
    results = probe_memory("")
    total = next(item for item in results if item.capability == "memory.total")
    available = next(item for item in results if item.capability == "memory.available")
    assert total.status is Status.UNKNOWN
    assert available.status is Status.UNKNOWN
    assert total.technical_reason


def test_memory_probe_prefers_memavailable_over_memfree() -> None:
    results = probe_memory(MEMINFO_FULL)
    available = next(item for item in results if item.capability == "memory.available")
    assert available.details["source"] == "MemAvailable"


# -------------------------------------------------------------- platform


def test_platform_probe_maps_armv7_reference_values() -> None:
    results = probe_platform(
        platform_name="Linux",
        termux_prefix="/data/data/com.termux/files/usr",
        termux_version="0.118.0",
        android_build_prop_exists=True,
        machine="armv7l",
        kernel_release="5.15.0-android13",
        android_props={"android_version": "15", "manufacturer": "itel", "model": "A6611L"},
    )
    arch = next(item for item in results if item.capability == "platform.architecture")
    assert arch.status is Status.PASS
    assert arch.details["architecture"] == "arm32"
    assert arch.details["abi"] == "armeabi-v7a"
    android = next(item for item in results if item.capability == "platform.android")
    assert android.details["android_version"] == "15"
    termux = next(item for item in results if item.capability == "platform.termux")
    assert termux.details["termux"] == "yes"


def test_platform_probe_tolerates_missing_metadata() -> None:
    """docs/15 §6: failure to read optional metadata must not crash."""
    results = probe_platform(
        platform_name="Linux",
        termux_prefix=None,
        termux_version=None,
        android_build_prop_exists=False,
        machine="sparc64",
        kernel_release="",
        android_props={},
    )
    arch = next(item for item in results if item.capability == "platform.architecture")
    assert arch.status is Status.WARN
    assert arch.details["architecture"] == "unknown"
    os_result = next(item for item in results if item.capability == "platform.os")
    assert os_result.status is Status.PASS  # scan itself still succeeds


# ------------------------------------------------------------- toolchain


def _fake_runner(ok_tools: set[str]):
    def runner(argv: list[str]) -> CommandOutcome:
        tool = Path(argv[0]).name
        if tool in ok_tools:
            return CommandOutcome(True, f"{tool} version 1.2.3")
        return CommandOutcome(False, "boom")

    return runner


def test_toolchain_probe_reports_present_and_missing() -> None:
    def lookup(name: str) -> str | None:
        return f"/usr/bin/{name}" if name in {"clang", "make"} else None

    results = probe_toolchain(
        runner=_fake_runner({"clang", "make"}), lookup=lookup
    )
    by_capability = {item.capability: item for item in results}
    clang = by_capability["toolchain.clang"]
    assert clang.status is Status.PASS
    assert clang.details["version"].startswith("clang")
    rustc = by_capability["toolchain.rustc"]
    assert rustc.status is Status.FAIL
    assert "MISSING" in rustc.message


def test_missing_rust_is_a_soft_failure_only() -> None:
    """docs/15 §9: missing Rust affects only Rust-requiring capabilities."""
    results = probe_toolchain(
        runner=_fake_runner(set()), lookup=lambda name: None
    )
    rustc = next(item for item in results if item.capability == "toolchain.rustc")
    assert rustc.severity.value == "MEDIUM"  # soft, not CRITICAL
    git = next(item for item in results if item.capability == "toolchain.git")
    assert git.severity.value == "LOW"


def test_first_version_line_picks_nonempty() -> None:
    sample = chr(10).join(("", "clang version 21.1.8", "more"))
    assert first_version_line(sample) == "clang version 21.1.8"
    assert first_version_line("") == ""


# --------------------------------------------------------------- network


def test_network_probe_offline_never_crashes() -> None:
    """docs/15 §33: network failure MUST NOT crash Doctor."""
    results = probe_network(connector=lambda address: False, https_check=lambda url: False)
    assert all(item.status is Status.WARN for item in results)
    dns = next(item for item in results if item.capability == "network.dns")
    assert dns.technical_reason


def test_network_probe_online_reports_pass() -> None:
    results = probe_network(connector=lambda address: True, https_check=lambda url: True)
    assert all(item.status is Status.PASS for item in results)


# -------------------------------------------------------- native runtime


def test_runtime_level_executable_when_binary_found() -> None:
    level, detail = probe_native_runtime(
        binary_path="/opt/llama-server",
        architecture_supported=True,
        compiler_set=frozenset(),
    )
    assert level is InferenceLevel.EXECUTABLE
    assert detail.status is Status.PASS


def test_runtime_level_buildable_requires_full_toolchain() -> None:
    level, detail = probe_native_runtime(
        binary_path=None,
        architecture_supported=True,
        compiler_set=frozenset({"clang", "make", "cmake"}),
    )
    assert level is InferenceLevel.BUILDABLE
    assert "NOT assumed" in detail.message or "not installed" in detail.message


def test_runtime_level_not_tested_without_any_path() -> None:
    level, detail = probe_native_runtime(
        binary_path=None,
        architecture_supported=True,
        compiler_set=frozenset(),
    )
    assert level is InferenceLevel.NOT_TESTED
    assert detail.status is Status.UNKNOWN


# ----------------------------------------------------------------- model


def test_model_probe_states(tmp_path: Path) -> None:
    unset = probe_model(None)
    assert unset.status is Status.WARN

    missing = probe_model(str(tmp_path / "nope.gguf"))
    assert missing.status is Status.FAIL

    model_file = tmp_path / "model.gguf"
    model_file.write_bytes(b"x" * 2048)
    present = probe_model(str(model_file))
    assert present.status is Status.PASS
    assert present.details["size_bytes"] == "2048"


# --------------------------------------------------- dependency classify


def test_dependency_classification_matrix() -> None:
    cases = [
        # (importable, rust, wheel_query, expected)
        (True, False, None, DependencyState.AVAILABLE_WHEEL),
        (False, True, None, DependencyState.SOURCE_BUILDABLE),
        (False, False, None, DependencyState.SOURCE_BUILD_BLOCKED),
        (None, True, None, DependencyState.UNKNOWN),
        (None, None, "AVAILABLE_WHEEL", DependencyState.AVAILABLE_WHEEL),
        (None, True, "UNAVAILABLE", DependencyState.SOURCE_BUILDABLE),
        (None, False, "UNAVAILABLE", DependencyState.SOURCE_BUILD_BLOCKED),
        (None, None, "UNAVAILABLE", DependencyState.UNAVAILABLE),
    ]
    for importable, rust, wheel_query, expected in cases:
        outcome = classify_dependency(
            importable=importable, rust_available=rust, wheel_query=wheel_query
        )
        assert outcome is expected, (importable, rust, wheel_query)


def test_python_dependency_probe_uses_injected_facts() -> None:
    blocked = probe_python_dependency(
        "pydantic_core", importable=False, rust_available=False
    )
    assert blocked.details["dependency_state"] == DependencyState.SOURCE_BUILD_BLOCKED.value
    assert "pydantic-core" not in blocked.message  # module name used verbatim
    healthy = probe_python_dependency(
        "pydantic_core", importable=True, rust_available=False
    )
    assert healthy.status is Status.PASS


# --------------------------------------------------------------- storage


def test_storage_probe_measures_real_tmp(tmp_path: Path) -> None:
    results = probe_storage({"models": tmp_path / "models"})
    entry = results[0]
    assert entry.capability == "storage.models"
    assert int(entry.details["free_bytes"]) > 0