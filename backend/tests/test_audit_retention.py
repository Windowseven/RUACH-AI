"""P11A tests: audit-log rotation, retention boundary, failure behavior."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from app.application.tools.audit import AuditLog, AuditWriteError


def _log(tmp_path: Path, max_bytes: int, segments: int) -> AuditLog:
    return AuditLog(
        tmp_path / "audit.jsonl", clock=lambda: 1.0, max_bytes=max_bytes, retention_segments=segments
    )


def test_small_log_stays_in_active_segment(tmp_path: Path) -> None:
    log = _log(tmp_path, max_bytes=10_000, segments=2)
    log.emit("tool_executed", capability="filesystem.read")
    assert log.read_all()[0]["event"] == "tool_executed"
    assert not (tmp_path / "audit.jsonl.1").exists()


def test_rotation_renames_and_shifts_segments(tmp_path: Path) -> None:
    log = _log(tmp_path, max_bytes=120, segments=2)
    for index in range(6):
        log.emit("event", index=index)

    active = (tmp_path / "audit.jsonl").read_text().splitlines()
    seg1 = (tmp_path / "audit.jsonl.1").read_text().splitlines()
    seg2 = (tmp_path / "audit.jsonl.2").read_text().splitlines()
    assert not (tmp_path / "audit.jsonl.3").exists(), "retention cap enforced"

    ordered = [
        json.loads(line)["index"]
        for segment in (seg2, seg1, active)
        for line in segment
    ]
    # With 6 events and a tiny cap the oldest segment(s) aged out; what
    # remains must be contiguous, ordered, and end at index 5.
    assert ordered[-1] == 5
    assert ordered == sorted(ordered)
    assert len(ordered) >= 3


def test_oldest_segment_deleted_only_by_documented_retention(
    tmp_path: Path,
) -> None:
    log = _log(tmp_path, max_bytes=100, segments=1)
    for index in range(8):
        log.emit("event", index=index)
    assert (tmp_path / "audit.jsonl.1").exists()
    assert not (tmp_path / "audit.jsonl.2").exists(), "only N rotated segments kept"


def test_read_all_returns_chronological_evidence_across_segments(
    tmp_path: Path,
) -> None:
    log = _log(tmp_path, max_bytes=120, segments=2)
    emitted = [f"e{i}" for i in range(5)]
    for name in emitted:
        log.emit("event", name=name)
    names = [record["name"] for record in log.read_all()]
    assert names[-1] == "e4"
    assert names == sorted(names)


def test_write_failure_raises_audit_write_error_never_silent(
    tmp_path: Path, monkeypatch
) -> None:
    log = _log(tmp_path, max_bytes=10_000, segments=2)
    real_open = Path.open

    def broken_open(self, *args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(Path, "open", broken_open)
    with pytest.raises(AuditWriteError):
        log.emit("tool_executed")
    monkeypatch.setattr(Path, "open", real_open)
    assert log.read_all() == [], "failed write must not leave partial evidence"


def test_zero_retention_documents_active_only_behavior(tmp_path: Path) -> None:
    log = _log(tmp_path, max_bytes=80, segments=0)
    log.emit("first")
    log.emit("second")
    records = log.read_all()
    assert all(record["event"] in {"first", "second"} for record in records)
    assert not any(p.name.startswith("audit.jsonl.") for p in tmp_path.iterdir())
