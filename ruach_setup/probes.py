"""Device probes: independent discovery layers for RUACH Doctor.

Implements the discovery responsibilities of docs/15 §5-§13, docs/16 §4
and the probe decomposition of docs/17 §25. Rules that govern every probe:

  - A probe NEVER mutates the system (scan must not modify anything).
  - A probe NEVER raises: inaccessible information becomes UNKNOWN with an
    honest technical_reason (docs/15 §6/§7 "tolerate, don't crash").
  - Every claim carries only what was actually measured; statuses are
    never inferred from each other.

Probes take their raw inputs as parameters so tests construct values
directly without a real device; the None default means "measure live".
"""

from __future__ import annotations

import os
import platform as platform_module
import shutil
import struct
import subprocess
import sys
import sysconfig
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ruach_setup.diagnostics import (
    AVAILABLE,
    UNAVAILABLE,
    UNKNOWN,
    DependencyState,
    DiagnosticResult,
    InferenceLevel,
    Severity,
    Status,
    inference_rank,
    result,
)

# --------------------------------------------------------------------------
# Command execution (toolchain probing)


@dataclass(frozen=True)
class CommandOutcome:
    ok: bool
    output: str


CommandRunner = Callable[[list[str]], CommandOutcome]
PathLookup = Callable[[str], str | None]


def _default_runner(argv: list[str]) -> CommandOutcome:
    try:
        completed = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return CommandOutcome(False, str(error))
    output = (completed.stdout or "") + (completed.stderr or "")
    return CommandOutcome(completed.returncode == 0, output.strip())


def _default_lookup(name: str) -> str | None:
    return shutil.which(name)


# --------------------------------------------------------------------------
# Platform probe (docs/15 §5)


def _android_props() -> dict[str, str]:
    """Best-effort Android properties; absent/inaccessible means empty."""
    props: dict[str, str] = {}
    getprop = shutil.which("getprop")
    if not getprop:
        return props
    keys = {
        "ro.build.version.release": "android_version",
        "ro.product.manufacturer": "manufacturer",
        "ro.product.model": "model",
    }
    for prop_key, label in keys.items():
        try:
            value = subprocess.run(
                [getprop, prop_key],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            ).stdout.strip()
        except (OSError, subprocess.TimeoutExpired):
            continue
        if value:
            props[label] = value
    return props


def probe_platform(
    *,
    platform_name: str | None = None,
    termux_prefix: str | None = None,
    termux_version: str | None = None,
    android_build_prop_exists: bool | None = None,
    machine: str | None = None,
    kernel_release: str | None = None,
    android_props: dict[str, str] | None = None,
) -> list[DiagnosticResult]:
    platform_name = platform_name if platform_name is not None else platform_module.system()
    termux_prefix = termux_prefix if termux_prefix is not None else os.environ.get("PREFIX")
    termux_version = (
        termux_version if termux_version is not None else os.environ.get("TERMUX_VERSION")
    )
    if android_build_prop_exists is None:
        android_build_prop_exists = os.path.isfile("/system/build.prop")
    machine = machine if machine is not None else os.uname().machine
    if kernel_release is None:
        try:
            kernel_release = os.uname().release
        except OSError:  # pragma: no cover - uname always works on CPython
            kernel_release = ""
    android_props = android_props if android_props is not None else _android_props()

    from ruach_setup.device import normalize_architecture

    architecture, abi, recognized = normalize_architecture(machine)
    bitness = 64 if struct.calcsize("P") == 8 else 32

    results: list[DiagnosticResult] = []
    results.append(
        result(
            "platform.os",
            Status.PASS,
            message=f"Operating system: {platform_name}",
            system=platform_name,
            kernel=kernel_release or UNKNOWN,
        )
    )

    termux_detected = bool(termux_version) or bool(
        termux_prefix and "com.termux" in termux_prefix
    )
    android_detected = termux_detected or android_build_prop_exists
    results.append(
        result(
            "platform.android",
            Status.PASS,
            severity=Severity.INFO,
            message="Android environment detected" if android_detected else "No Android detected",
            android="yes" if android_detected else "no",
            android_version=android_props.get("android_version", UNKNOWN),
            manufacturer=android_props.get("manufacturer", UNKNOWN),
            model=android_props.get("model", UNKNOWN),
        )
    )
    results.append(
        result(
            "platform.termux",
            Status.PASS,
            message="Termux detected" if termux_detected else "No Termux detected",
            termux="yes" if termux_detected else "no",
            termux_version=termux_version or UNKNOWN,
        )
    )
    results.append(
        result(
            "platform.architecture",
            Status.PASS if recognized else Status.WARN,
            severity=Severity.LOW if recognized else Severity.MEDIUM,
            message=(
                f"Architecture {architecture} ({abi}), {bitness}-bit"
                if recognized
                else f"Unrecognized architecture '{machine}'"
            ),
            architecture=architecture,
            abi=abi,
            machine=machine,
            bitness=str(bitness),
            actions=()
            if recognized
            else ("Record this architecture in a bug report;",),
            technical_reason=(
                f"uname.machine={machine!r} mapped to {architecture}/{abi}"
                if recognized
                else f"uname.machine={machine!r} has no entry in ARCHITECTURE_MAP"
            ),
        )
    )
    return results


