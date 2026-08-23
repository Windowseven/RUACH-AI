"""Workspace path boundary: normalize, resolve, contain (docs/05 §14–§17).

Security review P11B — TOCTOU / symlink hardening:

The historical implementation resolved the candidate path, checked
containment, THEN opened it by name. Between check and open an attacker
able to write inside the workspace could swap in a symlink so the open
landed on an arbitrary target ("validate path -> attacker changes path ->
open different target").

All resolution now happens through kernel directory file descriptors:
the workspace root fd is pinned at construction, every INTERMEDIATE
component is opened with O_NOFOLLOW|O_DIRECTORY (symlinks refused,
ELOOP -> PathOutsideWorkspaceError), and final components are opened/
unlinked with O_NOFOLLOW / follow_symlinks=False directly under the
parent descriptor. No symlink anywhere in the requested path is ever
followed during an operation.

Honest residual limitations (documented, not hidden):

- A concurrently swapped REAL directory component (not a symlink) stays
  inside the workspace by construction; escaping still requires a
  symlink, which cannot be followed.
- The pinned root fd means renaming/replacing the root directory cannot
  redirect operations.
- Policy/approval binds argument STRINGS, not inodes: content swapped
  under the same approved name between approval and execution executes
  on the new content under that name. Accepted limitation.
- Hardlink escapes require write access outside the model's reach;
  treated as out of scope.
"""

from __future__ import annotations

import errno
import os
import stat as stat_module
from pathlib import Path

from .schemas import PathOutsideWorkspaceError

_DIRFLAGS = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_DIRECTORY", 0)


class WorkspaceBoundary:
    def __init__(self, root: Path) -> None:
        if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
            raise RuntimeError(
                "This platform lacks O_NOFOLLOW/O_DIRECTORY; the workspace "
                "boundary refuses to operate without symlink protection."
            )
        root = Path(root)
        self._root_strict = root.resolve()
        self._root_strict.mkdir(parents=True, exist_ok=True)
        # Pin the root inode for the lifetime of the boundary.
        self._root_fd = os.open(self._root_strict, _DIRFLAGS)

    @property
    def root(self) -> Path:
        return self._root_strict

    # ------------------------------------------------------------- policy

    def resolve_within(self, raw_path: str) -> Path:
        """Policy-time containment check (string level, symlink-aware).

        Returns the would-be real path for audit/policy purposes. The
        execution layer independently re-derives everything through the
        dirfd walk, so this string-level check alone is not the security
        control anymore.
        """
        relative = self._relative_form(raw_path)
        resolved = (self._root_strict / relative).resolve(strict=False)
        try:
            resolved.relative_to(self._root_strict)
        except ValueError as exc:
            raise PathOutsideWorkspaceError(
                "Path escapes the approved workspace"
            ) from exc
        return resolved

    def _relative_form(self, raw_path: str) -> Path:
        if not isinstance(raw_path, str) or not raw_path.strip():
            raise PathOutsideWorkspaceError("Path must be a non-empty string")
        if "\x00" in raw_path:
            raise PathOutsideWorkspaceError("Path contains null byte")
        candidate = Path(raw_path)
        if candidate.is_absolute():
            try:
                return candidate.resolve(strict=False).relative_to(self._root_strict)
            except ValueError as exc:
                raise PathOutsideWorkspaceError(
                    "Path escapes the approved workspace"
                ) from exc
        return candidate

    @staticmethod
    def _clean_parts(relative: Path) -> list[str]:
        parts = [part for part in relative.parts if part != "."]
        if any(part == ".." for part in parts):
            # '..' could never leave the pinned root through dir_fd
            # chaining, but refusing keeps mechanics aligned with policy.
            raise PathOutsideWorkspaceError("Path traversal components are refused")
        return parts

    def _open_dir_chain(self, parts: list[str], *, create_parents: bool) -> int:
        """Open (optionally create) each part as a REAL directory under the
        pinned root. Symlinks are refused at every step (ELOOP)."""
        current_fd = os.dup(self._root_fd)
        try:
            for part in parts:
                try:
                    next_fd = os.open(part, _DIRFLAGS, dir_fd=current_fd)
                except FileNotFoundError:
                    if not create_parents:
                        raise
                    os.mkdir(part, 0o700, dir_fd=current_fd)
                    next_fd = os.open(part, _DIRFLAGS, dir_fd=current_fd)
                except FileExistsError:
                    raise PathOutsideWorkspaceError(
                        "A non-directory occupies the request path"
                    )
                except NotADirectoryError as error:
                    raise PathOutsideWorkspaceError(
                        "Path component is not a directory"
                    ) from error
                except OSError as error:
                    if error.errno == errno.ELOOP:
                        raise PathOutsideWorkspaceError(
                            "Symbolic links are refused inside request paths"
                        ) from error
                    raise
                os.close(current_fd)
                current_fd = next_fd
            return current_fd
        except BaseException:
            os.close(current_fd)
            raise

    def _split(self, raw_path: str) -> tuple[int, str]:
        """Return (parent_dir_fd, final_name); caller owns the fd."""
        parts = self._clean_parts(self._relative_form(raw_path))
        if not parts:
            raise PathOutsideWorkspaceError("Path names the workspace itself")
        parent_parts, name = parts[:-1], parts[-1]
        parent_fd = self._open_dir_chain(parent_parts, create_parents=False)
        return parent_fd, name

    # ------------------------------------------------------------ operations

    def open_read(self, raw_path: str) -> tuple[int, os.stat_result]:
        """Open a REGULAR file for reading without following symlinks."""
        parent_fd, name = self._split(raw_path)
        flags = os.O_RDONLY | os.O_NOFOLLOW
        try:
            fd = os.open(name, flags, dir_fd=parent_fd)
        except OSError as error:
            if error.errno == errno.ELOOP:
                raise PathOutsideWorkspaceError(
                    "Symbolic links are refused inside request paths"
                ) from error
            raise
        finally:
            os.close(parent_fd)
        try:
            info = os.fstat(fd)
            if not stat_module.S_ISREG(info.st_mode):
                raise PathOutsideWorkspaceError("Target is not a regular file")
        except BaseException:
            os.close(fd)
            raise
        return fd, info

    def open_write(self, raw_path: str) -> int:
        """Create/truncate a REGULAR file without following symlinks,
        creating missing parents inside the workspace."""
        relative = self._relative_form(raw_path)
        parts = self._clean_parts(relative)
        if not parts:
            raise PathOutsideWorkspaceError("Path names the workspace itself")
        parent_fd = self._open_dir_chain(parts[:-1], create_parents=True)
        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW
        try:
            fd = os.open(parts[-1], flags, 0o600, dir_fd=parent_fd)
        except OSError as error:
            if error.errno == errno.ELOOP:
                raise PathOutsideWorkspaceError(
                    "Symbolic links are refused inside request paths"
                ) from error
            raise
        finally:
            os.close(parent_fd)
        return fd

    def unlink_file(self, raw_path: str) -> None:
        """Unlink a REGULAR file; never follows a final symlink."""
        parent_fd, name = self._split(raw_path)
        try:
            info = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
            if not stat_module.S_ISREG(info.st_mode):
                raise PathOutsideWorkspaceError("Target is not a regular file")
            os.unlink(name, dir_fd=parent_fd)
        finally:
            os.close(parent_fd)

    def list_dir(self, raw_path: str) -> list[str]:
        parts = self._clean_parts(self._relative_form(raw_path))
        fd = self._open_dir_chain(parts, create_parents=False)
        try:
            return sorted(os.listdir(fd))
        finally:
            os.close(fd)
