"""Device detection for RUACH setup.

Detection answers one question only: "What is this device?" It never mutates
the environment — installation decisions belong to the installer (later increment).

All environment access goes through RawEnvironment so tests can construct
values directly without a real Android device.
"""

import os
import platform
import shutil
import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class RawEnvironment:
    platform_name: str
    termux_prefix: str | None
    termux_version: str | None
    android_build_prop_exists: bool
    machine: str
    cpu_cores: int | None
    mem_total_kb: int | None
    mem_available_kb: int | None
    home_path: str
    storage_total_bytes: int | None
    storage_free_bytes: int | None
    python_version: str


def _parse_meminfo(text: str) -> tuple[int | None, int | None]:
    total: int | None = None
    available: int | None = None
    for line in text.splitlines():
        key, _, rest = line.partition(":")
        value_text = rest.strip().split()[0] if rest.strip() else ""
        if not value_text.isdigit():
            continue
        if key == "MemTotal":
            total = int(value_text)
        elif key == "MemAvailable" or (key == "MemFree" and available is None):
            available = int(value_text)
    return total, available


class SystemEnvironmentReader:
    """Reads real values from the running system using stdlib interfaces."""

    def read(self) -> RawEnvironment:
        mem_total = mem_available = None
        try:
            with open("/proc/meminfo", encoding="utf-8", errors="replace") as handle:
                mem_total, mem_available = _parse_meminfo(handle.read())
        except OSError:
            pass

        storage_total = storage_free = None
        try:
            usage = shutil.disk_usage(os.path.expanduser("~"))
            storage_total, storage_free = usage.total, usage.free
        except OSError:
            pass

        version_info = sys.version_info
        return RawEnvironment(
            platform_name=platform.system(),
            termux_prefix=os.environ.get("PREFIX"),
            termux_version=os.environ.get("TERMUX_VERSION"),
            android_build_prop_exists=os.path.isfile("/system/build.prop"),
            machine=os.uname().machine,
            cpu_cores=os.cpu_count(),
            mem_total_kb=mem_total,
            mem_available_kb=mem_available,
            home_path=os.path.expanduser("~"),
            storage_total_bytes=storage_total,
            storage_free_bytes=storage_free,
            python_version=(f"{version_info.major}.{version_info.minor}.{version_info.micro}"),
        )


ARCHITECTURE_MAP = {
    "aarch64": ("arm64", "arm64-v8a"),
    "armv7l": ("arm32", "armeabi-v7a"),
    "armv8l": ("arm32", "armeabi-v7a"),
    "x86_64": ("x86_64", "x86_64"),
    "i686": ("x86", "i386"),
    "i386": ("x86", "i386"),
}


def normalize_architecture(machine: str) -> tuple[str, str, bool]:
    """Return (architecture, abi, is_recognized)."""
    entry = ARCHITECTURE_MAP.get(machine.lower())
    if entry is None:
        return "unknown", "unknown", False
    return entry[0], entry[1], True