# --------------------------------------------------------------------------
# Memory probe (docs/15 §7)


def parse_meminfo(text: str) -> dict[str, int]:
    """Parse /proc/meminfo into a kb-keyed dict of the fields we distinguish."""
    fields: dict[str, int] = {}
    wanted = {
        "MemTotal",
        "MemAvailable",
        "MemFree",
        "Cached",
        "SwapTotal",
        "SwapFree",
        "SwapCached",
    }
    for line in text.splitlines():
        key, _, rest = line.partition(":")
        if key not in wanted:
            continue
        value_text = rest.strip().split()[0] if rest.strip() else ""
        if value_text.isdigit():
            fields[key] = int(value_text)
    return fields


def probe_memory(meminfo_text: str | None = None) -> list[DiagnosticResult]:
    if meminfo_text is None:
        try:
            with open("/proc/meminfo", encoding="utf-8", errors="replace") as handle:
                meminfo_text = handle.read()
        except OSError:
            meminfo_text = ""

    fields = parse_meminfo(meminfo_text) if meminfo_text else {}
    total_kb = fields.get("MemTotal")
    available_kb = fields.get("MemAvailable")
    free_kb = fields.get("MemFree")
    cached_kb = fields.get("Cached")
    swap_total_kb = fields.get("SwapTotal")
    swap_free_kb = fields.get("SwapFree")

    def gib(kb: int | None) -> str:
        return f"{kb / (1024 * 1024):.2f} GB" if kb is not None else UNKNOWN

    results: list[DiagnosticResult] = []
    if total_kb is None:
        results.append(
            result(
                "memory.total",
                Status.UNKNOWN,
                severity=Severity.MEDIUM,
                message="Total RAM could not be determined",
                technical_reason="/proc/meminfo unavailable or unreadable on this system",
                actions=("Memory-dependent decisions will be conservative;",),
            )
        )
    else:
        results.append(
            result(
                "memory.total",
                Status.PASS,
                message=f"RAM total: {gib(total_kb)}",
                total_bytes=str(total_kb * 1024),
            )
        )

    # Available vs free are NOT interchangeable (docs/15 §7): prefer
    # MemAvailable; fall back to MemFree only as a lower bound.
    effective_available = available_kb if available_kb is not None else free_kb
    source = "MemAvailable" if available_kb is not None else ("MemFree" if free_kb is not None else "")
    if effective_available is None:
        results.append(
            result(
                "memory.available",
                Status.UNKNOWN,
                severity=Severity.MEDIUM,
                message="Available RAM could not be determined",
                technical_reason="neither MemAvailable nor MemFree present in meminfo",
            )
        )
    else:
        note = "" if available_kb is not None else " (MemFree lower bound)"
        results.append(
            result(
                "memory.available",
                Status.PASS,
                message=f"RAM available: {gib(effective_available)}{note}",
                available_bytes=str(effective_available * 1024),
                source=source,
            )
        )

    if cached_kb is not None:
        results.append(
            result(
                "memory.cached",
                Status.PASS,
                message=f"Cached memory: {gib(cached_kb)}",
                cached_bytes=str(cached_kb * 1024),
            )
        )

    # Swap configured vs usable are different claims (docs/15 §7).
    if swap_total_kb:
        usable = swap_free_kb
        certainty = (
            "usable amount verified"
            if usable is not None
            else "usable amount unverifiable (Android may restrict swap)"
        )
        results.append(
            result(
                "memory.swap",
                Status.WARN if usable is None else Status.PASS,
                severity=Severity.LOW if usable is None else Severity.INFO,
                message=(
                    f"Swap configured: {gib(swap_total_kb)}; "
                    + (f"usable: {gib(usable)}" if usable is not None else "usable: unknown")
                ),
                technical_reason=certainty,
                swap_total_bytes=str(swap_total_kb * 1024),
                swap_usable_bytes=str(usable * 1024) if usable is not None else UNKNOWN,
            )
        )
    return results


