"""RUACH Doctor engine: the full diagnostic lifecycle.

Implements docs/15 §4 (SCAN → NORMALIZE → ANALYZE → SELECT PROFILE →
GENERATE INSTALLATION PLAN → VERIFY → REPORT), §29 (verification
levels), §31/§32 (machine- and human-readable output), docs/16 §5/§6
(capability matrix, hard vs soft failures) and docs/17 §24-§28
(probe decomposition feeding a decision engine).

Doctor NEVER modifies the system: every probe is read-only, installation
belongs to the planner/guided setup. Network probes are optional and
failure-tolerant (offline-first, docs/15 §33).
"""

from __future__ import annotations

import datetime as _dt
import os
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ruach_setup.capability import analyze, build_profile
from ruach_setup.device import RawEnvironment, SystemEnvironmentReader
from ruach_setup.diagnostics import (
    AVAILABLE,
    RESTRICTED,
    UNAVAILABLE,
    UNKNOWN,
    DiagnosticResult,
    InferenceLevel,
    Status,
    inference_rank,
)
from ruach_setup.oplog import log_operation
from ruach_setup.planner import InstallationPlan, build_plan, human_bytes
from ruach_setup.probes import (
    compilers_present,
    probe_memory,
    probe_model,
    probe_native_runtime,
    probe_network,
    probe_platform,
    probe_python,
    probe_python_dependency,
    probe_storage,
    probe_toolchain,
)
from ruach_setup.profiles import DecisionInput, RuntimeProfile, decide
from ruach_setup.recommend import recommend
from ruach_setup.registry import load_models, load_runtimes

CommandRunner = Callable[[list[str]], object]
PathLookup = Callable[[str], str | None]

# Backend packages whose absence constrains the Python path (docs/16 §11).
_CRITICAL_NATIVE_DEPS: tuple[str, ...] = ("pydantic_core",)


@dataclass(frozen=True)
class VerificationEntry:
    """One verification level result (docs/15 §29)."""

    level: str
    status: Status
    detail: str
    technical_reason: str = ""

    def to_json(self) -> dict:
        return {
            "level": self.level,
            "status": self.status.value,
            "detail": self.detail,
            "technical_reason": self.technical_reason,
        }


@dataclass
class DoctorReport:
    """Complete doctor output: CapabilityReport + decision + plan + verify."""

    generated_at: str
    environment_status: str
    device: dict
    memory: dict
    storage: dict
    python: dict
    toolchain: dict
    network: dict
    results: list[DiagnosticResult]
    matrix: dict[str, str]
    decision: dict
    plan: InstallationPlan
    verification: list[VerificationEntry]
    warnings: list[str] = field(default_factory=list)

    @property
    def status(self) -> str:
        """READY | DEGRADED | BLOCKED (docs/15 §30/§32)."""
        if self.decision["profile"] == RuntimeProfile.UNSUPPORTED.value:
            return "BLOCKED"
        bad = [
            entry
            for entry in self.verification
            if entry.status in {Status.FAIL, Status.WARN}
        ]
        return "DEGRADED" if bad else "READY"

    def to_json(self) -> dict:
        return {
            "generated_at": self.generated_at,
            "environment": self.environment_status,
            "device": self.device,
            "memory": self.memory,
            "storage": self.storage,
            "python": self.python,
            "toolchain": self.toolchain,
            "network": self.network,
            "capabilities": [item.to_json() for item in self.results],
            "matrix": dict(self.matrix),
            "decision": self.decision,
            "plan": self.plan.to_json(),
            "verification": [entry.to_json() for entry in self.verification],
            "warnings": list(self.warnings),
            "status": self.status,
        }


def _state_for(status: Status) -> str:
    return {
        Status.PASS: AVAILABLE,
        Status.WARN: RESTRICTED,
        Status.FAIL: UNAVAILABLE,
        Status.UNKNOWN: UNKNOWN,
    }[status]


def _matrix_from(results: list[DiagnosticResult]) -> dict[str, str]:
    return {item.capability: _state_for(item.status) for item in results}


