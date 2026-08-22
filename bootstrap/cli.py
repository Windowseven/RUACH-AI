"""RUACH bootstrap CLI.

Development/bootstrap tooling. Reports the truth about the machine it runs
on and never implies macOS behavior proves Android/Termux behavior.
Stdlib-only: safe to run with any system Python ≥ 3.11 via ./ruach.
"""

import argparse
import json
import sys
from pathlib import Path

from ruach_setup.capability import (
    CapabilityAssessment,
    analyze,
    build_profile,
    load_tier_config,
)
from ruach_setup.device import SystemEnvironmentReader
from ruach_setup.recommend import recommend
from ruach_setup.registry import load_models, load_runtimes

APP_VERSION = "0.1.0"
ROOT = Path(__file__).resolve().parent.parent


def _fmt_gib(num_bytes: int | None) -> str:
    if num_bytes is None:
        return "unknown"
    return f"{num_bytes / (1024**3):.1f} GB"


def _environment_label(status: str) -> str:
    return {
        "target_device": "Termux Target Device",
        "development_host": "Development Host",
        "unknown": "Unknown",
    }.get(status, status)


def _print_environment(assessment: CapabilityAssessment) -> None:
    p = assessment.profile
    print("Environment")
    print("─" * 32)
    print(f"Platform       : {p.platform_name}")
    print(f"Android        : {'yes' if p.android_detected else 'no'}")
    print(f"Termux         : {p.termux_version or ('yes' if p.termux_detected else 'no')}")
    print(f"Environment    : {_environment_label(assessment.environment_status)}")
    print(f"Architecture   : {p.architecture} ({p.abi})")
    print(f"CPU cores      : {p.cpu_cores if p.cpu_cores is not None else 'unknown'}")
    print(f"RAM            : {_fmt_gib(p.ram_total_bytes)} total")
    print(f"RAM available  : {_fmt_gib(p.ram_available_bytes)}")
    print(f"Storage        : {_fmt_gib(p.storage_available_bytes)} free")
    print(f"Python         : {p.python_version}")
    print(f"Capability     : {assessment.tier.upper()}")


def _print_recommendation_if_target(assessment: CapabilityAssessment) -> None:
    if assessment.environment_status != "target_device":
        print()
        print("Target:")
        print("  Android + Termux")
        print()
        print("NOTE:")
        print("  This machine is the development host.")
        print("  Target-device compatibility has not yet been verified.")
        return

    rec = recommend(
        assessment,
        load_runtimes(),
        load_models(),
        storage_free_bytes=assessment.profile.storage_available_bytes,
    )
    print()
    print("Recommendation")
    print("─" * 32)
    print(f"Runtime        : {rec.runtime_id}")
    print(f"Model          : {rec.model_id or 'none fits this device'}")
    budget = assessment.safe_memory_budget_bytes
    print(f"Safe memory    : {_fmt_gib(budget)} (ESTIMATE-based)")
    print()
    print("Why:")
    for reason in rec.reasons:
        print(f"  • {reason}")
    if rec.warnings:
        print()
        print("Warnings:")
        for warning in rec.warnings:
            print(f"  ! {warning}")
    if rec.alternatives:
        print()
        print("Alternatives:")
        for model_id, why in rec.alternatives:
            print(f"  - {model_id}: {why}")
    print()
    print("NOTE:")
    print("  Model memory figures are ESTIMATES until the first")
    print("  on-device benchmark records observed values.")


def _check(label: str, ok: bool, detail: str = "") -> bool:
    marker = "✓" if ok else "✗"
    suffix = f" ({detail})" if detail else ""
    print(f"{marker} {label}{suffix}")
    return ok