# --------------------------------------------------------------------------
# Storage probe (docs/15 §8)


def probe_storage(paths: dict[str, Path] | None = None) -> list[DiagnosticResult]:
    if paths is None:
        home = Path(os.path.expanduser("~"))
        prefix = os.environ.get("PREFIX")
        paths = {
            "home": home,
            "models": home / ".ruach" / "models",
            "tmp": Path("/tmp") if Path("/tmp").exists() else home,
        }
        if prefix:
            paths["prefix"] = Path(prefix)

    results: list[DiagnosticResult] = []
    for label, path in sorted(paths.items()):
        probe = Path(path)
        while not probe.exists() and probe != probe.parent:
            probe = probe.parent
        try:
            usage = shutil.disk_usage(probe)
        except OSError as error:
            results.append(
                result(
                    f"storage.{label}",
                    Status.UNKNOWN,
                    severity=Severity.MEDIUM,
                    message=f"Storage for {label} could not be measured",
                    technical_reason=f"disk_usage({probe}) failed: {error}",
                )
            )
            continue
        free_gb = usage.free / 1024**3
        results.append(
            result(
                f"storage.{label}",
                Status.PASS if free_gb >= 1 else Status.WARN,
                severity=Severity.INFO if free_gb >= 1 else Severity.HIGH,
                message=f"{label}: {free_gb:.1f} GB available at {probe}",
                path=str(probe),
                free_bytes=str(usage.free),
                total_bytes=str(usage.total),
                filesystem_backs=str(label),
                actions=()
                if free_gb >= 1
                else ("Free up space before installing models;",),
            )
        )
    return results


# --------------------------------------------------------------------------
# Python runtime probe (docs/15 §10)