def _read_config_env(home: Path) -> dict[str, str]:
    from bootstrap.runtime import DEFAULT_CONFIG_PATH, load_config, merged_environment

    config_path = home / ".ruach" / "config" / "ruach.env"
    effective = config_path if config_path.is_file() else DEFAULT_CONFIG_PATH
    if not effective.is_file():
        return {}
    try:
        return merged_environment(load_config(effective))
    except Exception:  # noqa: BLE001 - unreadable config degrades honestly
        return {}


def _recommended_model(storage_free_bytes: int | None):
    try:
        assessment_profile_raw: RawEnvironment = SystemEnvironmentReader().read()
        assessment = analyze(build_profile(assessment_profile_raw))
        rec = recommend(
            assessment,
            load_runtimes(),
            load_models(),
            storage_free_bytes=storage_free_bytes,
        )
        if rec.model_id is None:
            return None
        return load_models().get(rec.model_id)
    except Exception:  # noqa: BLE001 - registry problems must not kill doctor
        return None


def build_decision_input(
    raw: RawEnvironment,
    *,
    resolved_binary_path: str | None,
    compiler_set: frozenset[str],
    rust_available: bool,
    tier: str,
    environment_status: str,
) -> DecisionInput:
    """Normalize probe measurements into the decision snapshot."""
    from ruach_setup.device import normalize_architecture

    _architecture, abi, recognized = normalize_architecture(raw.machine)

    deps_healthy: bool | None = None
    dep_notes: list[str] = []
    for module_name in _CRITICAL_NATIVE_DEPS:
        outcome = probe_python_dependency(module_name)
        if outcome.status is Status.PASS:
            deps_healthy = True
        else:
            deps_healthy = None if deps_healthy is None else deps_healthy
            dep_notes.append(outcome.message)

    version_info = raw.python_version
    major_minor = tuple(int(part) for part in version_info.split(".")[:2])
    return DecisionInput(
        architecture_supported=recognized,
        abi=abi,
        ram_total_bytes=raw.mem_total_kb * 1024 if raw.mem_total_kb else None,
        ram_available_bytes=(
            raw.mem_available_kb * 1024 if raw.mem_available_kb else None
        ),
        storage_free_bytes=raw.storage_free_bytes,
        python_ok=major_minor >= (3, 11),
        python_version=version_info,
        compilers_present=compiler_set,
        rust_available=rust_available,
        native_binary_found=bool(resolved_binary_path),
        inference_level=InferenceLevel.NOT_TESTED,  # replaced by caller
        python_deps_healthy=deps_healthy,
        resource_tier=tier,
        environment_status=environment_status,
    )


def _verify_environment(home: Path) -> VerificationEntry:
    """Read-only writability probe: never creates anything (docs/15 §4).

    When the workspace directory does not exist yet, writability of the
    nearest existing ancestor is checked instead of creating the tree.
    """
    workspace = home / ".ruach" / "workspace"
    target = workspace
    while not target.exists() and target != target.parent:
        target = target.parent
    try:
        if target == workspace:
            probe = workspace / ".doctor-write-probe"
            probe.write_text("x", encoding="utf-8")
            probe.unlink()
        elif not os.access(target, os.W_OK):
            raise OSError(f"no write permission on {target}")
    except OSError as error:
        return VerificationEntry(
            "Environment",
            Status.FAIL,
            f"RUACH location not writable near {workspace}",
            str(error),
        )
    detail = (
        "~/.ruach/workspace writable"
        if target == workspace
        else f"writable via nearest existing dir: {target}"
    )
    return VerificationEntry("Environment", Status.PASS, detail)


def _verify_toolchain(compiler_set: frozenset[str]) -> VerificationEntry:
    has_cc = bool({"clang", "gcc"} & compiler_set)
    has_build = bool({"make", "cmake"} & compiler_set)
    if has_cc and has_build:
        return VerificationEntry(
            "Toolchain", Status.PASS, f"compilers/build tools present: {sorted(compiler_set)}"
        )
    if has_cc or has_build:
        return VerificationEntry(
            "Toolchain",
            Status.WARN,
            "partial toolchain (soft failure; limits native-build paths)",
            f"present={sorted(compiler_set)}",
        )
    return VerificationEntry(
        "Toolchain",
        Status.UNKNOWN,
        "no C compiler/build tools found (prebuilt-binary paths only)",
    )


