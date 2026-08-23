"""Device readiness probe (`ruach probe`) — instruments, not guesses.

Collects a benchmark/evidence record for the CURRENT machine. Runs
anywhere Python runs (macOS dev host now, Termux target later) and never
invents values: every section reports status measured | unavailable |
skipped with the reason. Output lands in ~/.ruach/benchmarks/ as JSON so
the Target Device Readiness Gate (docs/13) compares records, not vibes.

Stdlib-only by design: the whole point is running it on the target before
heavy dependencies are proven there.
"""

from __future__ import annotations

import argparse
import json
import platform
import sqlite3
import statistics
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

BACKEND_PACKAGES = (
    "fastapi",
    "uvicorn",
    "sqlalchemy",
    "alembic",
    "pydantic_core",
    "pydantic_settings",
    "httpx",
)

SCHEMA_VERSION = 1


def _section(status: str, data: object = None, reason: str = "") -> dict:
    return {"status": status, "data": data, "reason": reason}


def collect_environment() -> dict:
    try:
        from ruach_setup.capability import build_profile
        from ruach_setup.device import SystemEnvironmentReader

        profile = build_profile(SystemEnvironmentReader().read())
        data = {
            "platform_name": profile.platform_name,
            "android_detected": profile.android_detected,
            "termux_detected": profile.termux_detected,
            "architecture": profile.architecture,
            "abi": profile.abi,
            "cpu_cores": profile.cpu_cores,
            "ram_total_bytes": profile.ram_total_bytes,
            "ram_available_bytes": profile.ram_available_bytes,
            "storage_available_bytes": profile.storage_available_bytes,
        }
        # Honesty over optimism: a section that could not read some fields
        # is PARTIAL, not measured — downstream decisions must know.
        unread = sorted(k for k, v in data.items() if v is None)
        if unread == list(data):
            return _section("unavailable", reason="no fields readable on this platform")
        if unread:
            return _section(
                "measured",
                {**data, "_unreadable_fields": unread},
                reason=f"unreadable: {', '.join(unread)}",
            )
        return _section("measured", data)
    except Exception as error:  # noqa: BLE001 - probe reports, never crashes
        return _section("unavailable", reason=f"{type(error).__name__}: {error}")


def collect_python() -> dict:
    return _section(
        "measured",
        {
            "version": platform.python_version(),
            "implementation": platform.python_implementation(),
            "executable": sys.executable,
        },
    )


def collect_dependencies() -> dict:
    results = {}
    for package in BACKEND_PACKAGES:
        try:
            module = __import__(package)
            version = getattr(module, "__version__", None)
            results[package] = {"status": "measured", "version": version}
        except Exception as error:  # noqa: BLE001
            results[package] = {
                "status": "unavailable",
                "reason": f"{type(error).__name__}: {error}",
            }
    missing = [name for name, item in results.items() if item["status"] != "measured"]
    return _section("measured", results, reason=f"missing: {', '.join(missing)}" if missing else "")


def collect_sqlite() -> dict:
    try:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            connection = sqlite3.connect(str(Path(tmp) / "probe.db"))
            version, *_ = connection.execute("select sqlite_version()").fetchone()
            # WAL is only meaningful for file-backed databases
            mode, *_ = connection.execute("pragma journal_mode=wal").fetchone()
            connection.execute("pragma foreign_keys=on")
            foreign_keys, *_ = connection.execute("pragma foreign_keys").fetchone()
            connection.close()
        return _section(
            "measured",
            {
                "sqlite_version": version,
                "wal_supported": str(mode).lower() == "wal",
                "foreign_keys_bindable": bool(foreign_keys),
            },
        )
    except sqlite3.Error as error:
        return _section("unavailable", reason=str(error))


def collect_runtime(env: dict[str, str]) -> dict:
    from bootstrap.runtime_resolver import configured_binary_override, resolve_llama_server

    resolved = resolve_llama_server(explicit=configured_binary_override(env))
    if not resolved.found or resolved.path is None:
        return _section("unavailable", reason="llama-server not found (config/user/project/PATH)")
    stat = resolved.path.stat()
    return _section(
        "measured",
        {
            "path": str(resolved.path),
            "source": resolved.source,
            "size_bytes": stat.st_size,
        },
    )


def collect_model_artifact(env: dict[str, str]) -> dict:
    raw = env.get("RUACH_MODEL_PATH", "").strip()
    if not raw:
        return _section("skipped", reason="RUACH_MODEL_PATH not configured")
    path = Path(raw).expanduser()
    if not path.is_file():
        return _section("unavailable", reason=f"missing file: {path}")
    return _section("measured", {"path": str(path), "size_bytes": path.stat().st_size})


