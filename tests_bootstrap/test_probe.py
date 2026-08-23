"""P13 tests: the probe records evidence, never guesses.

Contract under test:
- every section reports status measured|unavailable|skipped (+ reason)
- missing things produce honest unavailable sections, not crashes
- percentile math is correct
- records are written to ~/.ruach/benchmarks as JSON (redirected home)
"""

from __future__ import annotations

import json
from pathlib import Path

from bootstrap import probe


def test_every_section_has_status_data_reason() -> None:
    report = _collect()
    for name, section in report["environment_sections"].items():
        assert section["status"] in {"measured", "unavailable", "skipped"}, name
        assert "reason" in section and "data" in section, name


def test_unreachable_inference_is_skipped_not_faked(monkeypatch) -> None:
    monkeypatch.setattr(
        probe,
        "collect_inference_latency",
        lambda url, quick, real: probe._section(
            "skipped", reason=f"inference endpoint unreachable at {url}: refused"
        ),
    )
    sections = _collect(inference_url="http://127.0.0.1:1")["environment_sections"]
    latency = sections["inference_latency"]
    assert latency["status"] == "skipped"
    assert "unreachable" in latency["reason"]


def test_missing_model_artifact_reports_honestly(monkeypatch) -> None:
    import os

    monkeypatch.setenv("RUACH_MODEL_PATH", "/nowhere/real.gguf")
    section = probe.collect_model_artifact(dict(os.environ))
    assert section["status"] == "unavailable"
    assert "missing file" in section["reason"]


def test_percentiles_match_sorted_statistics() -> None:
    stats = probe._percentiles([1.0, 2.0, 3.0, 4.0, 100.0])
    assert stats["min_s"] == 1.0
    assert stats["max_s"] == 100.0
    assert stats["p50_s"] == 3.0  # middle of sorted list
    assert stats["p95_s"] == 100.0  # round(0.95*4)=4 -> last element
    assert abs(stats["mean_s"] - 22.0) < 0.01


def test_dependency_probe_reports_missing_packages_individually(monkeypatch) -> None:
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "httpx":
            raise ImportError("No module named 'httpx'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    section = probe.collect_dependencies()
    assert section["status"] == "measured"  # the SECTION ran; entries differ
    results = section["data"]
    assert results["httpx"]["status"] == "unavailable"
    assert results["fastapi"]["status"] == "measured"
    assert "httpx" in section["reason"]


def test_run_probe_writes_record_and_summary(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("RUACH_MODEL_SERVER_URL", raising=False)
    config_dir = tmp_path / ".ruach" / "config"
    config_dir.mkdir(parents=True)
    # no generated config -> inference skipped honestly

    out_path = probe.run_probe(echo=lambda *_: None)
    record = json.loads(out_path.read_text())
    assert record["schema_version"] == 1
    assert out_path.parent == tmp_path / ".ruach" / "benchmarks"
    assert out_path.name.startswith("probe-") and out_path.suffix == ".json"

    printed = capsys.readouterr().out  # echo suppressed -> nothing
    assert printed == ""
    sections = record["environment_sections"]
    assert sections["python"]["data"]["version"]
    assert sections["sqlite"]["data"]["wal_supported"] is True
    storage = sections["storage_paths"]["data"]
    assert all(item["writable"] for item in storage.values())


def _collect(**kwargs) -> dict:
    out_path = probe.run_probe(echo=lambda *_: None, **kwargs)
    return json.loads(out_path.read_text())
