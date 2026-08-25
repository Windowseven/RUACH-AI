"""P16 tests: guided CLI state machine and user flows (docs/12 §24)."""

from __future__ import annotations

import stat
from pathlib import Path

from bootstrap import cli, cli_state, guided
from bootstrap.cli_state import CliState, ResolvedCliState, resolve_state


class FakeIO:
    def __init__(self, answers: list[str]):
        self.answers = list(answers)
        self.out: list[str] = []

    def reader(self) -> str:
        return self.answers.pop(0) if self.answers else "0"

    def writer(self, line: str = "") -> None:
        self.out.append(line)


def _make_executable(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\n")
    mode = path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
    path.chmod(mode)
    return path


def _configured_home(tmp_path: Path) -> Path:
    """A home that passes every READY signal."""
    home = tmp_path / "home"
    model = tmp_path / "model.gguf"
    model.write_bytes(b"\x00")
    binary = _make_executable(tmp_path / "bin" / "llama-server")
    config_dir = home / ".ruach" / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "ruach.env").write_text(
        f"RUACH_MODEL_RUNTIME=llama_cpp\n"
        f"RUACH_MODEL_PATH={model}\n"
        f"RUACH_LLAMA_SERVER_BIN={binary}\n",
        encoding="utf-8",
    )
    db_dir = home / ".ruach" / "data"
    db_dir.mkdir(parents=True)
    import sqlite3

    connection = sqlite3.connect(db_dir / "ruach.db")
    connection.execute("create table alembic_version (version_num varchar(32))")
    connection.execute("insert into alembic_version values ('head')")
    connection.commit()
    connection.close()
    return home


def _rec(calls: dict, key: str):
    def go() -> int:
        calls[key] = calls.get(key, 0) + 1
        return 0

    return go


def _run_guided(io: FakeIO, resolved: ResolvedCliState, calls: dict | None = None):
    calls = calls if calls is not None else {}
    return guided.run_guided(
        interactive=True,
        reader=io.reader,
        writer=io.writer,
        resolver=lambda: resolved,
        version="0.0.0-test",
        on_setup=_rec(calls, "setup"),
        on_start=_rec(calls, "start"),
        on_stop=_rec(calls, "stop"),
        on_status=_rec(calls, "status"),
        on_verify=_rec(calls, "verify"),
        on_doctor=_rec(calls, "doctor"),
        on_logs=_rec(calls, "logs"),
        on_config=_rec(calls, "config"),
        on_model=_rec(calls, "model"),
        on_help=_rec(calls, "help"),
        open_url=lambda url: calls.update({"url": url}),
    )


def _stopped_status() -> dict:
    return {
        "lifecycle": {"state": "STOPPED", "detail": "", "at": "", "responsive": None},
        "backend": {"pid": None, "process_alive": False, "running": False},
        "model_server": {"pid": None, "running": False},
    }


# ------------------------------------------------------------ Flows A and B
def test_first_run_shows_welcome_and_setup(tmp_path: Path) -> None:
    io = FakeIO(["2", "0"])  # learn about RUACH, then exit
    code = _run_guided(io, resolve_state(home=tmp_path / "empty-home", run_dir=tmp_path / "run"))
    text = "\n".join(io.out)
    assert code == 0
    assert "first time" in text.lower()
    assert "Set up RUACH" in text
    assert "Learn about RUACH" in text
    assert "approval" in text.lower(), "learn screen explains the approval model"


def test_setup_incomplete_offers_resume(tmp_path: Path) -> None:
    home = _configured_home(tmp_path)
    (home / ".ruach" / "setup_state.json").write_text('{"stage": "model_installed"}')
    resolved = resolve_state(home=home, run_dir=tmp_path / "run")
    assert resolved.state is CliState.SETUP_INCOMPLETE
    assert resolved.setup_stage == "installing"

    io = FakeIO(["1", "0"])  # resume setup, then exit
    calls: dict = {}
    _run_guided(io, resolved, calls)
    text = "\n".join(io.out)
    assert "SETUP INCOMPLETE" in text
    assert "Resume setup" in text
    assert calls.get("setup") == 1


def test_corrupt_setup_state_is_readable_error(tmp_path: Path) -> None:
    home = _configured_home(tmp_path)
    (home / ".ruach" / "setup_state.json").write_text("{not json")
    resolved = resolve_state(home=home, run_dir=tmp_path / "run")
    assert resolved.state is CliState.ERROR
    assert resolved.reasons


# ----------------------------------------------------------------- Flow C
def test_ready_shows_home_menu_with_start(tmp_path: Path) -> None:
    home = _configured_home(tmp_path)
    resolved = resolve_state(home=home, run_dir=tmp_path / "run")
    assert resolved.state is CliState.READY
    assert resolved.model_ok and resolved.binary_ok and resolved.db_ready

    io = FakeIO(["0"])
    _run_guided(io, resolved)
    text = "\n".join(io.out)
    assert "Start RUACH" in text
    assert "[ok]" in text


def test_ready_start_invokes_handler_and_exits_menu(tmp_path: Path) -> None:
    home = _configured_home(tmp_path)
    io = FakeIO(["1"])  # choose start; handler "blocks" until exit code
    calls: dict = {}
    code = _run_guided(io, resolve_state(home=home, run_dir=tmp_path / "run"), calls)
    assert code == 0
    assert calls.get("start") == 1