def probe_python(
    *,
    version: str | None = None,
    implementation: str | None = None,
    pip_available: bool | None = None,
    wheel_platform: str | None = None,
    venv_capable: bool | None = None,
) -> list[DiagnosticResult]:
    version_info = sys.version_info
    version = version if version is not None else (
        f"{version_info.major}.{version_info.minor}.{version_info.micro}"
    )
    implementation = (
        implementation if implementation is not None else platform_module.python_implementation()
    )
    if pip_available is None:
        pip_available = shutil.which("pip") is not None or shutil.which("pip3") is not None
    if wheel_platform is None:
        try:
            wheel_platform = sysconfig.get_platform()
        except (OSError, ValueError):  # pragma: no cover - defensive
            wheel_platform = ""
    if venv_capable is None:
        try:
            import ensurepip  # noqa: F401
            import venv  # noqa: F401

            venv_capable = True
        except ImportError:
            venv_capable = False

    version_ok = version_info >= (3, 11)
    results: list[DiagnosticResult] = [
        result(
            "python.runtime",
            Status.PASS if version_ok else Status.FAIL,
            severity=Severity.INFO if version_ok else Severity.CRITICAL,
            message=f"Python {version} ({implementation})",
            version=version,
            implementation=implementation,
            actions=() if version_ok else ("RUACH requires Python 3.11+;",),
        ),
        result(
            "python.pip",
            Status.PASS if pip_available else Status.WARN,
            severity=Severity.INFO if pip_available else Severity.MEDIUM,
            message="pip available" if pip_available else "pip not found",
            technical_reason="looked for pip/pip3 on PATH",
        ),
        result(
            "python.wheel_platform",
            Status.PASS,
            message=f"Wheel platform tag: {wheel_platform or UNKNOWN}",
            platform_tag=wheel_platform or UNKNOWN,
        ),
        result(
            "python.venv",
            Status.PASS if venv_capable else Status.WARN,
            severity=Severity.INFO if venv_capable else Severity.MEDIUM,
            message="virtual environments supported" if venv_capable else "venv capability limited",
            technical_reason="venv+ensurepip import check",
        ),
    ]
    return results


# --------------------------------------------------------------------------
# Toolchain probe (docs/15 §9)


TOOLCHAIN_TOOLS: tuple[str, ...] = (
    "clang",
    "gcc",
    "make",
    "cmake",
    "ninja",
    "git",
    "rustc",
    "cargo",
)


def first_version_line(output: str) -> str:
    for line in output.splitlines():
        line = line.strip()
        if line:
            return line[:80]
    return ""


def probe_toolchain(
    runner: CommandRunner | None = None,
    lookup: PathLookup | None = None,
    tools: tuple[str, ...] = TOOLCHAIN_TOOLS,
) -> list[DiagnosticResult]:
    runner = runner or _default_runner
    lookup = lookup or _default_lookup
    results: list[DiagnosticResult] = []
    for tool in tools:
        path = lookup(tool)
        if path is None:
            # Missing Rust MUST NOT classify the device as unsupported
            # (docs/15 §9); it only affects capabilities needing Rust.
            severity = Severity.MEDIUM if tool in {"rustc", "cargo"} else Severity.LOW
            results.append(
                result(
                    f"toolchain.{tool}",
                    Status.FAIL,
                    severity=severity,
                    message=f"{tool}: MISSING",
                    technical_reason=f"{tool} not found on PATH",
                )
            )
            continue
        outcome = runner([path, "--version"])
        version = first_version_line(outcome.output) if outcome.ok else ""
        results.append(
            result(
                f"toolchain.{tool}",
                Status.PASS if outcome.ok else Status.WARN,
                message=f"{tool}: PASS" + (f" ({version})" if version else ""),
                path=path,
                version=version or UNKNOWN,
                technical_reason="" if outcome.ok else f"--version failed: {outcome.output[:120]}",
            )
        )
    return results


def compilers_present(results: list[DiagnosticResult]) -> frozenset[str]:
    present: set[str] = set()
    for item in results:
        if item.capability.startswith("toolchain.") and item.status is Status.PASS:
            present.add(item.capability.removeprefix("toolchain."))
    return frozenset(present)


# --------------------------------------------------------------------------
# Network probe (docs/15 §33 offline-first; docs/16 §4 networking)


