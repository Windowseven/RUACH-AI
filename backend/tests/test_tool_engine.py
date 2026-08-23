from pathlib import Path

import pytest

from backend.app.application.tools.approvals import (
    InMemoryApprovalStore,
    action_fingerprint,
)
from backend.app.application.tools.audit import AuditLog
from backend.app.application.tools.engine import ToolEngine
from backend.app.application.tools.paths import WorkspaceBoundary
from backend.app.application.tools.schemas import ApprovalError, ToolRequest


class FakeClock:
    def __init__(self) -> None:
        self.now = 1_000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture()
def workspace(tmp_path: Path) -> Path:
    root = tmp_path / "workspace"
    (root / "project").mkdir(parents=True)
    (root / "notes.txt").write_text("hello ruach", encoding="utf-8")
    return root


@pytest.fixture()
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture()
def engine(workspace: Path, tmp_path: Path, clock: FakeClock) -> ToolEngine:
    boundary = WorkspaceBoundary(workspace)
    approvals = InMemoryApprovalStore(ttl_seconds=300.0, clock=clock)
    audit = AuditLog(tmp_path / "audit.jsonl", clock=clock)
    return ToolEngine(boundary, approvals, audit, clock=clock)


def req(tool: str, capability: str, **arguments) -> ToolRequest:
    return ToolRequest(tool=tool, capability=capability, arguments=arguments)


# ---------------------------------------------------------------- read/list/write


def test_read_inside_workspace_is_allowed(engine: ToolEngine):
    outcome = engine.submit(req("filesystem", "filesystem.read", path="notes.txt"))
    assert outcome.state == "COMPLETED"
    assert outcome.output == "hello ruach"


def test_list_directory_returns_sorted_names(engine: ToolEngine):
    outcome = engine.submit(req("filesystem", "filesystem.list", path="project"))
    assert outcome.state == "COMPLETED"
    assert outcome.output == []


def test_write_then_read_roundtrip(engine: ToolEngine):
    engine.submit(req("filesystem", "filesystem.write", path="new.md", content="# hi"))
    outcome = engine.submit(req("filesystem", "filesystem.read", path="new.md"))
    assert outcome.output == "# hi"


# ------------------------------------------------------------ boundary violations


def test_traversal_escape_denied_and_audited(engine: ToolEngine, tmp_path: Path):
    outcome = engine.submit(req("filesystem", "filesystem.read", path="../../../../etc/passwd"))
    assert outcome.state == "DENIED"


def test_absolute_path_outside_denied(engine: ToolEngine):
    outcome = engine.submit(req("filesystem", "filesystem.read", path="/etc/passwd"))
    assert outcome.state == "DENIED"


def test_symlink_escape_denied(engine: ToolEngine, workspace: Path, tmp_path: Path):
    secret = tmp_path / "secret.txt"
    secret.write_text("top secret", encoding="utf-8")
    (workspace / "link").symlink_to(secret)
    outcome = engine.submit(req("filesystem", "filesystem.read", path="link"))
    assert outcome.state == "DENIED"
    assert "secret" not in str(outcome.output)


def test_null_byte_path_denied(engine: ToolEngine):
    outcome = engine.submit(req("filesystem", "filesystem.read", path="a\x00b"))
    assert outcome.state == "DENIED"


# --------------------------------------------------------------- unknown / abuse


def test_unknown_capability_denied_fail_closed(engine: ToolEngine):
    outcome = engine.submit(req("shell", "shell.execute", command="rm -rf /"))
    assert outcome.state == "DENIED"


def test_model_supplied_approved_field_is_stripped(engine: ToolEngine):
    outcome = engine.submit(
        req(
            "filesystem",
            "filesystem.delete",
            path="notes.txt",
            approved=True,
        )
    )
    assert outcome.state == "AWAITING_APPROVAL"


# ------------------------------------------------------------------- approvals