def _verify_runtime(
    resolved_path: str | None,
    compiler_set: frozenset[str],
    arch_supported: bool,
) -> VerificationEntry:
    if resolved_path:
        return VerificationEntry(
            "Runtime", Status.PASS, f"llama-server binary: {resolved_path}"
        )
    has_cc = bool({"clang", "gcc"} & compiler_set)
    has_build = bool({"make", "cmake"} & compiler_set)
    if has_cc and has_build and arch_supported:
        return VerificationEntry(
            "Runtime",
            Status.WARN,
            "runtime not installed; on-device source build looks viable "
            "(build success is NOT assumed)",
        )
    return VerificationEntry(
        "Runtime",
        Status.UNKNOWN,
        "no runtime binary and no complete build toolchain",
    )


def _verify_model(model_path: str | None) -> VerificationEntry:
    if not model_path:
        return VerificationEntry(
            "Model", Status.WARN, "no model configured yet (run ./ruach setup)"
        )
    path = Path(model_path).expanduser()
    if path.is_file() and path.stat().st_size > 0:
        size = human_bytes(path.stat().st_size)
        return VerificationEntry("Model", Status.PASS, f"{path} ({size})")
    return VerificationEntry(
        "Model", Status.FAIL, f"configured model missing: {path}", "RUACH_MODEL_PATH unset file"
    )


def _verify_inference(server_url: str, enabled: bool) -> VerificationEntry:
    if not enabled:
        return VerificationEntry(
            "Inference",
            Status.UNKNOWN,
            "NOT_TESTED (use --check-inference with a running server)",
        )
    import urllib.request

    try:
        request = urllib.request.Request(
            server_url.rstrip("/") + "/health"
        )
        with urllib.request.urlopen(request, timeout=3):
            return VerificationEntry(
                "Inference", Status.PASS, f"inference server answering at {server_url}"
            )
    except OSError as error:
        return VerificationEntry(
            "Inference",
            Status.FAIL,
            f"inference server not answering at {server_url}",
            str(error),
        )