def probe_network(
    connector: Callable[[tuple[str, int]], bool] | None = None,
    https_check: Callable[[str], bool] | None = None,
) -> list[DiagnosticResult]:
    """Network capability. Failure MUST NOT crash Doctor (docs/15 §33)."""
    if connector is None:

        def connector(address: tuple[str, int]) -> bool:
            import socket

            try:
                with socket.create_connection(address, timeout=3):
                    return True
            except OSError:
                return False

    if https_check is None:

        def https_check(url: str) -> bool:
            import urllib.request

            try:
                request = urllib.request.Request(
                    url, method="HEAD"
                )
                with urllib.request.urlopen(request, timeout=5):
                    return True
            except (OSError, ValueError):
                return False

    dns_ok = connector(("1.1.1.1", 53))
    https_ok = https_check("https://pypi.org/simple/") if dns_ok else False
    return [
        result(
            "network.dns",
            Status.PASS if dns_ok else Status.WARN,
            severity=Severity.INFO if dns_ok else Severity.LOW,
            message="Network reachable" if dns_ok else "No network route detected",
            technical_reason="TCP connect to 1.1.1.1:53 timed out or refused"
            if not dns_ok
            else "",
        ),
        result(
            "network.https",
            Status.PASS if https_ok else Status.WARN,
            severity=Severity.INFO if https_ok else Severity.LOW,
            message="HTTPS reachable" if https_ok else "HTTPS unreachable (downloads blocked)",
            technical_reason="HEAD https://pypi.org/simple/ failed" if not https_ok else "",
        ),
    ]


# --------------------------------------------------------------------------
# Native runtime / inference probe (docs/15 §12-§13)


def probe_native_runtime(
    *,
    binary_path: str | None,
    architecture_supported: bool,
    compiler_set: frozenset[str],
    registry_arch_status: str = "unknown",
) -> tuple[InferenceLevel, DiagnosticResult]:
    """Map measurements to an inference capability level (docs/15 §13).

    Only EXECUTABLE-or-below claims are made here; MODEL_LOADABLE and
    INFERENCE_FUNCTIONAL require explicit runtime checks (--check-runtime /
    --check-inference), never a scan-time guess.
    """
    if binary_path:
        level = InferenceLevel.EXECUTABLE
        message = f"Native runtime binary found: {binary_path}"
        status = Status.PASS
        reason = "executable file located via RuntimeResolver search order"
    elif "clang" in compiler_set or "gcc" in compiler_set:
        build_tools = {"make", "cmake"} & compiler_set
        if build_tools and architecture_supported:
            level = InferenceLevel.BUILDABLE
            status = Status.WARN
            message = "Native runtime not installed but compilation looks viable"
            reason = (
                "C compiler and build tools present; llama.cpp acquisition is "
                "on-device source build (registry); build success is NOT assumed"
            )
        elif registry_arch_status == "experimental":
            level = InferenceLevel.SOURCE_AVAILABLE
            status = Status.WARN
            message = "Compiler present but build viability unproven for this ABI"
            reason = f"registry marks this architecture experimental: {registry_arch_status}"
        else:
            level = InferenceLevel.NOT_TESTED
            status = Status.UNKNOWN
            message = "Native runtime untested on this device"
            reason = "no binary and incomplete build toolchain"
    else:
        level = InferenceLevel.NOT_TESTED
        status = Status.UNKNOWN
        message = "No native runtime binary and no C compiler detected"
        reason = "inference capability cannot be established locally"

    detail = result(
        "runtime.native_inference",
        status,
        severity=Severity.INFO if status is Status.PASS else Severity.MEDIUM,
        message=message,
        technical_reason=reason,
        inference_level=level.value,
        binary=binary_path or "",
    )
    return level, detail


# --------------------------------------------------------------------------
# Model probe (docs/15 §34)


def probe_model(model_path: str | None) -> DiagnosticResult:
    if not model_path:
        return result(
            "model.artifact",
            Status.WARN,
            severity=Severity.LOW,
            message="No model configured yet",
            technical_reason="RUACH_MODEL_PATH unset; setup selects one",
            actions=("Run ./ruach setup to choose a model;",),
        )
    path = Path(model_path).expanduser()
    if not path.is_file():
        return result(
            "model.artifact",
            Status.FAIL,
            severity=Severity.HIGH,
            message=f"Configured model missing: {path}",
            technical_reason="RUACH_MODEL_PATH points at a non-existent file",
            actions=("Re-run ./ruach setup to reinstall the model;",),
        )
    size_mb = path.stat().st_size // (1024 * 1024)
    return result(
        "model.artifact",
        Status.PASS,
        message=f"Model artifact present ({size_mb} MB)",
        path=str(path),
        size_bytes=str(path.stat().st_size),
    )


