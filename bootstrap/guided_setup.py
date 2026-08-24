"""Guided CLI setup experience (docs/17 state machine).

WELCOME → DEVICE_SCAN → CLASSIFY → PLAN → CONFIRM → INSTALL → VERIFY →
MODEL_SETUP → FINAL_VERIFY → READY, with failure menus (retry /
alternative / skip / details / exit), resume support, safe Ctrl+C
handling and a non-interactive mode with deterministic defaults.

Presentation + interaction only: every effect is delegated to an
injectable SetupEffects object whose defaults call the real installer,
config generator and doctor engine. This keeps the flow fully testable
without touching a real device (docs/17 §26 separation of concerns).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ruach_setup.oplog import append_setup_log
from ruach_setup.planner import InstallationPlan, human_bytes, render_plan
from ruach_setup.profiles import DecisionInput, validate_mode
from ruach_setup.state import SetupState, load_state, save_state

Reader = Callable[[], str]
Writer = Callable[[str], None]

RULE = "-" * 46


class Cancelled(Exception):
    """User chose Exit in a menu."""


# --------------------------------------------------------------------------
# Injectable side effects


@dataclass
class SetupEffects:
    """The only place setup touches the world."""

    ensure_directories: Callable[[Path], list[str]]
    resolve_runtime: Callable[[Path], Any]
    resolve_model: Callable[[str], Any]
    install_model: Callable[..., Any]
    write_config: Callable[[Path, str, str], Path]
    backend_packages_missing: Callable[[], list[str]]


def default_effects() -> SetupEffects:
    def ensure_directories(home: Path) -> list[str]:
        created = []
        for name in ("config", "data", "models", "runtime", "logs", "workspace"):
            target = home / ".ruach" / name
            if not target.exists():
                target.mkdir(parents=True, exist_ok=True)
                created.append(name)
        return created

    def resolve_runtime(home: Path):
        from bootstrap.runtime_resolver import resolve_llama_server

        return resolve_llama_server(home=home)

    def install_model(model_id, models_root, state, state_path, **kwargs):
        from bootstrap.installer import install_model as run_install

        return run_install(model_id, models_root, state, state_path, **kwargs)

    def resolve_model(requested: str):
        from bootstrap.installer import resolve_model_id

        return resolve_model_id(requested)

    def write_config(home: Path, model_name: str, model_path: str) -> Path:
        from bootstrap.configgen import env_entries_for_model, write_env

        entries = env_entries_for_model(
            runtime_id="llama_cpp",
            model_name=model_name,
            model_path=Path(model_path),
            server_url="http://127.0.0.1:8080",
            timeout_seconds=120.0,
        )
        return write_env(home / ".ruach" / "config" / "ruach.env", entries)

    def backend_packages_missing() -> list[str]:
        missing = []
        for package in ("fastapi", "uvicorn", "sqlalchemy", "alembic", "pydantic_settings"):
            try:
                __import__(package)
            except ImportError:
                missing.append(package)
        return missing

    return SetupEffects(
        ensure_directories=ensure_directories,
        resolve_runtime=resolve_runtime,
        resolve_model=resolve_model,
        install_model=install_model,
        write_config=write_config,
        backend_packages_missing=backend_packages_missing,
    )


# --------------------------------------------------------------------------
# Interaction helpers (docs/17 §4 interaction model)


def ask_yes(
    writer: Writer, reader: Reader | None, question: str, default_yes: bool = True
) -> bool:
    suffix = "[Y/n]" if default_yes else "[y/N]"
    writer(f"{question} {suffix}")
    if reader is None:
        return default_yes
    try:
        answer = reader().strip().lower()
    except (EOFError, KeyboardInterrupt):
        raise Cancelled() from None
    if not answer:
        return default_yes
    return answer in {"y", "yes"}


def ask_menu(
    writer: Writer,
    reader: Reader,
    options: list[tuple[str, str]],
    *,
    allow_empty: str | None = None,
) -> str:
    """Number selection with stable keys; returns the chosen key."""
    for key, label in options:
        writer(f"  {key}. {label}")
    valid = {key for key, _ in options}
    while True:
        try:
            choice = reader().strip()
        except (EOFError, KeyboardInterrupt):
            raise Cancelled() from None
        if not choice and allow_empty is not None:
            return allow_empty
        if choice in valid:
            return choice
        writer(f"  Please choose one of: {', '.join(sorted(valid))}")


def show_technical_details(writer: Writer, facts: dict[str, str]) -> None:
    writer("")
    writer("Technical diagnostics")
    for key, value in sorted(facts.items()):
        writer(f"  {key:<18}: {value}")
    writer("")


# --------------------------------------------------------------------------
# The guided flow


@dataclass
class SetupOutcome:
    exit_code: int
    degraded_reasons: list[str] = field(default_factory=list)


def run_guided_setup(
    *,
    reader: Reader | None,
    writer: Writer,
    home: Path | None = None,
    interactive: bool = True,
    assume_yes: bool = False,
    requested_mode: str = "auto",
    install_model_request: str = "auto",
    models_root: Path | None = None,
    effects: SetupEffects | None = None,
) -> int:
    """Run the full guided setup. Returns a process exit code."""
    home = home if home is not None else Path.home()
    models_root = models_root if models_root is not None else home / ".ruach" / "models"
    fx = effects or default_effects()
    state_path = home / ".ruach" / "setup_state.json"
    interactive = interactive and reader is not None

    try:
        return _flow(
            reader=reader,
            writer=writer,
            home=home,
            models_root=models_root,
            fx=fx,
            state_path=state_path,
            interactive=interactive,
            assume_yes=assume_yes,
            requested_mode=requested_mode,
            install_model_request=install_model_request,
        )
    except Cancelled:
        writer("")
        writer("Setup cancelled.")
        writer("Your completed components have been preserved.")
        writer("")
        writer("Resume later with:")
        writer("  ./ruach setup")
        append_setup_log("cancelled by user", home=home)
        return 130
    except KeyboardInterrupt:
        writer("")
        writer("Setup cancelled safely (Ctrl+C).")
        writer("Your completed components have been preserved.")
        writer("")
        writer("Resume later with:")
        writer("  ./ruach setup")
        append_setup_log("interrupted (Ctrl+C)", home=home)
        return 130


def _confirm(writer: Writer, reader: Reader, question: str, interactive: bool) -> bool:
    if not interactive:
        return True  # deterministic default: proceed with safe actions
    return ask_yes(writer, reader, question)


def _flow(
    *,
    reader,
    writer,
    home: Path,
    models_root: Path,
    fx: SetupEffects,
    state_path: Path,
    interactive: bool,
    assume_yes: bool,
    requested_mode: str,
    install_model_request: str,
) -> int:
    writer("")
    writer("RUACH SETUP")
    writer(RULE)

    # ---- WELCOME ----------------------------------------------------------
    if interactive and not assume_yes:
        writer("")
        writer("Welcome. Let's prepare RUACH for this device.")
        writer("We'll check your system and choose the best execution")
        writer("strategy automatically. You confirm each major step.")
        if not ask_yes(writer, reader, "Ready?", default_yes=True):
            writer("Maybe later. Run ./ruach setup whenever you're ready.")
            return 0

    # ---- DEVICE_SCAN + CLASSIFY -------------------------------------------
    from bootstrap.doctor_engine import run_doctor

    writer("")
    writer("[1/5] Understanding your device...")
    report = run_doctor(home=home, probe_network_enabled=False)
    profile = report.decision["profile"]
    confidence = report.decision["confidence"]
    arch = report.device.get("arch", "?")
    abi = report.device.get("abi", "?")
    ram = report.device.get("ram_available_bytes")
    storage = report.device.get("storage_free_bytes")
    writer(f"      Architecture : {arch} ({abi})")
    writer(f"      RAM available: {human_bytes(ram) if ram else 'unknown'}")
    writer(f"      Storage free : {human_bytes(storage) if storage else 'unknown'}")
    writer("      Done")

    capabilities = _capabilities_from_report(report)
    append_setup_log(
        f"start mode={requested_mode} profile={profile} confidence={confidence}",
        home=home,
    )

    # ---- Mode validation (docs/16 §18) ------------------------------------
    if requested_mode != "auto":
        ok, message, available = validate_mode(capabilities, requested_mode)
        if not ok:
            writer("")
            writer(message)
            if available:
                writer("")
                writer("Available modes:")
                for mode in available:
                    writer(f"  {mode}")
            append_setup_log(f"mode rejected: {requested_mode}", home=home)
            return 2

    writer("")
    writer("[2/5] Selecting runtime...")
    writer(f"      Recommended profile: {profile} (confidence {confidence})")
    for reason in report.decision["reason"][:3]:
        writer(f"      - {reason}")
    writer("      Done")

    # ---- PLAN + CONFIRM (docs/17 §13) --------------------------------------
    writer("")
    writer("[3/5] Preparing installation plan...")
    plan = report.plan
    writer("")
    for line in render_plan(plan).splitlines():
        writer(line)
    writer("")
    if plan.mode == "none":
        writer("RUACH cannot identify a viable installation strategy.")
        writer("Run ./ruach doctor --verbose and share the output in a bug report.")
        return 1
    if not _confirm(writer, reader, "Install this configuration?", interactive):
        writer("No changes made. Run ./ruach setup when ready.")
        return 0

    # ---- INSTALL ------------------------------------------------------------
    state: SetupState = _load_state_safe(state_path)
    degraded: list[str] = []

    # [directories]
    created = fx.ensure_directories(home)
    if created:
        writer(f"[4/5] Installing configuration... ({len(created)} directories created)")
    else:
        writer("[4/5] Installing configuration... (already present)")
    if state.stage == "not_initialized":
        state.mark("environment_ready")
        save_state(state, state_path)

    # [runtime]
    resolved = fx.resolve_runtime(home)
    if getattr(resolved, "found", False):
        writer(f"[4/5] Preparing native runtime... already installed ({resolved.path})")
        if state.stage in {"not_initialized", "environment_ready"}:
            state.mark("runtime_installed")
            save_state(state, state_path)
    else:
        writer("[4/5] Preparing native runtime... FAILED")
        writer("")
        writer("Reason:")
        writer("  No llama-server binary was found, and building llama.cpp on")
        writer("  this platform is pending target-device validation (docs/11).")
        choice = "2"
        if interactive:
            writer("")
            writer("What would you like to do?")
            choice = ask_menu(
                writer,
                reader,
                [
                    ("1", "Retry detection"),
                    ("2", "Continue without it (development stub can substitute)"),
                    ("3", "Show technical details"),
                    ("4", "Exit"),
                ],
            )
            if choice == "1":
                resolved = fx.resolve_runtime(home)
                choice = "2" if not getattr(resolved, "found", False) else "done"
            elif choice == "3":
                show_technical_details(
                    writer,
                    {
                        "searched": "config override, ~/.ruach/runtime/, project .build/runtime/, PATH",
                        "toolchain": ", ".join(sorted(report.toolchain)) or "none measured",
                        "docs": "docs/11_TERMUX_SPIKE.md governs runtime acquisition",
                    },
                )
                choice = ask_menu(
                    writer,
                    reader,
                    [
                        ("2", "Continue without native runtime"),
                        ("4", "Exit"),
                    ],
                )
        if choice == "4":
            raise Cancelled()
        degraded.append("native runtime binary not installed; inference needs setup or stub")
        append_setup_log("runtime missing; continuing degraded", home=home)

    # [model]
    model_result = _model_stage(
        writer=writer,
        reader=reader,
        interactive=interactive,
        home=home,
        models_root=models_root,
        fx=fx,
        state=state,
        state_path=state_path,
        request=install_model_request,
        plan=plan,
    )
    model_path = model_result
    if model_path is None:
        degraded.append("no model installed; chat requires one before starting")

    # [python components — soft check, never a blind install (docs/16 §25)]
    missing = fx.backend_packages_missing()
    if missing:
        writer("")
        writer(f"Note: Python application packages not installed here ({', '.join(missing)}).")
        writer("Run ./install.sh to build the virtual environment; RUACH will")
        writer("not install global packages automatically.")

    # [config]
    if model_path is not None:
        name = Path(model_path).stem
        config_path = fx.write_config(home, name, model_path)
        writer("")
        writer(f"[5/5] Running final verification... config written: {config_path}")
        if state.stage in {"not_initialized", "environment_ready", "runtime_installed", "model_installed"}:
            state.mark("configured")
            save_state(state, state_path)
    else:
        writer("")
        writer("[5/5] Running final verification... (skipped config: no model)")

    # ---- FINAL VERIFY -------------------------------------------------------
    final = run_doctor(home=home, probe_network_enabled=False)
    for entry in final.verification:
        marker = {
            "PASS": "+",
            "WARN": "!",
            "FAIL": "x",
            "UNKNOWN": "?",
        }[entry.status.value]
        writer(f"  [{marker}] {entry.level}: {entry.detail}")

    if final.decision["profile"] != "UNSUPPORTED" and state.stage in {
        "not_initialized",
        "environment_ready",
        "runtime_installed",
        "model_installed",
        "configured",
    }:
        state.mark("healthy")
        save_state(state, state_path)

    append_setup_log(f"finished status={final.status}", home=home)

    # ---- READY SCREEN (docs/17 §38) -----------------------------------------
    writer("")
    writer("RUACH IS READY" if not degraded else "RUACH IS READY — DEGRADED")
    writer("")
    writer(f"  Architecture : {arch}")
    writer(f"  Mode         : {plan.mode}")
    writer(f"  Profile      : {final.decision['profile']}")
    writer(f"  Model        : {Path(model_path).name if model_path else '(none yet)'}")
    if degraded:
        writer("")
        writer("Unavailable for now:")
        for reason in degraded:
            writer(f"  ! {reason}")
    writer("")
    writer("Start RUACH:")
    writer("  ./ruach start")
    writer("")
    writer("Doctor:")
    writer("  ./ruach doctor")
    return 0


def _capabilities_from_report(report) -> DecisionInput:
    """Rebuild the DecisionInput snapshot from a DoctorReport."""
    from ruach_setup.profiles import DecisionInput

    return DecisionInput(
        architecture_supported=report.device.get("arch") not in (None, "unknown"),
        abi=str(report.device.get("abi", "")),
        ram_total_bytes=report.device.get("ram_bytes"),
        ram_available_bytes=report.device.get("ram_available_bytes"),
        storage_free_bytes=report.device.get("storage_free_bytes"),
        python_ok=bool(report.python.get("available")),
        python_version=str(report.python.get("version", "")),
        compilers_present=frozenset(k for k, ok in report.toolchain.items() if ok),
        rust_available=bool(report.toolchain.get("rustc")),
        native_binary_found="llama-server" in str(
            next((e.detail for e in report.verification if e.level == "Runtime"), "")
        ),
        inference_level=_level_from_verification(report),
        python_deps_healthy=None,
        resource_tier="unknown",
        environment_status=report.environment_status,
    )


def _level_from_verification(report):
    from ruach_setup.diagnostics import InferenceLevel

    runtime_entry = next((e for e in report.verification if e.level == "Runtime"), None)
    if runtime_entry is None:
        return InferenceLevel.NOT_TESTED
    if runtime_entry.status.value == "PASS":
        return InferenceLevel.EXECUTABLE
    if "source build looks viable" in runtime_entry.detail:
        return InferenceLevel.BUILDABLE
    return InferenceLevel.NOT_TESTED


def _load_state_safe(state_path: Path) -> SetupState:
    try:
        return load_state(state_path)
    except Exception:  # noqa: BLE001 - corrupt state restarts the pipeline
        return SetupState()


def _model_stage(
    *,
    writer: Writer,
    reader,
    interactive: bool,
    home: Path,
    models_root: Path,
    fx: SetupEffects,
    state: SetupState,
    state_path: Path,
    request: str,
    plan: InstallationPlan,
) -> str | None:
    """Acquire a model artifact. Returns its path, or None when skipped."""
    from bootstrap.installer import InstallError

    entry = fx.resolve_model(request)

    choice = "1"
    if interactive:
        writer("")
        writer("Model setup")
        options = []
        if entry is not None:
            size_mb = entry.download_size_bytes // (1024 * 1024)
            options.append(("1", f"Download recommended model ({entry.id}, ~{size_mb} MB)"))
        options.append(("2", "Use an existing model file"))
        options.append(("3", "Skip model setup"))
        choice = ask_menu(writer, reader, options)
    else:
        if entry is None:
            writer("")
            writer("Model setup... no recommended model fits this device (skipped)")
            return None
        writer("")
        writer(
            f"Model setup... downloading {entry.id} "
            f"(~{entry.download_size_bytes // (1024 * 1024)} MB)"
        )

    if choice == "3":
        writer("  Skipped (optional at this stage)")
        return None

    if choice == "2":
        writer("  Enter model path:")
        try:
            raw_path = (reader() if reader else "").strip()
        except (EOFError, KeyboardInterrupt):
            raise Cancelled() from None
        candidate = Path(raw_path).expanduser()
        if not candidate.is_file():
            writer(f"  x No file at {candidate}; skipping model setup.")
            return None
        return str(candidate)

    if entry is None:
        writer("  x No installable model resolved for this device.")
        return None

    try:
        result = fx.install_model(entry.id, models_root, state, state_path)
    except InstallError as error:
        writer(f"  x Model download failed: {error}")
        if interactive:
            retry = ask_yes(writer, reader, "Retry?", default_yes=True)
            if retry:
                try:
                    result = fx.install_model(entry.id, models_root, state, state_path)
                except InstallError as second_error:
                    writer(f"  x Still failing: {second_error}")
                    return None
            else:
                return None
        else:
            return None

    status_text = (
        "already present (verified)"
        if result.already_present
        else ("downloaded (resumed)" if result.resumed else "downloaded")
    )
    writer(f"  Model {status_text}: {result.path}")
    writer(f"  SHA-256: {result.sha256[:16]}...")
    return str(result.path)


__all__ = ["Cancelled", "SetupEffects", "SetupOutcome", "run_guided_setup"]