def _completion(base_url: str, timeout: float, max_tokens: int, prompt: str) -> tuple[float, int | None]:
    url = base_url.rstrip("/") + "/v1/chat/completions"
    payload = json.dumps(
        {
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
    ).encode()
    request = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    started = time.monotonic()
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = json.loads(response.read())
    elapsed = time.monotonic() - started
    usage = body.get("usage") or {}
    tokens = usage.get("completion_tokens")
    return elapsed, tokens if isinstance(tokens, int) else None


def _percentiles(values: list[float]) -> dict:
    ordered = sorted(values)
    def pct(fraction: float) -> float:
        index = min(len(ordered) - 1, max(0, round(fraction * (len(ordered) - 1))))
        return round(ordered[index], 3)
    return {
        "min_s": round(ordered[0], 3),
        "p50_s": pct(0.50),
        "p95_s": pct(0.95),
        "max_s": round(ordered[-1], 3),
        "mean_s": round(statistics.fmean(ordered), 3),
    }


def collect_inference_latency(url: str, quick: int, real: int) -> dict:
    base = url.rstrip("/")
    try:
        elapsed_first, _tokens_first = _completion(
            base, timeout=300.0, max_tokens=1, prompt="ping"
        )
        first_token_s = round(elapsed_first, 3)
    except (urllib.error.URLError, OSError, ValueError) as error:
        return _section(
            "skipped",
            reason=f"inference endpoint unreachable at {base}: {error}",
        )

    one_token = []
    one_token_tps = []
    for _ in range(max(1, quick)):
        seconds, tokens = _completion(base, timeout=300.0, max_tokens=1, prompt="ping")
        one_token.append(seconds)
        if tokens:
            one_token_tps.append(round(tokens / seconds, 2))

    sixty_four = []
    tps_64 = []
    for _ in range(max(1, real)):
        seconds, tokens = _completion(
            base,
            timeout=600.0,
            max_tokens=64,
            prompt="Summarize what a local AI assistant is.",
        )
        sixty_four.append(seconds)
        if tokens:
            tps_64.append(round(tokens / seconds, 2))

    return _section(
        "measured",
        {
            "endpoint": base + "/v1/chat/completions",
            "first_token_after_warm_call_s": first_token_s,
            "one_token_completions": _percentiles(one_token),
            "one_token_tokens_per_second": one_token_tps or None,
            "sixtyfour_token_completions": _percentiles(sixty_four),
            "sixtyfour_token_tokens_per_second": tps_64 or None,
        },
    )


def collect_process_lifecycle() -> dict:
    """Validates PID-liveness assumptions ON THIS PLATFORM. Cannot simulate
    Android's phantom-process reaper; battery/thermal fields stay manual."""
    try:
        child = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        child.kill()
        child.wait(timeout=10)
        reaped = child.poll() is not None
        return _section(
            "measured",
            {
                "sigkill_reap_detected": reaped,
                "note": (
                    "Android phantom-process killing of BACKGROUND processes "
                    "cannot be simulated here; observe manually during "
                    "Termux validation."
                ),
            },
        )
    except OSError as error:
        return _section("unavailable", reason=str(error))


def collect_manual_fields() -> dict:
    """Fields no script can honestly fill on this platform. Recorded as
    explicit nulls with instructions so the validation session fills them."""
    return _section(
        "skipped",
        data={
            "battery_behavior_during_inference": None,
            "thermal_throttling_observed": None,
            "background_reaping_observed": None,
            "installation_ux_notes": None,
        },
        reason=(
            "manual observation required on target: run inference ~5 min, "
            "watch temperature/battery, background the app, check processes"
        ),
    )


def collect_storage_paths(home: Path | None = None) -> dict:
    home = home if home is not None else Path.home()
    results = {}
    for label, path in {
        "config_dir": home / ".ruach" / "config",
        "data_dir": home / ".ruach" / "data",
        "workspace_dir": home / ".ruach" / "workspace",
        "run_dir": home / ".ruach" / "run",
        "benchmarks_dir": home / ".ruach" / "benchmarks",
    }.items():
        try:
            path.mkdir(parents=True, exist_ok=True)
            probe = path / ".probe-write"
            probe.write_text("x", encoding="utf-8")
            probe.unlink()
            results[label] = {"status": "measured", "path": str(path), "writable": True}
        except OSError as error:
            results[label] = {
                "status": "unavailable",
                "path": str(path),
                "reason": str(error),
            }
    return _section("measured", results)


def run_probe(
    *,
    inference_url: str = "",
    quick: int = 5,
    real: int = 3,
    echo=print,
) -> Path:
    from bootstrap.runtime import DEFAULT_CONFIG_PATH, load_config, merged_environment

    # Full config merge (process env wins over generated file), exactly as
    # the orchestrating CLI sees it — the probe must not know fewer keys
    # than the product does.
    env = merged_environment(
        load_config(DEFAULT_CONFIG_PATH) if DEFAULT_CONFIG_PATH.is_file() else {}
    )
    url = inference_url or env.get("RUACH_MODEL_SERVER_URL", "")

    report: dict = {
        "schema_version": SCHEMA_VERSION,
        "recorded_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "environment_sections": {
            "device_profile": collect_environment(),
            "python": collect_python(),
            "backend_dependencies": collect_dependencies(),
            "sqlite": collect_sqlite(),
            "runtime_binary": collect_runtime(env),
            "model_artifact": collect_model_artifact(env),
            "storage_paths": collect_storage_paths(),
            "process_lifecycle_probe": collect_process_lifecycle(),
            "manual_target_fields": collect_manual_fields(),
        },
    }
    if url:
        report["environment_sections"]["inference_latency"] = collect_inference_latency(
            url, quick=quick, real=real
        )
    else:
        report["environment_sections"]["inference_latency"] = _section(
            "skipped", reason="no inference endpoint configured (start the stack or pass --inference-url)"
        )

    out_dir = Path.home() / ".ruach" / "benchmarks"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out_path = out_dir / f"probe-{stamp}.json"
    out_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    for name, section in report["environment_sections"].items():
        detail = f" — {section['reason']}" if section.get("reason") else ""
        echo(f"[probe] {name:<26} {section['status']}{detail}")
    echo(f"[probe] record written : {out_path}")
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ruach-probe",
        description="record an honest device-readiness benchmark (stdlib-only)",
    )
    parser.add_argument("--inference-url", default="", help="running llama-server URL")
    parser.add_argument("--quick", type=int, default=5, help="one-token completions")
    parser.add_argument("--real", type=int, default=3, help="64-token completions")
    args = parser.parse_args(argv)
    run_probe(inference_url=args.inference_url, quick=args.quick, real=args.real)
    return 0


if __name__ == "__main__":
    sys.exit(main())
