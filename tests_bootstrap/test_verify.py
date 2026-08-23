"""Tests for the Inc 12 MVP gate orchestration."""

from __future__ import annotations

from bootstrap.verify import (
    build_stages,
    classify_protected_turn,
    protected_turn_is_fail_closed,
)


def test_stage_list_contains_the_six_deterministic_stages() -> None:
    names = [stage.name for stage in build_stages(include_live=False)]
    assert names == [
        "doctor",
        "backend-unit",
        "bootstrap-tests",
        "fresh-install-twice-from-zero",
        "ui-build",
        "browser-e2e",
    ]
    assert all(stage.command is not None for stage in build_stages(include_live=False))


def test_live_flag_appends_live_smoke() -> None:
    stages = build_stages(include_live=True)
    assert stages[-1].name == "live-model-smoke"
    assert stages[-1].command is None


def test_classify_pending_branch() -> None:
    branch, detail = classify_protected_turn(
        {
            "pending_approval": {
                "approval_id": "abc",
                "capability": "filesystem.delete",
            },
            "content": "",
        }
    )
    assert branch == "pending"
    assert detail == "filesystem.delete"


def test_classify_surfaces_terminal_tool_state() -> None:
    branch, detail = classify_protected_turn(
        {"tool": {"state": "DENIED", "capability": "filesystem.write"}, "content": "..."}
    )
    assert branch == "tool"
    assert "DENIED" in detail


def test_classify_fail_closed_denial_via_honest_text() -> None:
    branch, _ = classify_protected_turn(
        {"content": "I did not perform this action. Reason: Content must be a string"}
    )
    assert branch == "denied"


def test_classify_flags_dishonest_turns_as_uncertain() -> None:
    branch, _ = classify_protected_turn({"content": "Sure, I deleted it!"})
    assert branch == "uncertain"


def test_fail_closed_invariant_uses_filesystem_truth_not_prose() -> None:
    # Model prose is noise; the file's existence is the fact.
    assert protected_turn_is_fail_closed(
        {"content": "Sure, I deleted it!"}, target_exists=True
    )
    assert not protected_turn_is_fail_closed(
        {"content": "Sure, I deleted it!"}, target_exists=False
    )
    assert protected_turn_is_fail_closed(
        {"pending_approval": {"approval_id": "x"}}, target_exists=True
    )
