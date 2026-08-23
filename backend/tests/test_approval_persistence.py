"""P4 acceptance proofs: approvals survive restarts and expire honestly.

Directive docs/13 P4 #12. Every "restart" is simulated by destroying the
store/engine objects and constructing brand-new instances over the SAME
database file -- exactly what happens when the server process restarts.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from app.application.tools.approvals import action_fingerprint
from app.application.tools.audit import AuditLog
from app.application.tools.engine import ToolEngine
from app.application.tools.paths import WorkspaceBoundary
from app.application.tools.schemas import ApprovalError, ToolRequest
from app.infrastructure.approval_store_db import PersistentApprovalStore
from app.infrastructure.db import create_session_factory, get_engine
from app.infrastructure.models import Base


class FakeClock:
    def __init__(self) -> None:
        self.now = 1_000_000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


DB_NAME = "approvals.db"
TTL = 900.0


def make_store(db_path: Path, clock: FakeClock | None = None) -> PersistentApprovalStore:
    kwargs: dict[str, Any] = {"ttl_seconds": TTL}
    if clock is not None:
        kwargs["clock"] = clock
    return PersistentApprovalStore(create_session_factory(f"sqlite:///{db_path}"), **kwargs)


def make_engine(workspace: Path, db_path: Path) -> ToolEngine:
    return ToolEngine(
        WorkspaceBoundary(workspace),
        make_store(db_path),
        AuditLog(db_path.parent / "audit.jsonl"),
    )


def new_conversation(db_path: Path) -> str:
    """A REAL conversation row: production approvals always reference one."""
    from app.application.repositories import ConversationRepository

    factory = create_session_factory(f"sqlite:///{db_path}")
    session = factory()
    try:
        conversation = ConversationRepository(session).create("t")
        session.commit()
        return conversation.id
    finally:
        session.close()


@pytest.fixture()
def env(tmp_path: Path) -> tuple[Path, Path]:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    db = tmp_path / DB_NAME
    # Test-only schema bootstrap; production path is Alembic (P5 gate).
    Base.metadata.create_all(get_engine(f"sqlite:///{db}"))
    return workspace, db


# ---------------------------------------------------------------- Test A
def test_restart_survival_pending(env: tuple[Path, Path]) -> None:
    _workspace, db = env
    store = make_store(db)
    record = store.create_pending(
        "filesystem", "filesystem.delete", {"path": "a.txt"}, "a.txt"
    )

    del store  # process "restarts"

    revived = make_store(db).get(record.approval_id)
    assert revived.state.value == "PENDING"
    assert revived.arguments == {"path": "a.txt"}
    assert revived.tool == "filesystem"


# ---------------------------------------------------------------- Test B
def test_approval_persists_after_resolution(env: tuple[Path, Path]) -> None:
    _, db = env
    store = make_store(db)
    record = store.create_pending("filesystem", "filesystem.delete", {"path": "b.txt"}, None)
    fingerprint = action_fingerprint("filesystem", "filesystem.delete", {"path": "b.txt"})

    approved = store.approve(record.approval_id, fingerprint)

    assert approved.state.value == "APPROVED"
    assert approved.decision == "approved"
    # Visible from a brand-new store instance (i.e., after restart).
    persisted = make_store(db).get(record.approval_id)
    assert persisted.state.value == "APPROVED"
    assert persisted.decision == "approved"


# ---------------------------------------------------------------- Test C
def test_rejection_persists(env: tuple[Path, Path]) -> None:
    _, db = env
    store = make_store(db)
    record = store.create_pending("filesystem", "filesystem.delete", {"path": "c.txt"}, None)
    store.reject(record.approval_id)

    persisted = make_store(db).peek(record.approval_id)
    assert persisted is not None
    assert persisted.state.value == "REJECTED"
    assert persisted.decision == "rejected"


# ---------------------------------------------------------------- Test D
def test_ttl_expiration_is_explicit_and_persisted(env: tuple[Path, Path]) -> None:
    _, db = env
    clock = FakeClock()
    store = make_store(db, clock)
    record = store.create_pending("filesystem", "filesystem.delete", {"path": "d.txt"}, None)

    clock.advance(TTL + 1)
    with pytest.raises(ApprovalError):
        store.get(record.approval_id)

    # The transition is durable and honest, not a silent read-time lie.
    persisted = make_store(db).peek(record.approval_id)
    assert persisted is not None
    assert persisted.state.value == "EXPIRED"
    assert persisted.decision == "system_expired"


# ---------------------------------------------------------------- Test E
def test_startup_sweep_expires_only_stale(env: tuple[Path, Path]) -> None:
    _, db = env
    clock = FakeClock()
    store = make_store(db, clock)
    stale_ids = [
        store.create_pending("filesystem", "filesystem.delete", {"path": f"s{i}.txt"}, None).approval_id
        for i in range(3)
    ]
    clock.advance(10)
    fresh_id = store.create_pending(
        "filesystem", "filesystem.delete", {"path": "fresh.txt"}, None
    ).approval_id
    clock.advance(TTL)  # stale trio expires, fresh has ~890s left

    del store
    swept = make_store(db, clock).expire_stale()

    assert swept == 3
    revived = make_store(db, clock)
    for approval_id in stale_ids:
        assert revived.peek(approval_id).state.value == "EXPIRED"  # type: ignore[union-attr]
    assert revived.peek(fresh_id).state.value == "PENDING"  # type: ignore[union-attr]
    # Idempotent: second sweep finds nothing.
    assert revived.expire_stale() == 0


# ---------------------------------------------------------------- Test F
def test_fingerprint_binding_survives_restart(env: tuple[Path, Path]) -> None:
    workspace, db = env
    target = workspace / "f.txt"
    target.write_text("data", encoding="utf-8")

    first_engine = make_engine(workspace, db)
    outcome = first_engine.submit(
        ToolRequest(tool="filesystem", capability="filesystem.delete", arguments={"path": "f.txt"}),
        conversation_id=new_conversation(db),
    )
    assert outcome.state == "AWAITING_APPROVAL"
    approval_id = outcome.approval_id
    assert approval_id is not None

    restarted_engine = make_engine(workspace, db)  # "restart"

    # A modified request must NOT be accepted as the original approval.
    tampered = action_fingerprint("filesystem", "filesystem.delete", {"path": "OTHER.txt"})
    with pytest.raises(ApprovalError):
        make_store(db).approve(approval_id, tampered)
    # Still PENDING: the tampered attempt changed nothing.
    assert restarted_engine._approvals.peek(approval_id).state.value == "PENDING"  # type: ignore[attr-defined]

    # Correct fingerprint through the public engine path executes for real.
    result = restarted_engine.approve_and_execute(approval_id)
    assert result.state == "COMPLETED"
    assert not target.exists()


# ------------------------------------------------- Engine-level restart flow
def test_full_approval_flow_across_restart(env: tuple[Path, Path]) -> None:
    workspace, db = env
    (workspace / "g.txt").write_text("x", encoding="utf-8")

    engine_a = make_engine(workspace, db)
    pending = engine_a.submit(
        ToolRequest(tool="filesystem", capability="filesystem.delete", arguments={"path": "g.txt"}),
        conversation_id=new_conversation(db),
    )
    assert pending.approval_id is not None

    engine_b = make_engine(workspace, db)
    info = engine_b.approval_info(pending.approval_id)
    assert info is not None and info.state.value == "PENDING"
    assert engine_b.pending_conversation(pending.approval_id) is not None

    executed = engine_b.approve_and_execute(pending.approval_id)
    assert executed.state == "COMPLETED"
    record = make_store(db).peek(pending.approval_id)
    assert record is not None
    assert record.state.value == "CONSUMED"


# ------------------------------------------------- Arguments round-trip
def test_arguments_json_round_trip_preserves_content(env: tuple[Path, Path]) -> None:
    _, db = env
    args = {"path": "n.txt", "content": "line1\nline2 \"quoted\"", "mode": "overwrite"}
    store = make_store(db)
    record = store.create_pending("filesystem", "filesystem.write", args, "n.txt")
    revived = make_store(db).get(record.approval_id)
    assert revived.arguments == json.loads(json.dumps(args))


# ------------------------------------- Infrastructure failure classification
def test_store_outage_is_system_error_not_denial(
    env: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """docs/13 P4 #8/#9/#16c: a DB failure must NOT become a security event."""
    workspace, db = env
    (workspace / "h.txt").write_text("x", encoding="utf-8")
    audit_path = db.parent / "audit.jsonl"
    engine = ToolEngine(
        WorkspaceBoundary(workspace),
        make_store(db),
        AuditLog(audit_path),
    )
    pending = engine.submit(
        ToolRequest(tool="filesystem", capability="filesystem.delete", arguments={"path": "h.txt"}),
        conversation_id=new_conversation(db),
    )
    approval_id = pending.approval_id
    assert approval_id is not None

    # Store breaks the moment we try to resolve the approval.
    def broken_approve(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("database is locked")

    monkeypatch.setattr(engine._approvals, "approve", broken_approve)
    outcome = engine.approve_and_execute(approval_id)

    assert outcome.state == "SYSTEM_ERROR"
    assert "security" not in outcome.reason.lower()
    assert not _has_event(audit_path, "tool_denied")
    error = _last_event(audit_path, "tool_execution_error")
    assert error["category"] == "infrastructure"
    assert error["error_type"] == "RuntimeError"
    assert (workspace / "h.txt").exists(), "fail-closed: nothing may execute"


def test_policy_denial_still_audited_as_security_event(env: tuple[Path, Path]) -> None:
    """The split must not weaken real policy denials."""
    workspace, db = env
    outside = db.parent / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    audit_path = db.parent / "audit.jsonl"
    engine = ToolEngine(WorkspaceBoundary(workspace), make_store(db), AuditLog(audit_path))

    outcome = engine.submit(
        ToolRequest(tool="filesystem", capability="filesystem.read", arguments={"path": str(outside)}),
    )

    assert outcome.state == "DENIED"
    assert _has_event(audit_path, "security_violation")


# ----------------------------------------------------------------- helpers
def _events(audit_path: Path) -> list[dict[str, Any]]:
    if not audit_path.exists():
        return []
    return [
        json.loads(line)
        for line in audit_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _has_event(audit_path: Path, event: str) -> bool:
    return any(e.get("event") == event for e in _events(audit_path))


def _last_event(audit_path: Path, event: str) -> dict[str, Any]:
    matches = [e for e in _events(audit_path) if e.get("event") == event]
    assert matches, f"expected a {event} event"
    return matches[-1]