# --------------------------------------------------------------------------
# Python dependency classification (docs/15 §11, docs/16 §11)


def classify_dependency(
    *,
    importable: bool | None,
    rust_available: bool | None,
    wheel_query: str | None = None,
) -> DependencyState:
    """Pure state machine for one native Python dependency.

    wheel_query, when provided, is an authoritative external answer
    ("AVAILABLE_WHEEL"/"UNAVAILABLE") e.g. from a pip index query.
    Without it, only locally measurable facts are used.
    """
    if wheel_query == "AVAILABLE_WHEEL":
        return DependencyState.AVAILABLE_WHEEL
    if wheel_query == "UNAVAILABLE":
        if rust_available:
            return DependencyState.SOURCE_BUILDABLE
        if rust_available is False:
            return DependencyState.SOURCE_BUILD_BLOCKED
        return DependencyState.UNAVAILABLE
    if importable is True:
        return DependencyState.AVAILABLE_WHEEL
    if importable is False:
        if rust_available is True:
            return DependencyState.SOURCE_BUILDABLE
        if rust_available is False:
            return DependencyState.SOURCE_BUILD_BLOCKED
        return DependencyState.SOURCE_BUILD_REQUIRED
    return DependencyState.UNKNOWN


def probe_python_dependency(
    module_name: str,
    *,
    importable: bool | None = None,
    rust_available: bool | None = None,
    wheel_query: str | None = None,
) -> DiagnosticResult:
    if importable is None:
        try:
            __import__(module_name)
            importable = True
        except ImportError:
            importable = False
    if rust_available is None:
        rust_available = shutil.which("rustc") is not None

    state = classify_dependency(
        importable=importable,
        rust_available=rust_available,
        wheel_query=wheel_query,
    )
    messages = {
        DependencyState.AVAILABLE_WHEEL: f"{module_name}: package available",
        DependencyState.SOURCE_BUILD_REQUIRED: (
            f"{module_name}: no local install; source build required"
        ),
        DependencyState.SOURCE_BUILDABLE: (
            f"{module_name}: no compatible wheel; source build possible (Rust present)"
        ),
        DependencyState.SOURCE_BUILD_BLOCKED: (
            f"{module_name}: no compatible wheel; source build blocked (no Rust toolchain)"
        ),
        DependencyState.UNAVAILABLE: f"{module_name}: unavailable on this device",
        DependencyState.UNKNOWN: f"{module_name}: compatibility unknown",
    }
    status_map = {
        DependencyState.AVAILABLE_WHEEL: Status.PASS,
        DependencyState.SOURCE_BUILDABLE: Status.WARN,
        DependencyState.SOURCE_BUILD_REQUIRED: Status.WARN,
        DependencyState.SOURCE_BUILD_BLOCKED: Status.WARN,
        DependencyState.UNAVAILABLE: Status.FAIL,
        DependencyState.UNKNOWN: Status.UNKNOWN,
    }
    return result(
        f"python.dependency.{module_name}",
        status_map[state],
        severity=Severity.INFO
        if state is DependencyState.AVAILABLE_WHEEL
        else Severity.MEDIUM,
        message=messages[state],
        technical_reason=(
            f"importable={importable}, rustc={'present' if rust_available else 'absent'}, "
            f"wheel_query={wheel_query or 'not performed'}"
        ),
        dependency_state=state.value,
    )


__all__ = [
    "AVAILABLE",
    "UNAVAILABLE",
    "UNKNOWN",
    "CommandOutcome",
    "CommandRunner",
    "DependencyState",
    "DiagnosticResult",
    "InferenceLevel",
    "Status",
    "classify_dependency",
    "compilers_present",
    "first_version_line",
    "inference_rank",
    "parse_meminfo",
    "probe_memory",
    "probe_model",
    "probe_native_runtime",
    "probe_network",
    "probe_platform",
    "probe_python",
    "probe_python_dependency",
    "probe_storage",
    "probe_toolchain",
    "result",
]