# ----------------------------------------------------------------- Flow E
def test_degraded_explains_what_is_wrong(tmp_path: Path) -> None:
    home = _configured_home(tmp_path)
    (tmp_path / "model.gguf").unlink()  # break the artifact after config
    resolved = resolve_state(home=home, run_dir=tmp_path / "run")
    assert resolved.state is CliState.DEGRADED
    assert any("missing" in reason for reason in resolved.reasons)

    io = FakeIO(["1", "0"])  # run diagnostics, then exit
    calls: dict = {}
    _run_guided(io, resolved, calls)
    text = "\n".join(io.out)
    assert "NEEDS ATTENTION" in text
    assert "missing" in text
    assert calls.get("doctor") == 1


# ----------------------------------------------------------------- Flow D
def test_running_menu_never_offers_second_start(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        cli_state,
        "runtime_status",
        lambda _rd: {
            "lifecycle": {
                "state": "HEALTHY",
                "detail": "",
                "at": "",
                "responsive": True,
            },
            "backend": {"pid": 4242, "process_alive": True, "running": True},
            "model_server": {"pid": None, "running": False},
        },
    )
    resolved = resolve_state(home=tmp_path / "anyhome", run_dir=tmp_path / "run")
    assert resolved.state is CliState.RUNNING

    io = FakeIO(["1", "5", "0"])  # open URL, stop, exit
    calls: dict = {}
    _run_guided(io, resolved, calls)
    text = "\n".join(io.out)
    assert "RUACH IS RUNNING" in text
    assert "Start RUACH" not in text, "running menu must not offer a duplicate start"


def test_unresponsive_process_is_degraded_not_running(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        cli_state,
        "runtime_status",
        lambda _rd: {
            "lifecycle": {
                "state": "UNRESPONSIVE",
                "detail": "",
                "at": "",
                "responsive": False,
            },
            "backend": {"pid": 4242, "process_alive": True, "running": True},
            "model_server": {"pid": None, "running": False},
        },
    )
    resolved = resolve_state(home=tmp_path, run_dir=tmp_path / "run")
    assert resolved.state is CliState.DEGRADED
    assert any("not answering" in reason for reason in resolved.reasons)


# ----------------------------------------------------------------- Flow F
def test_help_lists_all_supported_commands(capsys) -> None:
    assert cli.cmd_help() == 0
    text = capsys.readouterr().out
    for name in (
        "setup",
        "start",
        "stop",
        "restart",
        "status",
        "verify",
        "doctor",
        "logs",
        "config",
        "model",
        "help",
        "version",
    ):
        assert f"./ruach {name}" in text, name


def test_help_is_categorized(capsys) -> None:
    assert cli.cmd_help() == 0
    text = capsys.readouterr().out
    for section in ("Getting Started", "System", "Configuration", "Maintenance"):
        assert section in text


# ----------------------------------------------------------------- Flow G
def test_direct_command_routing_does_not_regress(monkeypatch) -> None:
    called: list[str] = []
    monkeypatch.setattr(cli, "_guided_home", lambda: called.append("guided") or 0)
    monkeypatch.setattr(cli, "cmd_doctor", lambda: called.append("doctor") or 0)
    monkeypatch.setattr(cli, "cmd_help", lambda: called.append("help") or 0)
    monkeypatch.setattr(cli, "cmd_config", lambda: called.append("config") or 0)
    monkeypatch.setattr(cli, "cmd_model", lambda: called.append("model") or 0)
    monkeypatch.setattr(
        cli, "cmd_logs", lambda rd, lines: called.append(f"logs:{lines}") or 0
    )
    monkeypatch.setattr(cli, "cmd_start", lambda *a, **k: called.append("start") or 0)
    monkeypatch.setattr(cli, "cmd_stop", lambda rd: called.append("stop") or 0)

    assert cli.main([]) == 0
    assert called[-1] == "guided"

    assert cli.main(["help"]) == 0
    assert cli.main(["config"]) == 0
    assert cli.main(["model"]) == 0
    assert cli.main(["logs", "--lines", "5"]) == 0
    assert "logs:5" in called

    assert cli.main(["restart", "--stub"]) == 0
    assert "stop" in called and "start" in called


def test_non_interactive_bare_ruach_prints_summary_not_prompt(
    tmp_path: Path, capsys
) -> None:
    home = _configured_home(tmp_path)
    resolved = resolve_state(home=home, run_dir=tmp_path / "run")
    from bootstrap.guided import not_interactive_summary

    code = not_interactive_summary(lambda line="": print(line), resolved, "0.3.0")
    out = capsys.readouterr().out
    assert code == 0
    assert f"State: {resolved.state.value}" in out
    assert "./ruach start|stop|restart|status|verify|doctor|logs|help" in out


def test_menus_stay_narrow_terminal_safe(tmp_path: Path) -> None:
    for state in (
        CliState.FIRST_RUN,
        CliState.SETUP_INCOMPLETE,
        CliState.READY,
        CliState.RUNNING,
        CliState.DEGRADED,
    ):
        resolved = ResolvedCliState(
            state=state,
            base_url="http://127.0.0.1:8018" if state is CliState.RUNNING else None,
            reasons=["example reason"] if state is CliState.DEGRADED else [],
            setup_stage="model_installed"
            if state is CliState.SETUP_INCOMPLETE
            else None,
            config_present=True,
            model_ok=True,
            binary_ok=True,
            db_ready=True,
        )
        io = FakeIO(["0"])
        _run_guided(io, resolved)
        widest = max(len(line) for line in io.out)
        assert widest <= 62, f"{state}: line too wide ({widest}) for small terminals"
