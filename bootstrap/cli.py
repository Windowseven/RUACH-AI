"""RUACH bootstrap CLI.

Development/bootstrap tooling. Reports the truth about the machine it runs
on and never implies macOS behavior proves Android/Termux behavior.
Stdlib-only: safe to run with any system Python ≥ 3.11 via ./ruach.

Doctor/setup/status follow docs/15-17: doctor is read-only diagnostics
(--json/--verbose/--check-runtime/--check-inference); setup plans before
it touches anything (--plan), validates requested modes against device
capabilities (--mode), and runs a guided flow interactively.
"""

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

from bootstrap.runtime import DEFAULT_CONFIG_PATH
from bootstrap.version import __version__
from ruach_setup.capability import (
    CapabilityAssessment,
    analyze,
    build_profile,
)
from ruach_setup.device import SystemEnvironmentReader
from ruach_setup.recommend import recommend
from ruach_setup.registry import load_models, load_runtimes

APP_VERSION = __version__
default_run_dir = Path.home() / ".ruach" / "run"
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


# --------------------------------------------------------------------------
# Setup (docs/15 §24-§28, docs/16 §13-§18, docs/17 §6-§22)


def _setup_plan_only() -> int:
    """./ruach setup --plan — show the plan WITHOUT executing it."""
    from bootstrap.doctor_engine import run_doctor
    from ruach_setup.planner import render_plan

    report = run_doctor(probe_network_enabled=False)
    print("RUACH SETUP — INSTALLATION PLAN (preview only)")
    print("═" * 32)
    print(render_plan(report.plan))
    print()
    print("Why this plan:")
    for reason in report.decision["reason"]:
        print(f"  - {reason}")
    print()
    print("No changes were made. Run ./ruach setup to execute this plan.")
    return 0


def _capabilities_for_mode_validation(assessment: CapabilityAssessment):
    from bootstrap.runtime_resolver import resolve_llama_server
    from ruach_setup.diagnostics import InferenceLevel
    from ruach_setup.profiles import DecisionInput

    profile = assessment.profile
    resolved = resolve_llama_server(home=Path.home())
    compilers = frozenset(
        tool
        for tool in ("clang", "gcc", "make", "cmake", "ninja")
        if shutil.which(tool)
    )
    return DecisionInput(
        architecture_supported=profile.architecture_supported,
        abi=profile.abi,
        ram_total_bytes=profile.ram_total_bytes,
        ram_available_bytes=profile.ram_available_bytes,
        storage_free_bytes=profile.storage_available_bytes,
        python_ok=sys.version_info >= (3, 11),
        python_version=profile.python_version,
        compilers_present=compilers,
        rust_available=bool(shutil.which("rustc")),
        native_binary_found=resolved.found,
        inference_level=(
            InferenceLevel.EXECUTABLE if resolved.found else InferenceLevel.NOT_TESTED
        ),
        resource_tier=assessment.tier,
        environment_status=assessment.environment_status,
    )


def cmd_setup(
    install_model: str | None,
    models_root: Path,
    source_url: str | None,
    registry: Path | None,
    assume_yes: bool,
    plan_only: bool = False,
    non_interactive: bool = False,
    mode: str = "auto",
) -> int:
    if plan_only:
        return _setup_plan_only()

    interactive = not non_interactive and not assume_yes and sys.stdin.isatty()
    if interactive:
        from bootstrap.guided_setup import run_guided_setup

        return run_guided_setup(
            reader=input,
            writer=print,
            interactive=True,
            requested_mode=mode,
            install_model_request=install_model or "auto",
            models_root=models_root,
        )

    # ---- Non-interactive path: deterministic, script-safe, no prompts -----
    print("RUACH SETUP")
    print("═" * 32)
    raw = SystemEnvironmentReader().read()
    assessment = analyze(build_profile(raw))
    _print_environment(assessment)
    _print_recommendation_if_target(assessment)

    if mode != "auto":
        from ruach_setup.profiles import validate_mode

        ok, message, available = validate_mode(
            _capabilities_for_mode_validation(assessment), mode
        )
        if not ok:
            print()
            print(message)
            if available:
                print()
                print("Available modes:")
                for available_mode in available:
                    print(f"  {available_mode}")
            return 2

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


# --------------------------------------------------------------------------
# Doctor (docs/15 §29-§32, docs/16 §17, docs/17 §24-§28)