def cmd_setup(
    install_model: str | None,
    models_root: Path,
    source_url: str | None,
    registry: Path | None,
    assume_yes: bool,
) -> int:
    print("RUACH SETUP")
    print("═" * 32)
    raw = SystemEnvironmentReader().read()
    assessment = analyze(build_profile(raw))
    _print_environment(assessment)
    _print_recommendation_if_target(assessment)

    if install_model is None:
        return 0

    from bootstrap.configgen import env_entries_for_model, write_env
    from bootstrap.installer import InstallError, resolve_model_id
    from bootstrap.installer import install_model as run_install
    from ruach_setup.state import SetupState

    entry = resolve_model_id(install_model, registry)
    if entry is None:
        print()
        print("No installable model resolved for this device.")
        return 1

    print()
    print(f"Model to install : {entry.id} ({entry.parameters}, {entry.quantization})")
    print(f"Download size    : ~{entry.download_size_bytes // (1024**2)} MB [ESTIMATE]")
    print(f"Memory estimate  : ~{entry.estimated_memory_bytes // (1024**2)} MB [ESTIMATE]")
    if not assume_yes:
        answer = input("Continue? [y/N] ").strip().lower()
        if answer not in ("y", "yes"):
            print("Aborted.")
            return 1

    state = SetupState()
    state_path = Path.home() / ".ruach" / "setup_state.json"
    try:
        result = run_install(
            entry.id,
            models_root,
            state,
            state_path,
            source_url_override=source_url,
            registry_path=registry,
        )
    except InstallError as error:
        print(f"INSTALL FAILED: {error}")
        return 1

    status = (
        "already present (verified)"
        if result.already_present
        else ("downloaded (resumed)" if result.resumed else "downloaded")
    )
    print()
    print(f"Model {status}: {result.path}")
    print(f"SHA-256      : {result.sha256}")

    config_entries = env_entries_for_model(
        runtime_id="llama_cpp",
        model_name=entry.family,
        model_path=result.path,
        server_url="http://127.0.0.1:8080",
        timeout_seconds=120.0,
    )
    config_path = write_env(models_root.parent / "config" / "ruach.env", config_entries)
    print(f"Configuration: {config_path}")
    print()
    print("RUACH model stage ready.")
    print("Runtime stage remains blocked pending target-device validation (docs/11).")
    return 0


def cmd_doctor() -> int:
    print("RUACH DOCTOR")
    print("═" * 32)
    healthy = True

    version_ok = sys.version_info >= (3, 11)
    healthy &= _check("Python", version_ok, ".".join(str(v) for v in sys.version_info[:3]))

    healthy &= _check(
        "Repository layout",
        (ROOT / "backend" / "app").is_dir() and (ROOT / "docs").is_dir(),
    )
    healthy &= _check("RUACH source", (ROOT / "ruach_setup").is_dir())

    try:
        config = load_tier_config()
        healthy &= _check(
            "Tier configuration", True, f"reserve={config.reserve_bytes // (1024**2)}MB"
        )
    except (OSError, ValueError, KeyError) as error:
        healthy &= _check("Tier configuration", False, str(error))

    try:
        runtimes = load_runtimes()
        models = load_models()
        healthy &= _check("Registries", True, f"{len(runtimes)} runtime(s), {len(models)} model(s)")
    except (OSError, ValueError, KeyError) as error:
        healthy &= _check("Registries", False, str(error))

    state_file = Path.home() / ".ruach" / "setup_state.json"
    if state_file.is_file():
        try:
            state = json.loads(state_file.read_text(encoding="utf-8"))
            healthy &= _check("Setup state", True, state.get("stage", "?"))
        except ValueError as error:
            healthy &= _check("Setup state", False, f"corrupt: {error}")
    else:
        _check("Setup state", True, "not initialized yet")

    print()
    print("RUACH is healthy." if healthy else "Problems detected.")
    return 0 if healthy else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ruach", description="RUACH local AI setup tool")
    parser.add_argument("--version", action="version", version=f"ruach {APP_VERSION}")
    subparsers = parser.add_subparsers(dest="command", required=True)
    setup_parser = subparsers.add_parser(
        "setup", help="detect environment and recommend configuration"
    )
    setup_parser.add_argument(
        "--install-model",
        nargs="?",
        const="auto",
        default=None,
        metavar="MODEL_ID",
        help="download and verify a model (default: recommended)",
    )
    setup_parser.add_argument(
        "--models-root",
        type=Path,
        default=Path.home() / ".ruach" / "models",
        help="where model artifacts live (default: ~/.ruach/models)",
    )
    setup_parser.add_argument("--source-url", default=None, help=argparse.SUPPRESS)
    setup_parser.add_argument("--registry", type=Path, default=None, help=argparse.SUPPRESS)
    setup_parser.add_argument(
        "--yes", action="store_true", help="assume yes; do not prompt for confirmation"
    )
    subparsers.add_parser("doctor", help="diagnose installation health")

    args = parser.parse_args(argv)
    if args.command == "setup":
        return cmd_setup(
            install_model=args.install_model,
            models_root=args.models_root,
            source_url=args.source_url,
            registry=args.registry,
            assume_yes=args.yes,
        )
    return cmd_doctor()


if __name__ == "__main__":
    sys.exit(main())
