"""Guided CLI experiences (docs/12 P16).

Presentation + interaction loop only; every action delegates to the
existing command implementations, which cli.py wires in. Works without
color or unicode (labels carry meaning), stays within ~60 columns, and
degrades to a one-screen summary with exact commands when stdin is not
interactive.
"""

from __future__ import annotations

from collections.abc import Callable

from bootstrap.cli_state import CliState, ResolvedCliState

Reader = Callable[[], str]
Writer = Callable[[str], None]

RULE = "─" * 46


def banner(writer: Writer, title: str, subtitle: str = "") -> None:
    writer("")
    writer("╔" + "═" * 44 + "╗")
    centered = title.center(44)
    writer("║" + centered + "║")
    if subtitle:
        writer("║" + subtitle.center(44) + "║")
    writer("╚" + "═" * 44 + "╝")


def menu(
    writer: Writer,
    reader: Reader,
    title: str,
    intro_lines: list[str],
    options: list[tuple[str, str, str]],
) -> str:
    """Render a menu, return the chosen option's key ('0' = exit)."""
    writer("")
    writer(title)
    for line in intro_lines:
        writer(f"  {line}")
    for key, label, description in options:
        writer(f"  [{key}] {label}")
        if description:
            writer(f"      {description}")
    writer("  [0] Exit")
    while True:
        try:
            choice = reader().strip()
        except (EOFError, KeyboardInterrupt):
            return "0"
        valid = {key for key, _, _ in options} | {"0"}
        if choice in valid:
            return choice
        writer(f"  Please choose one of: {', '.join(sorted(valid))}")


def learn_screen(writer: Writer) -> None:
    banner(writer, "ABOUT RUACH", "local AI for your device")
    lines = [
        "",
        "What it is",
        "  A private AI workspace that runs entirely on this device.",
        "",
        "What runs locally",
        "  - A small language model (a single model file)",
        "  - llama.cpp, the engine that runs it",
        "  - The RUACH server and interface you are using now",
        "",
        "Why approval is asked",
        "  Actions that touch your files (create/edit/delete) are",
        "  only ever PROPOSED by the model. Nothing executes until",
        "  you approve it. Denial is always available and final.",
        "",
        "Where data lives",
        "  ~/.ruach/config     settings",
        "  ~/.ruach/data       database",
        "  ~/.ruach/workspace  files the assistant may act on",
        "  ~/.ruach/run        runtime state while started",
        "",
        "No cloud service is required for any of this.",
    ]
    for line in lines:
        writer(line)


def _status_block(writer: Writer, resolved: ResolvedCliState) -> None:
    def mark(ok: bool | None) -> str:
        if ok is None:
            return "[??]"
        return "[ok]" if ok else "[!!]"

    def label(ok: bool | None, good: str, bad: str) -> str:
        return "unknown" if ok is None else (good if ok else bad)

    running = resolved.state is CliState.RUNNING
    writer("  Runtime      " + ("running" if running else "stopped"))
    writer(
        f"  Config       {mark(resolved.config_present)} "
        + label(resolved.config_present, "present", "missing")
    )
    writer(
        f"  Model        {mark(resolved.model_ok)} "
        + label(resolved.model_ok, "configured", "not ready")
    )
    writer(
        f"  Database     {mark(resolved.db_ready)} "
        + label(resolved.db_ready, "ready", "not initialized")
    )


def not_interactive_summary(
    writer: Writer,
    resolved: ResolvedCliState,
    version: str,
) -> int:
    """Script/CI-safe behavior for bare `./ruach` without a terminal."""
    banner(writer, f"RUACH v{version}", "local AI for your device")
    _status_block(writer, resolved)
    writer("")
    writer(f"  State: {resolved.state.value}")
    for reason in resolved.reasons:
        writer(f"    - {reason}")
    if resolved.state is CliState.RUNNING and resolved.base_url:
        writer("")
        writer(f"  Local interface: {resolved.base_url}")
    rec = resolved.recommendation
    if rec:
        writer("")
        writer("  Recommended next step:")
        writer(f"    {rec}")
    writer("")
    writer("  Interactive menu needs a terminal. Direct commands:")
    writer("    ./ruach start|stop|restart|status|verify|doctor|logs|help")
    writer("")
    return 0


HANDLER = Callable[[], int]