def cmd_doctor(
    json_output: bool = False,
    verbose: bool = False,
    check_runtime: bool = False,
    check_inference: bool = False,
) -> int:
    """Read-only deep diagnostics. Never modifies the system (docs/15 §4)."""
    from ruach_setup.doctor_engine import doctor, check_functional

    environment = check_functional() if check_runtime or check_inference else doctor()

    if json_output:
        print(json.dumps(environment.to_json(), indent=2))
        return 0 if environment.status == "pass" else 1

    print("RUACH DOCTOR")
    print("═" * 32)
    print(f"  OS       : {environment.os}")
    print(f"  Arch     : {environment.arch}")
    print(f"  CPU      : {environment.cpu}")
    print(f"  RAM      : {environment.ram or 'unknown'}")
    print(f"  Inference: {environment.inference_backend}")
    print(f"  Runtime  : {environment.runtime_backend}")
    print(f"  Target   : {'yes' if environment.target_device else 'no'}")
    print()
    healthy = environment.status == "pass"
    print("RUACH is healthy." if healthy else "Problems detected.")
    return 0 if healthy else 1


def _start_failure(error: Exception) -> int:
    message = str(error)
    print(f"\nx RUACH could not start.\n\nReason:\n  {message}")
    if "model" in message.lower() or "not found in config" in message:
        print(
            """
This usually means setup has not completed.

Recommended:
  [1] Run setup now   -> ./ruach setup
  [2] Diagnostics     -> ./ruach doctor
  [3] Configuration   -> ./ruach config"""
        )
    elif "already running" in message.lower():
        print(
            """
Recommended:
  [1] Check status    -> ./ruach status
  [2] Stop first      -> ./ruach stop"""
        )
    else:
        print(
            """
Recommended:
  [1] Diagnostics     -> ./ruach doctor
  [2] Recent logs     -> ./ruach logs"""
        )
    return 1


def cmd_start(
    config_path: Path,
    run_dir: Path,
    backend_port: int | None,
    stub: bool,
    no_browser: bool,
) -> int:
    from bootstrap.runtime import AlreadyRunning, StartError, start

    print("RUACH START")
    print("═" * 32)
    try:
        stack = start(
            config_path=config_path,
            run_dir=run_dir,
            backend_port=backend_port,
            stub=stub,
            browser=not no_browser,
        )
    except AlreadyRunning as error:
        print("\n! RUACH is already running.")
        print(f"  {error}")
        print(
            "\nWhat next:\n"
            "  Open the local interface shown by: ./ruach status\n"
            "  Or stop it first:                  ./ruach stop"
        )
        return 1
    except StartError as error:
        return _start_failure(error)

    print(
        f"""
  API                  ok
  Database             migrated
  Inference runtime    {"stub (development)" if stub else "ready"}
  Model                loaded
  Security             active

╔══════════════════════════════════════════════╗
║              RUACH IS READY                  ║
╚══════════════════════════════════════════════╝

Local interface:

  {stack.ui_url}

Next step:
  Open the address above in your browser to start
  chatting with RUACH. File actions it proposes
  will ask for your approval before executing.

Useful commands (run in another terminal):
  ./ruach status
  ./ruach logs
  ./ruach stop
  ./ruach help
"""
    )
    print("Press Ctrl+C to stop.")

    print(f"[start] ready          : {stack.ui_url}")
    print("Press Ctrl+C to stop.")
    try:
        stack.backend.wait()
        if stack.backend.returncode not in (0, None):
            from bootstrap.runtime import record_failed

            record_failed(
                stack.run_dir,
                f"backend exited with code {stack.backend.returncode}",
            )
    except KeyboardInterrupt:
        print()
    finally:
        stack.shutdown()
        print("[stop] RUACH stopped.")
    return 0


def cmd_stop(run_dir: Path) -> int:
    from bootstrap.runtime import stop

    return stop(run_dir=run_dir)


def _effective_env() -> dict[str, str]:
    from bootstrap.runtime import load_config, merged_environment

    if DEFAULT_CONFIG_PATH.is_file():
        try:
            return merged_environment(load_config(DEFAULT_CONFIG_PATH))
        except Exception:  # noqa: BLE001 - unreadable config degrades honestly
            return {}
    return {}


