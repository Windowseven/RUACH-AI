from pathlib import Path

from ruach_setup.preflight import check_storage


def test_sufficient_space_passes(tmp_path: Path):
    check = check_storage(tmp_path, required_bytes=1024)
    assert check.ok
    assert check.required_bytes == 1126  # 1024 + 10% margin


def test_impossible_requirement_fails(tmp_path: Path):
    check = check_storage(tmp_path, required_bytes=10**20)
    assert not check.ok
    assert check.available_bytes > 0


def test_custom_margin(tmp_path: Path):
    check = check_storage(tmp_path, required_bytes=1000, margin_percent=50)
    assert check.required_bytes == 1500


def test_nonexistent_dir_probes_parent(tmp_path: Path):
    target = tmp_path / "models" / "qwen"
    check = check_storage(target, required_bytes=1024)
    assert check.ok
