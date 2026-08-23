"""RUACH bootstrap CLI.

Development/bootstrap tooling. Reports the truth about the machine it runs
on and never implies macOS behavior proves Android/Termux behavior.
Stdlib-only: safe to run with any system Python ≥ 3.11 via ./ruach.
"""

import argparse
import json
import os
import sys
from pathlib import Path

from bootstrap.runtime import DEFAULT_CONFIG_PATH
from bootstrap.version import __version__
from ruach_setup.capability import (
    CapabilityAssessment,
    analyze,
    build_profile,
    load_tier_config,
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
    print("── application ──")
    healthy &= _check_application()

    print()
    print("── runtime configuration ──")
    healthy &= _check_runtime_config()

    print()
    print("RUACH is healthy." if healthy else "Problems detected.")
    return 0 if healthy else 1


_BACKEND_PACKAGES = ("fastapi", "uvicorn", "sqlalchemy", "alembic", "pydantic_settings")


def _check_application() -> bool:
    """Backend deps + migration state. Honest: missing is reported, never hidden."""
    healthy = True
    missing = []
    for package in _BACKEND_PACKAGES:
        try:
            __import__(package)
        except ImportError:
            missing.append(package)
    if missing:
        healthy &= _check(
            "Backend dependencies", False, f"missing: {', '.join(missing)} (create .venv)"
        )
    else:
        healthy &= _check("Backend dependencies", True)

    versions_dir = ROOT / "backend" / "migrations" / "versions"
    heads = _migration_heads(versions_dir)
    if len(heads) == 1:
        healthy &= _check("Migration chain", True, f"single head {next(iter(heads))}")
    elif not heads:
        healthy &= _check("Migration chain", False, "no migrations found")
    else:
        healthy &= _check(
            "Migration chain", False, f"MULTIPLE HEADS: {', '.join(sorted(heads))}"
        )

    db_path = Path.home() / ".ruach" / "data" / "ruach.db"
    if not db_path.exists():
        _check("Database", True, "not created yet (first `ruach start` migrates it)")
        return healthy
    applied = _applied_migration(db_path)
    if applied is None:
        healthy &= _check("Database schema", False, "no alembic_version; boot will refuse")
    elif len(heads) == 1 and applied != next(iter(heads)):
        healthy &= _check(
            "Database schema", False, f"at {applied}, head is {next(iter(heads))}; run alembic upgrade"
        )
    else:
        healthy &= _check("Database schema", True, f"at head {applied}")
    return healthy


def _migration_heads(versions_dir: Path) -> set[str]:
    """Parse revision/down_revision links without importing alembic."""
    import re

    revisions: dict[str, str | None] = {}
    if not versions_dir.is_dir():
        return set()
    for path in versions_dir.glob("*.py"):
        text = path.read_text(encoding="utf-8", errors="replace")
        rev_match = re.search(r'^revision(?::\s*str)?\s*=\s*["\']([^"\']+)["\']', text, re.MULTILINE)
        down_match = re.search(r'^down_revision(?::[^=]*)?\s*=\s*(.+)$', text, re.MULTILINE)
        if rev_match is None:
            continue
        down_raw = down_match.group(1).strip() if down_match else ""
        if down_raw.startswith(("None",)):
            down: str | None = None
        else:
            quoted = re.search(r'["\']([^"\']+)["\']', down_raw)
            down = quoted.group(1) if quoted else None
        revisions[rev_match.group(1)] = down
    children = {down for down in revisions.values() if down is not None}
    return {rev for rev in revisions if rev not in children}


def _applied_migration(db_path: Path) -> str | None:
    import sqlite3

    try:
        with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as connection:
            row = connection.execute(
                "SELECT version_num FROM alembic_version LIMIT 1"
            ).fetchone()
    except sqlite3.Error:
        return None
    return str(row[0]) if row else None


def _check_runtime_config() -> bool:
    from bootstrap.runtime import DEFAULT_CONFIG_PATH, load_config
    from bootstrap.runtime_resolver import resolve_llama_server

    healthy = True
    config = {}
    if DEFAULT_CONFIG_PATH.is_file():
        config = load_config(DEFAULT_CONFIG_PATH)
        healthy &= _check(
            "Generated config", True, f"{DEFAULT_CONFIG_PATH} ({len(config)} keys)"
        )
    else:
        _check("Generated config", True, f"none at {DEFAULT_CONFIG_PATH} (stub fallback)")

    runtime = os.environ.get("RUACH_MODEL_RUNTIME") or config.get(
        "RUACH_MODEL_RUNTIME", "llama_cpp"
    )
    if runtime == "llama_cpp":
        model_path = Path(os.environ.get("RUACH_MODEL_PATH") or config.get("RUACH_MODEL_PATH", ""))
        model_ok = model_path.is_file() and model_path.stat().st_size > 0
        healthy &= _check(
            "Model artifact", model_ok, str(model_path) if model_ok else f"missing: {model_path}"
        )
        resolved = resolve_llama_server(
            explicit=os.environ.get("RUACH_LLAMA_SERVER_BIN") or config.get(
                "RUACH_LLAMA_SERVER_BIN"
            ),
        )
        healthy &= _check(
            "llama-server binary",
            resolved.found,
            str(resolved.path) + f" (source: {resolved.source})"
            if resolved.found
            else "not found in config/user/project/PATH",
        )
    else:
        healthy &= _check("Model runtime", True, runtime)

    workspace = Path(os.environ.get("RUACH_WORKSPACE_PATH") or Path.home() / ".ruach" / "workspace")
    try:
        workspace.mkdir(parents=True, exist_ok=True)
        probe = workspace / ".doctor-write-probe"
        probe.write_text("x", encoding="utf-8")
        probe.unlink()
        healthy &= _check("Workspace writable", True, str(workspace))
    except OSError as error:
        healthy &= _check("Workspace writable", False, str(error))
    return healthy


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


def cmd_status(run_dir: Path) -> int:
    import json as _json

    from bootstrap.runtime import status

    state = status(run_dir=run_dir)
    print(_json.dumps(state, indent=2))
    backend_raw = state.get("backend") if isinstance(state, dict) else None
    backend_running = bool(backend_raw.get("running")) if isinstance(backend_raw, dict) else False
    return 0 if backend_running else 1


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
            ("doctor", "Diagnose common problems."),
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
    subparsers.add_parser("doctor", help="diagnose installation health")

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
        )
    if args.command == "start":
        return cmd_start(args.config, args.run_dir, args.port, args.stub, args.no_browser)
    if args.command == "stop":
        return cmd_stop(args.run_dir)
    if args.command == "status":
        return cmd_status(args.run_dir)
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