def _render_status_human(state: dict) -> int:
    """Human-readable status block (docs/16 §19)."""
    lifecycle = state.get("lifecycle", {}) if isinstance(state, dict) else {}
    backend = state.get("backend", {}) if isinstance(state, dict) else {}
    lifecycle_state = lifecycle.get("state", "STOPPED")
    api_label = {
        "HEALTHY": "READY",
        "UNRESPONSIVE": "ERROR",
        "STARTING": "STARTING",
        "STOPPING": "STOPPING",
    }.get(lifecycle_state, "STOPPED")

    env = _effective_env()
    runtime_kind = env.get("RUACH_MODEL_RUNTIME", "llama_cpp")
    model_path_text = env.get("RUACH_MODEL_PATH", "")
    model_path = Path(model_path_text).expanduser() if model_path_text else None
    model_ok = bool(model_path and model_path.is_file())
    if runtime_kind == "stub":
        model_label = "(deterministic stub)"
    elif model_ok:
        model_label = model_path.name  # type: ignore[union-attr]
    else:
        model_label = "not configured"
    inference_label = (
        "READY" if (model_ok or runtime_kind == "stub") else "NOT READY"
    )

    storage_label = "OK"
    try:
        free = shutil.disk_usage(Path.home()).free
        storage_label = "OK" if free > 1024**3 else "LOW"
    except OSError:
        storage_label = "UNKNOWN"

    backend_running = bool(backend.get("running"))
    if backend_running and api_label == "READY" and inference_label == "READY":
        overall = "READY"
    elif backend_running:
        overall = "DEGRADED"
    else:
        overall = "STOPPED"

    print("RUACH STATUS")
    print()
    print(f"Runtime       : {runtime_kind}")
    print(f"Backend       : {'READY' if backend_running else 'STOPPED'}")
    print(f"Inference     : {inference_label}")
    print(f"Model         : {model_label}")
    print(f"API           : {api_label}")
    print(f"Storage       : {storage_label}")
    print()
    print(f"Overall       : {overall}")
    return 0 if backend_running else 1


def cmd_status(run_dir: Path, json_output: bool = False) -> int:
    from bootstrap.runtime import status as runtime_status

    state = runtime_status(run_dir=run_dir)
    if json_output:
        print(json.dumps(state, indent=2))
        backend_raw = state.get("backend") if isinstance(state, dict) else None
        backend_running = (
            bool(backend_raw.get("running")) if isinstance(backend_raw, dict) else False
        )
        return 0 if backend_running else 1
    return _render_status_human(state)


def cmd_verify(live: bool) -> int:
    from bootstrap.verify import verify

    print("RUACH VERIFY — MVP GATE")
    print("═" * 32)
    return verify(include_live=live)


def _guided_home() -> int:
    """Bare `./ruach` — the state-driven, self-discovering entrypoint."""
    from bootstrap.cli_state import resolve_state
    from bootstrap.guided import run_guided

    interactive = sys.stdin.isatty()

    def open_url(url: str) -> None:
        from bootstrap.browser import launch_url

        launch_url(url)

    return run_guided(
        interactive=interactive,
        reader=input,
        writer=print,
        resolver=lambda: resolve_state(),
        version=__version__,
        on_setup=lambda: cmd_setup(
            install_model="auto",
            models_root=Path.home() / ".ruach" / "models",
            source_url=None,
            registry=None,
            assume_yes=False,
        ),
        on_start=lambda: cmd_start(DEFAULT_CONFIG_PATH, default_run_dir, None, False, False),
        on_stop=lambda: cmd_stop(default_run_dir),
        on_status=lambda: cmd_status(default_run_dir),
        on_verify=lambda: cmd_verify(False),
        on_doctor=cmd_doctor,
        on_logs=lambda: cmd_logs(default_run_dir, 40),
        on_config=cmd_config,
        on_model=cmd_model,
        on_help=cmd_help,
        open_url=open_url,
    )


def cmd_logs(run_dir: Path, lines: int) -> int:
    healthy = True
    for name in ("backend.log", "model_server.log"):
        path = run_dir / name
        if not path.is_file():
            print(f"[logs] {name}: no log yet (start RUACH first)")
            healthy = False
            continue
        print(f"[logs] {name} (last {lines} lines) {'─' * 8}")
        tail = path.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:]
        print("\n".join(tail) if tail else "(empty)")
        print()
    if not healthy:
        print("Recommended:\n  ./ruach start")
    return 0


