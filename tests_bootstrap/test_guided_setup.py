"""Guided setup UX tests (docs/17 §6-§22, §38, §45, §46)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from bootstrap.guided_setup import SetupEffects, run_guided_setup
from bootstrap.installer import InstallError
from ruach_setup.state import save_state


class IO:
    def __init__(self, answers: list[str]):
        self.answers = list(answers)
        self.out: list[str] = []

    def reader(self) -> str:
        if not self.answers:
            raise EOFError("no more answers")
        return self.answers.pop(0)

    def writer(self, line: str = "") -> None:
        self.out.append(line)


def make_effects(tmp_path: Path, *, runtime_found: bool = False, fail_downloads: int = 0):
    calls = {"downloads": 0}

    def ensure_directories(home: Path) -> list[str]:
        created = []
        for name in ("config", "data", "models", "runtime", "logs", "workspace"):
            target = home / ".ruach" / name
            if not target.exists():
                target.mkdir(parents=True)
                created.append(name)
        return created

    def resolve_runtime(home: Path):
        return SimpleNamespace(
            found=runtime_found,
            path=Path("/bin/llama-server") if runtime_found else None,
        )

    fake_entry = SimpleNamespace(
        id="qwen3-0.6b-q8",
        family="qwen3",
        parameters="0.6B",
        quantization="Q8_0",
        download_size_bytes=700 * 1024 * 1024,
    )

    def resolve_model(requested: str):
        return None if requested == "none" else fake_entry

    def install_model(model_id, models_root, state, state_path, **kwargs):
        calls["downloads"] += 1
        if calls["downloads"] <= fail_downloads:
            raise InstallError("network unreachable")
        dest = Path(models_root) / model_id / "model.gguf"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"x")
        from bootstrap.installer import _mark_forward

        _mark_forward(state, "environment_ready")
        _mark_forward(state, "model_installed", model_id=model_id)
        from ruach_setup.state import save_state as persist

        persist(state, state_path)
        return SimpleNamespace(path=dest, sha256="ab" * 32, resumed=False, already_present=False)

    def write_config(home: Path, name: str, model_path: str) -> Path:
        config_path = home / ".ruach" / "config" / "ruach.env"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(f"RUACH_MODEL_PATH={model_path}", encoding="utf-8")
        return config_path

    def backend_packages_missing() -> list[str]:
        return ["fastapi"]

    effects = SetupEffects(
        ensure_directories=ensure_directories,
        resolve_runtime=resolve_runtime,
        resolve_model=resolve_model,
        install_model=install_model,
        write_config=write_config,
        backend_packages_missing=backend_packages_missing,
    )
    return effects, calls


def _run(io: IO, tmp_path: Path, effects, **kwargs) -> int:
    return run_guided_setup(
        reader=io.reader,
        writer=io.writer,
        home=tmp_path / "home",
        interactive=True,
        effects=effects,
        **kwargs,
    )


def test_happy_path_downloads_model_and_finishes_ready(tmp_path: Path) -> None:
    io = IO(["y", "y", "1"])  # ready; install plan; download recommended model
    effects, calls = make_effects(tmp_path, runtime_found=True)
    code = _run(io, tmp_path, effects)
    text = chr(10).join(io.out)
    assert code == 0
    assert calls["downloads"] == 1
    assert "[1/5]" in text and "[5/5]" in text, "progress must be visible"
    assert "Installation Plan" in text
    assert "Install this configuration? [Y/n]" in text, "smart-default prompt shown"
    assert "RUACH IS READY" in text
    ready_line = next(line for line in io.out if line.startswith("RUACH IS READY"))
    assert "DEGRADED" not in ready_line
    assert (tmp_path / "home" / ".ruach" / "config" / "ruach.env").is_file()
    state_text = (tmp_path / "home" / ".ruach" / "setup_state.json").read_text()
    assert '"stage": "healthy"' in state_text


def test_skip_model_is_degraded_but_successful(tmp_path: Path) -> None:
    """docs/17 §18: optional components may be skipped."""
    io = IO(["y", "y", "2", "3"])
    effects, calls = make_effects(tmp_path)
    code = _run(io, tmp_path, effects)
    text = chr(10).join(io.out)
    assert code == 0
    assert calls["downloads"] == 0
    assert "Skipped" in text
    assert "RUACH IS READY — DEGRADED" in text
    assert "no model installed" in text


def test_declining_plan_makes_no_changes(tmp_path: Path) -> None:
    io = IO(["y", "n"])  # ready; decline installation
    effects, _calls = make_effects(tmp_path)
    code = _run(io, tmp_path, effects)
    text = chr(10).join(io.out)
    assert code == 0
    assert "No changes made." in text
    assert not (tmp_path / "home" / ".ruach" / "config").exists()


def test_ctrl_c_cancels_safely_with_resume_hint(tmp_path: Path) -> None:
    """docs/17 §22: cancellation preserves completed work."""

    class Interrupting:
        def __init__(self) -> None:
            self.out: list[str] = []

        def reader(self) -> str:
            raise KeyboardInterrupt()

        def writer(self, line: str = "") -> None:
            self.out.append(line)

    io = Interrupting()
    effects, _calls = make_effects(tmp_path)
    code = run_guided_setup(
        reader=io.reader,
        writer=io.writer,
        home=tmp_path / "home",
        interactive=True,
        effects=effects,
    )
    text = chr(10).join(io.out)
    assert code == 130
    assert "cancelled safely" in text.lower() or "cancelled" in text.lower()
    assert "./ruach setup" in text, "resume hint shown"


def test_non_interactive_never_prompts_and_uses_defaults(tmp_path: Path) -> None:
    effects, calls = make_effects(tmp_path)
    out: list[str] = []
    code = run_guided_setup(
        reader=None,
        writer=out.append,
        home=tmp_path / "home",
        interactive=False,
        effects=effects,
    )
    text = chr(10).join(out)
    assert code == 0
    assert calls["downloads"] == 1, "deterministic default downloads the recommended model"
    assert "What would you like to do?" not in text
    assert "Ready?" not in text


def test_download_failure_offers_retry_then_recovers_or_degrades(tmp_path: Path) -> None:
    """docs/17 §15/§16: failures produce actionable choices; retry is safe."""
    io = IO(["y", "y", "2", "1", "n"])  # continue w/o runtime; fail; decline retry
    effects, calls = make_effects(tmp_path, fail_downloads=1)
    code = _run(io, tmp_path, effects)
    text = chr(10).join(io.out)
    assert code == 0
    assert "Model download failed" in text
    assert "Retry?" in text
    assert calls["downloads"] == 1
    assert "RUACH IS READY — DEGRADED" in text


def test_existing_model_path_is_accepted(tmp_path: Path) -> None:
    existing = tmp_path / "existing.gguf"
    existing.write_bytes(b"g")
    io = IO(["y", "y", "2", "2", str(existing)])
    effects, calls = make_effects(tmp_path)
    code = _run(io, tmp_path, effects)
    text = chr(10).join(io.out)
    assert code == 0
    assert calls["downloads"] == 0
    assert "existing.gguf" in text
    assert (tmp_path / "home" / ".ruach" / "config" / "ruach.env").is_file()


def test_runtime_already_installed_is_detected_idempotently(tmp_path: Path) -> None:
    """docs/15 §27: repeated setup detects installed components."""
    io = IO(["y", "y", "1"])  # runtime found → no failure menu; download model
    effects, _calls = make_effects(tmp_path, runtime_found=True)
    code = _run(io, tmp_path, effects)
    text = chr(10).join(io.out)
    assert code == 0
    assert "already installed" in text
    assert "What would you like to do?" not in text


def test_setup_log_is_appended(tmp_path: Path) -> None:
    io = IO(["y", "n"])
    effects, _calls = make_effects(tmp_path)
    _run(io, tmp_path, effects)
    log_file = tmp_path / "home" / ".ruach" / "logs" / "setup.log"
    assert log_file.is_file()


def test_preexisting_state_is_loaded_not_reset(tmp_path: Path) -> None:
    """docs/17 §21: resume support — prior progress is remembered."""
    home = tmp_path / "home"
    state_path = home / ".ruach" / "setup_state.json"
    from ruach_setup.state import SetupState

    state_path.parent.mkdir(parents=True)
    save_state(SetupState(stage="environment_ready"), state_path)

    io = IO(["y", "y", "2", "3"])  # skip model at the end
    effects, _calls = make_effects(tmp_path)
    code = _run(io, tmp_path, effects)
    assert code == 0
    final_text = state_path.read_text()
    assert '"stage": "healthy"' in final_text