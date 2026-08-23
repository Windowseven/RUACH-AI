"""Workspace path boundary: normalize, resolve, contain (docs/05 §14–§17)."""

from __future__ import annotations

from pathlib import Path

from .schemas import PathOutsideWorkspaceError


class WorkspaceBoundary:
    def __init__(self, root: Path) -> None:
        self._root = root.resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    @property
    def root(self) -> Path:
        return self._root

    def resolve_within(self, raw_path: str) -> Path:
        if not isinstance(raw_path, str) or not raw_path.strip():
            raise PathOutsideWorkspaceError("Path must be a non-empty string")
        if "\x00" in raw_path:
            raise PathOutsideWorkspaceError("Path contains null byte")

        candidate = Path(raw_path)
        if candidate.is_absolute():
            resolved = candidate.resolve(strict=False)
        else:
            resolved = (self._root / candidate).resolve(strict=False)

        try:
            resolved.relative_to(self._root)
        except ValueError as exc:
            raise PathOutsideWorkspaceError("Path escapes the approved workspace") from exc
        return resolved