def cmd_config() -> int:
    from bootstrap.runtime import DEFAULT_CONFIG_PATH, load_config, merged_environment

    sources = {}
    if DEFAULT_CONFIG_PATH.is_file():
        sources.update(load_config(DEFAULT_CONFIG_PATH))
    effective = merged_environment(sources)
    relevant = {
        key: value
        for key, value in effective.items()
        if key.startswith("RUACH_") or key in sources
    }
    print("RUACH EFFECTIVE CONFIGURATION")
    print("═" * 32)
    if not relevant:
        print("(no RUACH configuration found)")
        print("Recommended:\n  ./ruach setup")
        return 1
    for key in sorted(relevant):
        origin = "env override" if os.environ.get(key) else "config file"
        print(f"  {key:<36} = {relevant[key]}  [{origin}]")
    print(f"\nSource file: {DEFAULT_CONFIG_PATH}")
    return 0


def cmd_model() -> int:
    from bootstrap.runtime import (
        DEFAULT_CONFIG_PATH,
        load_config,
        merged_environment,
    )
    from bootstrap.runtime_resolver import (
        configured_binary_override,
        resolve_llama_server,
    )

    env = merged_environment(load_config(DEFAULT_CONFIG_PATH) if DEFAULT_CONFIG_PATH.is_file() else {})
    print("RUACH MODEL INFORMATION")
    print("═" * 32)
    runtime_kind = env.get("RUACH_MODEL_RUNTIME", "llama_cpp")
    print(f"  Runtime         : {runtime_kind}")
    model_path = Path(env.get("RUACH_MODEL_PATH", "")).expanduser()
    exists = model_path.is_file()
    size_gb = model_path.stat().st_size / 1e9 if exists else 0
    state = f"{model_path} ({size_gb:.2f} GB)" if exists else f"{model_path or '(unset)'} — MISSING"
    print(f"  Model           : {state}")
    resolved = resolve_llama_server(explicit=configured_binary_override(env))
    binary = str(resolved.path) if resolved.found else "not found"
    source = resolved.source if resolved.found else ""
    print(f"  Engine binary   : {binary}" + (f"  [source: {source}]" if source else ""))
    print(f"  Server URL      : {env.get('RUACH_MODEL_SERVER_URL', '(default)')}")
    if not exists and runtime_kind != "stub":
        print("\nRecommended:\n  ./ruach setup")
        return 1
    return 0


HELP_SECTIONS: list[tuple[str, list[tuple[str, str]]]] = [
    (
        "Getting Started",
        [
            ("setup", "Set up RUACH for the first time (guided; resumable)."),
            ("start", "Start RUACH and its local AI runtime."),
            ("stop", "Stop the running RUACH instance."),
            ("restart", "Restart RUACH."),
        ],
    ),
    (
        "System",
        [
            ("status", "Show the current RUACH status."),
            ("verify", "Run the full installation gate (--live adds real-model smoke)."),
            ("doctor", "Diagnose common problems (--verbose/--json for detail)."),
            ("probe", "Record a device benchmark (docs/13)."),
        ],
    ),
    (
        "Configuration",
        [
            ("config", "View effective configuration."),
            ("model", "View configured model information."),
        ],
    ),
    (
        "Maintenance",
        [
            ("logs", "View recent runtime logs (--lines N)."),
        ],
    ),
    (
        "Help",
        [
            ("help", "Show this guide."),
            ("version", "Show RUACH version."),
        ],
    ),
]