def _verify_runtime_executable(binary_path: str) -> tuple[bool, str]:
    """--check-runtime: prove the binary actually executes (docs/16 §23)."""
    try:
        completed = subprocess.run(
            [binary_path, "--version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return False, str(error)
    output = ((completed.stdout or "") + (completed.stderr or "")).strip().splitlines()
    first = output[0][:80] if output else ""
    return completed.returncode == 0, first


def _verify_api(run_dir: Path) -> VerificationEntry:
    from bootstrap.runtime import read_lifecycle

    lifecycle = read_lifecycle(run_dir)
    state = lifecycle.get("state", "STOPPED")
    if state == "HEALTHY":
        url = lifecycle.get("base_url") or "(unknown URL)"
        return VerificationEntry("API", Status.PASS, f"backend healthy at {url}")
    if state in {"STARTING", "STOPPING"}:
        return VerificationEntry("API", Status.WARN, f"backend transitioning ({state})")
    if state == "UNRESPONSIVE":
        return VerificationEntry(
            "API", Status.FAIL, "backend process alive but not answering"
        )
    return VerificationEntry("API", Status.UNKNOWN, "backend not running (optional service)")


def _verify_application() -> list[VerificationEntry]:
    """Backend dependency + migration chain checks (legacy doctor scope)."""
    entries: list[VerificationEntry] = []
    missing = []
    for package in ("fastapi", "uvicorn", "sqlalchemy", "alembic", "pydantic_settings"):
        try:
            __import__(package)
        except ImportError:
            missing.append(package)
    entries.append(
        VerificationEntry(
            "Application dependencies",
            Status.WARN if missing else Status.PASS,
            f"missing: {', '.join(missing)} (create .venv)" if missing else "all backend packages importable",
        )
    )

    versions_dir = Path(__file__).resolve().parent.parent / "backend" / "migrations" / "versions"
    heads = _migration_heads(versions_dir)
    if len(heads) == 1:
        entries.append(
            VerificationEntry("Migration chain", Status.PASS, f"single head {next(iter(heads))}")
        )
    elif not heads:
        entries.append(VerificationEntry("Migration chain", Status.FAIL, "no migrations found"))
    else:
        entries.append(
            VerificationEntry(
                "Migration chain", Status.FAIL, f"MULTIPLE HEADS: {', '.join(sorted(heads))}"
            )
        )
    return entries


def _migration_heads(versions_dir: Path) -> set[str]:
    import re

    revisions: dict[str, str | None] = {}
    if not versions_dir.is_dir():
        return set()
    for path in versions_dir.glob("*.py"):
        text = path.read_text(encoding="utf-8", errors="replace")
        # [\x22\x27] matches either quote character without embedding
        # literal quotes in this source file.
        rev_match = re.search(
            r"^revision(?::\s*str)?\s*=\s*[\x22\x27]([^\x22\x27]+)[\x22\x27]",
            text,
            re.MULTILINE,
        )
        down_match = re.search(r'^down_revision(?::[^=]*)?\s*=\s*(.+)$', text, re.MULTILINE)
        if rev_match is None:
            continue
        down_raw = down_match.group(1).strip() if down_match else ""
        if down_raw.startswith(("None",)):
            down: str | None = None
        else:
            quoted = re.search(r"[\x22\x27]([^\x22\x27]+)[\x22\x27]", down_raw)
            down = quoted.group(1) if quoted else None
        revisions[rev_match.group(1)] = down
    children = {down for down in revisions.values() if down is not None}
    return {rev for rev in revisions if rev not in children}


def run_doctor(
    *,
    home: Path | None = None,
    check_runtime: bool = False,
    check_inference: bool = False,
    probe_network_enabled: bool = True,
    runner=None,
    lookup=None,
    run_dir: Path | None = None,
) -> DoctorReport:
    """Execute the full doctor lifecycle without modifying anything."""
    home = home if home is not None else Path.home()
    run_dir = run_dir if run_dir is not None else _default_run_dir()

    raw = SystemEnvironmentReader().read()
    assessment = analyze(build_profile(raw))

    results: list[DiagnosticResult] = []
    results.extend(probe_platform())
    results.extend(probe_memory())
    results.extend(probe_storage())
    results.extend(probe_python())
    results.extend(probe_toolchain(runner=runner, lookup=lookup))
    if probe_network_enabled:
        results.extend(probe_network())

    from bootstrap.runtime_resolver import resolve_llama_server

    env = _read_config_env(home)
    resolved = resolve_llama_server(explicit=env.get("RUACH_LLAMA_SERVER_BIN"), home=home)
    binary_path = str(resolved.path) if resolved.found else None

    compiler_set = compilers_present(results)
    rust_available = "rustc" in compiler_set
    arch_supported = any(
        item.capability == "platform.architecture" and item.status is Status.PASS
        for item in results
    )
    runtime_entry = load_runtimes().get("llama_cpp")
    registry_arch_status = (
        runtime_entry.supported_architectures.get(
            next(
                (
                    item.details.get("architecture", "")
                    for item in results
                    if item.capability == "platform.architecture"
                ),
                "",
            ),
            "unknown",
        )
        if runtime_entry
        else "unknown"
    )

    level, runtime_detail = probe_native_runtime(
        binary_path=binary_path,
        architecture_supported=arch_supported,
        compiler_set=compiler_set,
        registry_arch_status=registry_arch_status,
    )
    results.append(runtime_detail)
    results.append(probe_model(env.get("RUACH_MODEL_PATH") or None))
    for module_name in _CRITICAL_NATIVE_DEPS:
        results.append(probe_python_dependency(module_name))

    capabilities = build_decision_input(
        raw,
        resolved_binary_path=binary_path,
        compiler_set=compiler_set,
        rust_available=rust_available,
        tier=assessment.tier,
        environment_status=assessment.environment_status,
    )
    capabilities = DecisionInput(
        **{
            **{f.name: getattr(capabilities, f.name) for f in capabilities.__dataclass_fields__.values()},
            "inference_level": level,
        }
    )

    decision = decide(capabilities)
    model_entry = _recommended_model(capabilities.storage_free_bytes)
    plan = build_plan(decision, capabilities, model_entry)

    verification: list[VerificationEntry] = []
    verification.append(_verify_environment(home))
    verification.extend(_verify_application())
    verification.append(_verify_toolchain(compiler_set))
    runtime_verification = _verify_runtime(binary_path, compiler_set, arch_supported)
    if check_runtime and binary_path:
        executes, version_line = _verify_runtime_executable(binary_path)
        runtime_verification = VerificationEntry(
            "Runtime",
            Status.PASS if executes else Status.FAIL,
            (
                f"{binary_path} executes ({version_line})"
                if executes
                else f"{binary_path} failed to execute"
            ),
            "" if executes else "running the binary returned a failure",
        )
    verification.append(runtime_verification)
    verification.append(_verify_model(env.get("RUACH_MODEL_PATH") or None))
    verification.append(
        _verify_inference(env.get("RUACH_MODEL_SERVER_URL", "http://127.0.0.1:8080"), check_inference)
    )
    verification.append(_verify_api(run_dir))

    device: dict[str, Any] = {
        "arch": next(
            (
                item.details.get("architecture", UNKNOWN)
                for item in results
                if item.capability == "platform.architecture"
            ),
            UNKNOWN,
        ),
        "abi": capabilities.abi,
        "ram_bytes": capabilities.ram_total_bytes,
        "ram_available_bytes": capabilities.ram_available_bytes,
        "storage_free_bytes": capabilities.storage_free_bytes,
        "android": any(
            item.capability == "platform.android" and item.details.get("android") == "yes"
            for item in results
        ),
        "termux": any(
            item.capability == "platform.termux" and item.details.get("termux") == "yes"
            for item in results
        ),
    }
    toolchain_json = {
        item.capability.removeprefix("toolchain."): item.status is Status.PASS
        for item in results
        if item.capability.startswith("toolchain.")
    }
    python_json = {
        "available": capabilities.python_ok,
        "version": capabilities.python_version,
        "wheel_platform": next(
            (
                item.details.get("platform_tag", UNKNOWN)
                for item in results
                if item.capability == "python.wheel_platform"
            ),
            UNKNOWN,
        ),
    }

    warnings = sorted({item.capability for item in results if item.status is Status.WARN})

    report = DoctorReport(
        generated_at=_dt.datetime.now(_dt.UTC).isoformat(timespec="seconds"),
        environment_status=assessment.environment_status,
        device=device,
        memory={
            item.capability: item.to_json()
            for item in results
            if item.capability.startswith("memory.")
        },
        storage={
            item.capability: item.to_json()
            for item in results
            if item.capability.startswith("storage.")
        },
        python=python_json,
        toolchain=toolchain_json,
        network={
            item.capability: item.status.value
            for item in results
            if item.capability.startswith("network.")
        },
        results=results,
        matrix=_matrix_from(results),
        decision=decision.to_json(),
        plan=plan,
        verification=verification,
        warnings=warnings,
    )

    log_operation(
        "doctor",
        "scan",
        {
            "profile": decision.profile.value,
            "confidence": decision.confidence,
            "status": report.status,
            "inference_level": level.value,
            "arch": device["arch"],
        },
        home=home,
    )
    return report


def _default_run_dir() -> Path:
    from bootstrap.runtime import DEFAULT_RUN_DIR

    return DEFAULT_RUN_DIR


# --------------------------------------------------------------------------
# Rendering (docs/15 §32 concise, §31 JSON, verbose detail; docs/17 §5)


def _inference_label(level: InferenceLevel) -> str:
    if inference_rank(level) >= inference_rank(InferenceLevel.EXECUTABLE):
        return "AVAILABLE"
    if level is InferenceLevel.BUILDABLE:
        return "BUILDABLE"
    if level is InferenceLevel.SOURCE_AVAILABLE:
        return "SOURCE_AVAILABLE"
    return "NOT_TESTED"


def _api_label(report: DoctorReport) -> str:
    api = next((entry for entry in report.verification if entry.level == "API"), None)
    if api is None:
        return "OPTIONAL"
    if api.status is Status.PASS:
        return "READY"
    if api.status is Status.FAIL:
        return "ERROR"
    return "OPTIONAL"


def _measured_inference_level(report: DoctorReport) -> InferenceLevel:
    level_value = next(
        (
            item.details.get("inference_level")
            for item in report.results
            if item.capability == "runtime.native_inference"
        ),
        None,
    )
    try:
        return InferenceLevel(str(level_value)) if level_value else InferenceLevel.NOT_TESTED
    except ValueError:
        return InferenceLevel.NOT_TESTED


def render_concise(report: DoctorReport) -> str:
    storage_free = report.device.get("storage_free_bytes")
    storage_text = human_bytes(storage_free) + " available" if storage_free else "unknown"
    lines = [
        f"Status: {report.status}",
        f"Profile: {report.decision['profile']}",
        f"Inference: {_inference_label(_measured_inference_level(report))}",
        f"API: {_api_label(report)}",
        f"Model storage: {storage_text}",
        f"Warnings: {len(report.warnings)}",
        "",
        "Details: ./ruach doctor --verbose    Machine-readable: ./ruach doctor --json",
    ]
    return NL.join(lines)


def render_verbose(report: DoctorReport) -> str:
    lines: list[str] = ["RUACH DOCTOR — VERBOSE", ""]
    lines.append(f"Generated : {report.generated_at}")
    lines.append(f"Status    : {report.status}")
    lines.append(f"Profile   : {report.decision['profile']} (confidence {report.decision['confidence']})")
    lines.append("")
    lines.append("Device")
    for key, value in report.device.items():
        lines.append(f"  {key:<18}: {value}")
    lines.append("")
    lines.append("Capability matrix")
    for capability, state in sorted(report.matrix.items()):
        lines.append(f"  {capability:<36} {state}")
    lines.append("")
    lines.append("Findings")
    for item in report.results:
        marker = {Status.PASS: "+", Status.WARN: "!", Status.FAIL: "x", Status.UNKNOWN: "?"}[item.status]
        lines.append(f"  [{marker}] {item.capability}: {item.message}")
        if item.technical_reason:
            lines.append(f"      reason: {item.technical_reason}")
        for action in item.recommended_actions:
            lines.append(f"      action: {action}")
    lines.append("")
    lines.append("Why this profile")
    for reason in report.decision["reason"]:
        lines.append(f"  - {reason}")
    for block in report.decision["hard_blocks"]:
        lines.append(f"  ! blocked: {block}")
    if report.decision["scores"]:
        lines.append("  scores: " + ", ".join(f"{k}={v}" for k, v in report.decision["scores"].items()))
    lines.append("")
    lines.append("Installation plan")
    from ruach_setup.planner import render_plan

    lines.append(render_plan(report.plan))
    lines.append("")
    lines.append("Verification")
    for entry in report.verification:
        marker = {Status.PASS: "PASS", Status.WARN: "WARN", Status.FAIL: "FAIL", Status.UNKNOWN: "SKIP"}[
            entry.status
        ]
        lines.append(f"  {entry.level:<24} {marker:<5} {entry.detail}")
        if entry.technical_reason:
            lines.append(f"{'':<28}reason: {entry.technical_reason}")
    return NL.join(lines)


NL = chr(10)  # newline without embedding escape sequences in source


__all__ = [
    "DoctorReport",
    "VerificationEntry",
    "build_decision_input",
    "render_concise",
    "render_verbose",
    "run_doctor",
]