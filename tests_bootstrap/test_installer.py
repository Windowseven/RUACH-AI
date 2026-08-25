import hashlib
from pathlib import Path

import pytest

from bootstrap.installer import (
    InstallError,
    _record_sha256,
    install_model,
    resolve_model_id,
)
from ruach_setup.registry import ModelEntry
from ruach_setup.state import SetupState


def entry_for(url: str, payload: bytes, sha: str) -> ModelEntry:
    return ModelEntry(
        id="test-model",
        family="test",
        parameters="tiny",
        format="gguf",
        quantization="Q0",
        file_name="test.gguf",
        download_size_bytes=len(payload),
        estimated_memory_bytes=len(payload) * 2,
        min_recommended_memory_bytes=len(payload),
        max_context_tokens=2048,
        quality_tier="light",
        speed_expectation="fast",
        status="experimental",
        source_url=url,
        sha256=sha,
    )


def write_registry(tmp_path: Path, entry: ModelEntry, sha_field: str | None = None) -> Path:
    registry = tmp_path / "models.toml"
    sha = entry.sha256 if sha_field is None else sha_field
    lines = [f'[models."{entry.id}"]']
    values = {
        "family": entry.family,
        "parameters": entry.parameters,
        "format": entry.format,
        "quantization": entry.quantization,
        "file_name": entry.file_name,
        "download_size_bytes": entry.download_size_bytes,
        "estimated_memory_bytes": entry.estimated_memory_bytes,
        "min_recommended_memory_bytes": entry.min_recommended_memory_bytes,
        "max_context_tokens": entry.max_context_tokens,
        "quality_tier": entry.quality_tier,
        "speed_expectation": entry.speed_expectation,
        "status": entry.status,
        "source_url": entry.source_url,
    }
    for key, value in values.items():
        lines.append(f"{key} = {value!r}" if isinstance(value, int) else f'{key} = "{value}"')
    lines.append(f'sha256 = "{sha}"')
    registry.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return registry


def test_install_downloads_verifies_and_marks_state(file_server, tmp_path):
    url, _handler, payload = file_server
    sha = hashlib.sha256(payload).hexdigest()
    registry = write_registry(tmp_path, entry_for(url, payload, sha))
    models_root = tmp_path / "artifacts"
    state = SetupState()

    result = install_model(
        "test-model", models_root, state, tmp_path / "state.json", registry_path=registry
    )

    assert result.path.read_bytes() == payload
    assert result.sha256 == sha
    assert not result.already_present
    assert not (result.path.parent / "test.gguf.part").exists()
    assert state.stage == "installing"
    assert (tmp_path / "state.json").is_file()


def test_install_is_idempotent_when_hash_matches(file_server, tmp_path):
    url, _handler, payload = file_server
    sha = hashlib.sha256(payload).hexdigest()
    registry = write_registry(tmp_path, entry_for(url, payload, sha))
    models_root = tmp_path / "artifacts"
    state = SetupState()

    install_model("test-model", models_root, state, tmp_path / "s.json", registry_path=registry)
    second = install_model(
        "test-model", models_root, SetupState(), tmp_path / "s2.json", registry_path=registry
    )

    assert second.already_present is True
    assert second.resumed is False


def test_existing_file_with_wrong_hash_fails_loudly(file_server, tmp_path):
    url, _handler, payload = file_server
    sha = hashlib.sha256(payload).hexdigest()
    registry = write_registry(tmp_path, entry_for(url, payload, sha))
    dest = tmp_path / "artifacts" / "test-model" / "test.gguf"
    dest.parent.mkdir(parents=True)
    dest.write_bytes(b"corrupted leftovers")

    with pytest.raises(InstallError, match="does not match"):
        install_model(
            "test-model",
            tmp_path / "artifacts",
            SetupState(),
            tmp_path / "s.json",
            registry_path=registry,
        )


def test_insufficient_storage_blocks_before_download(file_server, tmp_path):
    url, handler, payload = file_server
    sha = hashlib.sha256(payload).hexdigest()
    huge = ModelEntry(
        **{
            **entry_for(url, payload, sha).__dict__,
            "download_size_bytes": 10**20,
        }
    )
    registry = write_registry(tmp_path, huge)

    with pytest.raises(InstallError, match="INSUFFICIENT_STORAGE"):
        install_model(
            "test-model",
            tmp_path / "artifacts",
            SetupState(),
            tmp_path / "s.json",
            registry_path=registry,
        )
    assert handler.range_hits == []


def test_checksum_mismatch_during_download_cleans_part(file_server, tmp_path):
    url, _handler, payload = file_server
    wrong_sha = "0" * 64
    registry = write_registry(tmp_path, entry_for(url, payload, wrong_sha))

    with pytest.raises(InstallError, match="SHA-256 mismatch"):
        install_model(
            "test-model",
            tmp_path / "artifacts",
            SetupState(),
            tmp_path / "s.json",
            registry_path=registry,
        )
    part = tmp_path / "artifacts" / "test-model" / "test.gguf.part"
    assert not part.exists()


def test_tofu_records_sha_into_empty_registry_field(file_server, tmp_path):
    url, _handler, payload = file_server
    registry = write_registry(tmp_path, entry_for(url, payload, ""), sha_field="")
    models_root = tmp_path / "artifacts"

    result = install_model(
        "test-model", models_root, SetupState(), tmp_path / "s.json", registry_path=registry
    )

    text = registry.read_text(encoding="utf-8")
    assert result.sha256 in text
    assert 'sha256 = ""' not in text


def test_record_sha_never_overwrites_existing_value(tmp_path):
    registry = tmp_path / "models.toml"
    registry.write_text('[models."x"]\nsha256 = "existing"\n', encoding="utf-8")
    changed = _record_sha256(registry, "x", "newhash")
    assert changed is False
    assert 'sha256 = "existing"' in registry.read_text(encoding="utf-8")


def test_resolve_unknown_id_returns_none():
    assert resolve_model_id("does-not-exist") is None


def test_runtime_install_checks_toolchain(tmp_path, monkeypatch):
    import shutil as _shutil

    monkeypatch.setattr(_shutil, "which", lambda name: None)
    from bootstrap.installer import install_runtime

    with pytest.raises(InstallError, match="cmake not found|no C compiler|make not found"):
        install_runtime(home=tmp_path)
