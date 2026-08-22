import json

import pytest

from ruach_setup.state import SetupState, SetupStateError, load_state, save_state


def test_fresh_state_when_file_missing(tmp_path):
    state = load_state(tmp_path / "absent" / "setup_state.json")
    assert state.stage == "not_initialized"


def test_mark_advances_through_pipeline():
    state = SetupState()
    state.mark("environment_ready")
    state.mark("runtime_installed", runtime_id="llama_cpp", runtime_version="b6100")
    state.mark("model_installed", model_id="qwen3-0.6b")
    state.mark("configured")
    state.mark("healthy")
    assert state.stage == "healthy"
    assert state.runtime_id == "llama_cpp"
    assert state.model_id == "qwen3-0.6b"


def test_backward_transition_rejected():
    state = SetupState()
    state.mark("runtime_installed")
    with pytest.raises(SetupStateError):
        state.mark("environment_ready")


def test_same_stage_is_idempotent():
    state = SetupState()
    state.mark("model_installed", model_id="qwen3-0.6b")
    state.mark("model_installed", model_id="qwen3-0.6b")
    assert state.stage == "model_installed"


def test_failed_stage_records_error_and_blocks_normal_advance():
    state = SetupState()
    state.mark("environment_ready")
    state.mark("failed", last_error="download interrupted")
    assert state.stage == "failed"
    assert state.last_error == "download interrupted"
    with pytest.raises(SetupStateError):
        state.mark("model_installed")


def test_failed_allows_restart_to_environment_ready():
    state = SetupState()
    state.mark("runtime_installed")
    state.mark("failed", last_error="boom")
    state.mark("environment_ready")
    assert state.stage == "environment_ready"


def test_unknown_stage_rejected():
    with pytest.raises(SetupStateError):
        SetupState().mark("warp_speed")


def test_save_and_load_roundtrip(tmp_path):
    path = tmp_path / "state" / "setup_state.json"
    state = SetupState()
    state.mark(
        "model_installed",
        model_id="qwen3-0.6b",
        model_sha256="abc123",
    )
    state.extras["build_jobs"] = "2"
    save_state(state, path)
    loaded = load_state(path)
    assert loaded == state
    raw = json.loads(path.read_text())
    assert raw["extras"] == {"build_jobs": "2"}


def test_save_is_atomic_no_tmp_leftover(tmp_path):
    path = tmp_path / "setup_state.json"
    save_state(SetupState(), path)
    assert not (tmp_path / "setup_state.json.tmp").exists()
    assert path.is_file()


def test_corrupt_state_raises_clear_error(tmp_path):
    path = tmp_path / "setup_state.json"
    path.write_text("{not json at all", encoding="utf-8")
    with pytest.raises(SetupStateError):
        load_state(path)