def cmd_help() -> int:
    print("RUACH COMMANDS")
    for title, entries in HELP_SECTIONS:
        print(f"\n{title}\n{'─' * max(4, len(title))}")
        for name, description in entries:
            print(f"  ./ruach {name:<8} {description}")
    print(
        """

Examples
────────
  First time     : ./ruach
  Start          : ./ruach start
  Check status   : ./ruach status
  Diagnose       : ./ruach doctor
  Stop           : ./ruach stop"""
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ruach", description="RUACH local AI setup tool")
    parser.add_argument("--version", action="version", version=f"ruach {APP_VERSION}")
    subparsers = parser.add_subparsers(dest="command")
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
    setup_parser.add_argument(
        "--plan",
        action="store_true",
        help="show the installation plan without executing anything",
    )
    setup_parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="never prompt; deterministic defaults (automation-safe)",
    )
    setup_parser.add_argument(
        "--mode",
        default="auto",
        choices=["auto", "hybrid", "native", "python", "compatibility", "stub"],
        help="requested installation mode (validated against device capabilities)",
    )

    doctor_parser = subparsers.add_parser("doctor", help="diagnose installation health")
    doctor_parser.add_argument(
        "--json", dest="doctor_json", action="store_true", help="machine-readable output"
    )
    doctor_parser.add_argument(
        "--verbose", action="store_true", help="full technical detail"
    )
    doctor_parser.add_argument(
        "--check-runtime",
        action="store_true",
        help="also verify the llama-server binary executes",
    )
    doctor_parser.add_argument(
        "--check-inference",
        action="store_true",
        help="also query the running inference server health endpoint",
    )

    start_parser = subparsers.add_parser(
        "start", help="start the local stack (model runtime if configured + UI/API)"
    )
    start_parser.add_argument(
        "--config", type=Path, default=Path.home() / ".ruach" / "config" / "ruach.env"
    )
    start_parser.add_argument("--run-dir", type=Path, default=default_run_dir)
    start_parser.add_argument("--port", type=int, default=None, help="backend port override")
    start_parser.add_argument(
        "--stub", action="store_true", help="use the deterministic stub model runtime"
    )
    start_parser.add_argument("--no-browser", action="store_true")

    stop_parser = subparsers.add_parser("stop", help="stop the running stack")
    stop_parser.add_argument("--run-dir", type=Path, default=default_run_dir)

    status_parser = subparsers.add_parser("status", help="show stack process state")
    status_parser.add_argument("--run-dir", type=Path, default=default_run_dir)
    status_parser.add_argument(
        "--json", dest="status_json", action="store_true", help="machine-readable output"
    )

    verify_parser = subparsers.add_parser(
        "verify", help="run the scripted fresh-environment MVP gate"
    )
    verify_parser.add_argument(
        "--live",
        action="store_true",
        help="also run the real-model smoke stage (slow; needs installed model)",
    )

    probe_parser = subparsers.add_parser(
        "probe",
        help="record an honest device-readiness benchmark (stdlib-only; runs on any host)",
    )
    probe_parser.add_argument(
        "--inference-url",
        default="",
        help="running llama-server URL (default: generated config / skip)",
    )
    probe_parser.add_argument("--quick", type=int, default=5, help="one-token completions")
    probe_parser.add_argument("--real", type=int, default=3, help="64-token completions")

    subparsers.add_parser("version", help="print the product version")
    subparsers.add_parser(
        "help", help="learn what RUACH can do (human-friendly guide)"
    )
    restart_parser = subparsers.add_parser(
        "restart", help="stop then start (foreground, like start)"
    )
    restart_parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    restart_parser.add_argument("--run-dir", type=Path, default=default_run_dir)
    restart_parser.add_argument("--port", type=int, default=None)
    restart_parser.add_argument("--stub", action="store_true")

    logs_parser = subparsers.add_parser("logs", help="view recent runtime logs")
    logs_parser.add_argument("--run-dir", type=Path, default=default_run_dir)
    logs_parser.add_argument("--lines", type=int, default=40)

    subparsers.add_parser("config", help="view effective configuration")
    subparsers.add_parser("model", help="view configured model information")

    args = parser.parse_args(argv)
    if args.command is None:
        return _guided_home()
    if args.command == "setup":
        return cmd_setup(
            install_model=args.install_model,
            models_root=args.models_root,
            source_url=args.source_url,
            registry=args.registry,
            assume_yes=args.yes,
            plan_only=args.plan,
            non_interactive=args.non_interactive,
            mode=args.mode,
        )
    if args.command == "doctor":
        return cmd_doctor(
            json_output=args.doctor_json,
            verbose=args.verbose,
            check_runtime=args.check_runtime,
            check_inference=args.check_inference,
        )
    if args.command == "start":
        return cmd_start(args.config, args.run_dir, args.port, args.stub, args.no_browser)
    if args.command == "stop":
        return cmd_stop(args.run_dir)
    if args.command == "status":
        return cmd_status(args.run_dir, json_output=args.status_json)
    if args.command == "verify":
        return cmd_verify(args.live)
    if args.command == "probe":
        from bootstrap.probe import run_probe

        run_probe(
            inference_url=args.inference_url,
            quick=args.quick,
            real=args.real,
        )
        return 0
    if args.command == "version":
        from bootstrap.version import __version__

        print(f"RUACH v{__version__}")
        return 0
    if args.command == "help":
        return cmd_help()
    if args.command == "restart":
        cmd_stop(args.run_dir)
        return cmd_start(args.config, args.run_dir, args.port, args.stub, no_browser=False)
    if args.command == "logs":
        return cmd_logs(args.run_dir, args.lines)
    if args.command == "config":
        return cmd_config()
    if args.command == "model":
        return cmd_model()
    return cmd_doctor()


if __name__ == "__main__":
    sys.exit(main())