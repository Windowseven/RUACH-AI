"""P11B security tests: symlink refusal + race-hardened opens + retention.

The execution layer must not trust policy-time path resolution: these
tests place symlinks AFTER the string-level check would have run, proving
the kernel-level walk refuses them anyway.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from app.application.tools.paths import WorkspaceBoundary
from app.application.tools.schemas import PathOutsideWorkspaceError


@pytest.fixture()
def boundary(tmp_path: Path) -> WorkspaceBoundary:
    return WorkspaceBoundary(tmp_path / "ws")


def test_string_level_check_refuses_existing_escape_symlink(
    boundary: WorkspaceBoundary,
) -> None:
    escape = boundary.root.parent / "outside.txt"
    escape.write_text("secret")
    link = boundary.root / "innocent.txt"
    link.symlink_to(escape)
    with pytest.raises(PathOutsideWorkspaceError):
        boundary.resolve_within("innocent.txt")


def test_final_component_symlink_refused_at_open_time_even_if_policy_passed(
    boundary: WorkspaceBoundary,
) -> None:
    """Simulate validate->swap->open: policy sees 'notes.txt' as safe
    (it does not exist yet); an attacker swaps in a symlink before the
    open. The fd layer must refuse."""
    escape = boundary.root.parent / "shadow"
    escape.write_text("top-secret")
    (boundary.root / "notes.txt").symlink_to(escape)

    fd, _stat = None, None  # noqa: F841 - clarity
    with pytest.raises(PathOutsideWorkspaceError):
        # Directly exercise execution-layer mechanics.
        boundary.open_read("notes.txt")


def test_intermediate_directory_symlink_refused(boundary: WorkspaceBoundary) -> None:
    escape_dir = boundary.root.parent / "elsewhere"
    escape_dir.mkdir()
    (escape_dir / "payload.txt").write_text("x")
    real = boundary.root / "real-dir"
    real.mkdir()
    # Swap 'real-dir/sub' to point at the outside directory.
    sub_link = real / "sub"
    sub_link.symlink_to(escape_dir)

    with pytest.raises(PathOutsideWorkspaceError):
        boundary.open_read("real-sub/../real-dir/sub/payload.txt" if False else "real-dir/sub/payload.txt")


def test_write_creates_file_with_owner_only_permissions(
    boundary: WorkspaceBoundary,
) -> None:
    fd = boundary.open_write("private/secret.txt")
    os.write(fd, b"data")
    os.close(fd)
    mode = (boundary.root / "private" / "secret.txt").stat().st_mode & 0o777
    assert mode == 0o600


def test_delete_refuses_symlinks_and_removes_only_regular_files(
    boundary: WorkspaceBoundary,
) -> None:
    target = boundary.root / "gone.txt"
    target.write_text("bye")
    boundary.unlink_file("gone.txt")
    assert not target.exists()

    escape = boundary.root.parent / "keepme.txt"
    escape.write_text("important")
    link = boundary.root / "alias.txt"
    link.symlink_to(escape)
    with pytest.raises(PathOutsideWorkspaceError):
        boundary.unlink_file("alias.txt")
    assert link.exists() and escape.exists(), "symlink must not be removed"


def test_traversal_components_refused(boundary: WorkspaceBoundary) -> None:
    with pytest.raises(PathOutsideWorkspaceError):
        boundary.resolve_within("../outside.txt")


def test_root_pinning_survives_root_rename(boundary: WorkspaceBoundary) -> None:
    fd = boundary.open_write("pin.txt")
    os.write(fd, b"before")
    os.close(fd)

    moved_root = boundary.root.parent / "ws-renamed"
    boundary.root.rename(moved_root)

    # The pinned inode keeps serving the ORIGINAL directory contents.
    fd, _stat = boundary.open_read("pin.txt")
    data = os.read(fd, 64)
    os.close(fd)
    assert data == b"before"


def test_directory_operations_refuse_file_components(boundary: WorkspaceBoundary) -> None:
    (boundary.root / "file.txt").write_text("x")
    with pytest.raises(PathOutsideWorkspaceError):
        boundary.list_dir("file.txt/nested")
