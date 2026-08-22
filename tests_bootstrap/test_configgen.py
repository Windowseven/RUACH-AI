from pathlib import Path

from bootstrap.configgen import build_env_content, env_entries_for_model, write_env


def test_env_content_is_sorted_and_deterministic():
    first = build_env_content({"RUACH_B": "2", "RUACH_A": "1"})
    second = build_env_content({"RUACH_A": "1", "RUACH_B": "2"})
    assert first == second
    assert first == "RUACH_A=1\nRUACH_B=2\n"


def test_env_entries_match_backend_settings_contract():
    entries = env_entries_for_model(
        runtime_id="llama_cpp",
        model_name="qwen3",
        model_path=Path("/data/models/q.gguf"),
        server_url="http://127.0.0.1:8080",
        timeout_seconds=120.0,
    )
    assert entries == {
        "RUACH_MODEL_RUNTIME": "llama_cpp",
        "RUACH_MODEL_NAME": "qwen3",
        "RUACH_MODEL_PATH": "/data/models/q.gguf",
        "RUACH_MODEL_SERVER_URL": "http://127.0.0.1:8080",
        "RUACH_INFERENCE_TIMEOUT_SECONDS": "120.0",
    }


def test_write_env_atomic_no_leftovers(tmp_path):
    target = tmp_path / "config" / "ruach.env"
    write_env(target, {"RUACH_X": "42"})
    assert target.read_text(encoding="utf-8") == "RUACH_X=42\n"
    assert not (tmp_path / "config" / "ruach.env.tmp").exists()
