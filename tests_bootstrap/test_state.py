import json

import pytest

from ruach_setup.state import SetupState, SetupStateError, load_state, save_state


def test_fresh_state_when_file_missing(tmp_path):
    state = load_state(tmp_path / "absent" / "setup_state.json")
    assert state.stage == "new"


def test_mark_advances_through_pipeline():
    state = SetupState()
    state.mark("discovering")
    state.mark("planned")
    state.mark("installing", runtime_id="llama_cpp", runtime_version="b6100")
    state.mark("verifying", model_id="qwen3-0.6b")
    state.mark("ready")
    assert state.stage == "ready"
    assert state.runtime_id == "llama_cpp"
    assert state.model_id == "qwen3-0.6b"


def test_backward_transition_rejected():
    state = SetupState()
    state.mark("installing")
    with pytest.raises(SetupStateError):
        state.mark("discovering")


def test_same_stage_is_idempotent():
    state = SetupState()
    state.mark("installing", model_id="qwen3-0.6b")
    state.mark("installing", model_id="qwen3-0.6b")
    assert state.stage == "installing"


def test_failed_stage_records_error_and_blocks_normal_advance():
    state = SetupState()
    state.mark("discovering")
    state.mark("failed", last_error="download interrupted")
    assert state.stage == "failed"
    assert state.last_error == "download interrupted"
    with pytest.raises(SetupStateError):
        state.mark("installing")


def test_failed_allows_restart_to_new():
    state = SetupState()
    state.mark("installing")
    state.mark("failed", last_error="boom")
    state.mark("new")
    assert state.stage == "new"


def test_unknown_stage_rejected():
    with pytest.raises(SetupStateError):
        SetupState().mark("warp_speed")


def test_save_and_load_roundtrip(tmp_path):
    path = tmp_path / "state" / "setup_state.json"
    state = SetupState()
    state.mark(
        "installing",
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


def test_old_stage_names_are_mapped(tmp_path):
    """Old stage names from v1 state files are mapped to v2 equivalents."""
    path = tmp_path / "setup_state.json"
    path.write_text(json.dumps({"stage": "not_initialized"}), encoding="utf-8")
    state = load_state(path)
    assert state.stage == "new"

    path.write_text(json.dumps({"stage": "environment_ready"}), encoding="utf-8")
    state = load_state(path)
    assert state.stage == "discovering"

    path.write_text(json.dumps({"stage": "healthy"}), encoding="utf-8")
    state = load_state(path)
    assert state.stage == "ready"


def test_terminal_states():
    for stage in ("ready", "degraded", "blocked", "failed"):
        state = SetupState(stage=stage)
        assert state.is_terminal is True


def test_non_terminal_states():
    for stage in ("new", "discovering", "planned", "installing", "verifying"):
        state = SetupState(stage=stage)
        assert state.is_terminal is False


def test_completed_and_remaining_stages():
    state = SetupState(stage="installing")
    assert "discovering" in state.completed_stages
    assert "verifying" in state.remaining_stages