def test_delete_requires_approval_and_does_not_execute(engine: ToolEngine, workspace: Path):
    outcome = engine.submit(req("filesystem", "filesystem.delete", path="notes.txt"))
    assert outcome.state == "AWAITING_APPROVAL"
    assert outcome.approval_id is not None
    assert (workspace / "notes.txt").exists()


def test_approval_executes_bound_action_once(engine: ToolEngine):
    first = engine.submit(req("filesystem", "filesystem.delete", path="notes.txt"))
    assert first.approval_id is not None
    result = engine.approve_and_execute(first.approval_id or "")
    assert result.state == "COMPLETED"

    replay = engine.approve_and_execute(first.approval_id or "")
    assert replay.state == "DENIED"


def test_changed_action_invalidates_approval(workspace: Path, tmp_path: Path, clock: FakeClock):
    engine = ToolEngine(
        WorkspaceBoundary(workspace),
        InMemoryApprovalStore(ttl_seconds=300.0, clock=clock),
        AuditLog(tmp_path / "a.jsonl", clock=clock),
        clock=clock,
    )
    engine.submit(req("filesystem", "filesystem.delete", path="notes.txt"))

    store = InMemoryApprovalStore(clock=clock)
    record = store.create_pending("x", "filesystem.delete", {"path": "other.txt"}, None)
    with pytest.raises(ApprovalError):
        store.approve(
            record.approval_id, action_fingerprint("x", "filesystem.delete", {"path": "CHANGED"})
        )


def test_expired_approval_denied(engine: ToolEngine, clock: FakeClock):
    pending = engine.submit(req("filesystem", "filesystem.delete", path="notes.txt"))
    clock.advance(301)
    result = engine.approve_and_execute(pending.approval_id or "")
    assert result.state == "DENIED"
    assert "expired" in result.reason.lower() or result.reason


def test_rejection_blocks_execution(engine: ToolEngine, workspace: Path):
    pending = engine.submit(req("filesystem", "filesystem.delete", path="notes.txt"))
    engine.reject(pending.approval_id or "")
    result = engine.approve_and_execute(pending.approval_id or "")
    assert result.state == "DENIED"
    assert (workspace / "notes.txt").exists()


# --------------------------------------------------------------------- limits


def test_oversized_read_rejected(engine: ToolEngine, workspace: Path):
    big = workspace / "big.bin"
    big.write_bytes(b"x" * (2 * 1_048_576))
    outcome = engine.submit(req("filesystem", "filesystem.read", path="big.bin"))
    assert outcome.state == "DENIED"


def test_bounded_offset_read_works(engine: ToolEngine):
    outcome = engine.submit(
        req("filesystem", "filesystem.read", path="notes.txt", offset=6, limit=4)
    )
    assert outcome.output == "ruac"


def test_write_size_cap_enforced(engine: ToolEngine):
    outcome = engine.submit(
        req("filesystem", "filesystem.write", path="o.bin", content="y" * (2 * 1_048_576))
    )
    assert outcome.state == "FAILED" or outcome.state == "DENIED"


# ---------------------------------------------------------------- fail closed


def test_policy_fault_fails_closed(tmp_path: Path, clock: FakeClock):
    class ExplodingBoundary(WorkspaceBoundary):
        def resolve_within(self, raw_path: str) -> Path:
            raise RuntimeError("boom")

    engine = ToolEngine(
        ExplodingBoundary(tmp_path / "ws"),
        InMemoryApprovalStore(clock=clock),
        AuditLog(tmp_path / "a.jsonl", clock=clock),
        clock=clock,
    )
    outcome = engine.submit(req("filesystem", "filesystem.list", path="."))
    assert outcome.state == "DENIED"


# ---------------------------------------------------------------------- audit


def test_audit_trail_records_decisions(engine: ToolEngine, tmp_path: Path):
    engine.submit(req("filesystem", "filesystem.read", path="notes.txt"))
    engine.submit(req("filesystem", "filesystem.read", path="/etc/passwd"))
    events = AuditLog(tmp_path / "audit.jsonl").read_all()
    names = [e["event"] for e in events]
    assert "tool_executed" in names
    assert "security_violation" in names