def run_guided(
    *,
    interactive: bool,
    reader: Reader,
    writer: Writer,
    resolver,
    version: str,
    on_setup: HANDLER,
    on_start: HANDLER,
    on_stop: HANDLER,
    on_status: HANDLER,
    on_verify: HANDLER,
    on_doctor: HANDLER,
    on_logs: HANDLER,
    on_config: HANDLER,
    on_model: HANDLER,
    on_help: HANDLER,
    open_url,
) -> int:
    """State-driven entrypoint loop. Returns a process exit code."""
    resolved = resolver()

    if not interactive:
        return not_interactive_summary(writer, resolved, version)

    while True:
        state = resolved.state

        if state is CliState.FIRST_RUN:
            banner(writer, "R U A C H", "local AI for your device")
            choice = menu(
                writer,
                reader,
                "Welcome to RUACH. This looks like your first time here.",
                [
                    "RUACH runs AI locally on this device — no cloud account,",
                    "no internet required after setup.",
                ],
                [
                    ("1", "Set up RUACH", "Check this device and prepare the AI runtime."),
                    ("2", "Learn about RUACH", "See what RUACH does before setting up."),
                    ("3", "Help", "Show available commands."),
                ],
            )
            if choice == "0":
                return 0
            if choice == "1":
                on_setup()
                resolved = resolver()
                continue
            if choice == "2":
                learn_screen(writer)
                continue
            if choice == "3":
                on_help()
                continue

        if state is CliState.SETUP_INCOMPLETE:
            stage_note = (
                f"Setup previously reached stage: {resolved.setup_stage}"
                if resolved.setup_stage
                else "Setup was started but did not finish."
            )
            banner(writer, "SETUP INCOMPLETE")
            writer("")
            writer(f"  {stage_note}")
            for reason in resolved.reasons:
                writer(f"  - {reason}")
            choice = menu(
                writer,
                reader,
                "What would you like to do?",
                [],
                [
                    ("1", "Resume setup", "Continue where it stopped (idempotent)."),
                    ("2", "Re-run setup", "Walk through setup again from the top."),
                    ("3", "Run diagnostics", "./ruach doctor"),
                ],
            )
            if choice == "0":
                return 0
            if choice in {"1", "2"}:
                on_setup()
                resolved = resolver()
                continue
            if choice == "3":
                on_doctor()
                continue

        if state is CliState.DEGRADED:
            banner(writer, "RUACH NEEDS ATTENTION")
            writer("")
            for reason in resolved.reasons:
                writer(f"  ! {reason}")
            choice = menu(
                writer,
                reader,
                "What would you like to do?",
                [],
                [
                    ("1", "Diagnose problems", "./ruach doctor"),
                    ("2", "Verify installation", "./ruach verify (takes a few minutes)"),
                    ("3", "Re-check status", ""),
                ],
            )
            if choice == "0":
                return 0
            if choice == "1":
                on_doctor()
            elif choice == "2":
                on_verify()
            elif choice == "3":
                resolved = resolver()
            continue

        if state is CliState.ERROR:
            banner(writer, "SOMETHING WENT WRONG")
            writer("")
            for reason in resolved.reasons:
                writer(f"  x {reason}")
            choice = menu(
                writer,
                reader,
                "What would you like to do?",
                ["Technical details are available via doctor."],
                [("1", "Run diagnostics", "./ruach doctor")],
            )
            if choice == "0":
                return 1
            on_doctor()
            continue

        if state is CliState.RUNNING:
            url = resolved.base_url or "(unknown address)"
            banner(writer, "RUACH IS RUNNING")
            writer("")
            writer(f"  Local interface: {url}")
            choice = menu(
                writer,
                reader,
                "What would you like to do?",
                [],
                [
                    ("1", "Open RUACH", "Open the local interface in a browser."),
                    ("2", "View status", "./ruach status"),
                    ("3", "View logs", "./ruach logs"),
                    ("4", "Run diagnostics", "./ruach doctor"),
                    ("5", "Stop RUACH", "./ruach stop"),
                ],
            )
            if choice == "0":
                return 0
            if choice == "1":
                open_url(url)
            elif choice == "2":
                on_status()
            elif choice == "3":
                on_logs()
            elif choice == "4":
                on_doctor()
            elif choice == "5":
                on_stop()
                resolved = resolver()
            continue

        # READY
        banner(writer, "R U A C H", "ready")
        writer("")
        _status_block(writer, resolved)
        choice = menu(
            writer,
            reader,
            "What would you like to do?",
            [],
            [
                ("1", "Start RUACH", "Start the local AI system."),
                ("2", "Check RUACH", "./ruach verify"),
                ("3", "Configuration", "./ruach config"),
                ("4", "Model information", "./ruach model"),
                ("5", "Logs", "./ruach logs"),
                ("6", "Doctor", "./ruach doctor"),
                ("7", "Help", "All commands."),
            ],
        )
        if choice == "0":
            return 0
        if choice == "1":
            # Blocking by design: hands the foreground to the server.
            return on_start()
        if choice == "2":
            on_verify()
        elif choice == "3":
            on_config()
        elif choice == "4":
            on_model()
        elif choice == "5":
            on_logs()
        elif choice == "6":
            on_doctor()
        elif choice == "7":
            on_help()
