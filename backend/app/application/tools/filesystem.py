"""Bounded filesystem executor using direct OS APIs, never shell strings (docs/05 §12–§13)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .paths import WorkspaceBoundary

DEFAULT_MAX_READ_BYTES = 1_048_576  # 1 MiB per docs/05 §32
DEFAULT_MAX_WRITE_BYTES = 1_048_576
MAX_LIST_ENTRIES = 500


class FilesystemExecutor:
    def __init__(
        self,
        boundary: WorkspaceBoundary,
        max_read_bytes: int = DEFAULT_MAX_READ_BYTES,
        max_write_bytes: int = DEFAULT_MAX_WRITE_BYTES,
    ) -> None:
        self._boundary = boundary
        self._max_read = max_read_bytes
        self._max_write = max_write_bytes

    def read_file(self, arguments: dict[str, Any]) -> str:
        path = self._require_resolved(arguments)
        offset = self._bounded_int(arguments.get("offset", 0), "offset")
        raw_limit = arguments.get("limit")
        if raw_limit is None:
            remaining = max(path.stat().st_size - offset, 0)
            if remaining > self._max_read:
                raise ValueError(f"File exceeds the {self._max_read} byte read cap")
            limit = remaining
        else:
            limit = self._bounded_int(raw_limit, "limit")
            if limit > self._max_read:
                raise ValueError(f"Read limit exceeds {self._max_read} bytes")
        with path.open("rb") as handle:
            handle.seek(offset)
            data = handle.read(limit)
        return data.decode("utf-8", errors="replace")

    def list_directory(self, arguments: dict[str, Any]) -> list[str]:
        path = self._require_resolved(arguments)
        entries = sorted(entry.name for entry in path.iterdir())
        if len(entries) > MAX_LIST_ENTRIES:
            raise ValueError(f"Directory has more than {MAX_LIST_ENTRIES} entries")
        return entries

    def write_file(self, arguments: dict[str, Any]) -> dict[str, Any]:
        path = self._require_resolved(arguments)
        content = arguments.get("content")
        if not isinstance(content, str):
            raise ValueError("Content must be a string")  # noqa: TRY004 - untrusted input contract
        data = content.encode("utf-8")
        if len(data) > self._max_write:
            raise ValueError(f"Write exceeds {self._max_write} byte limit")
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            handle.write(content)
        return {"written_bytes": len(data)}

    def delete_file(self, arguments: dict[str, Any]) -> dict[str, Any]:
        path = self._require_resolved(arguments)
        if not path.is_file():
            raise FileNotFoundError("Target is not a regular file")
        path.unlink()
        return {"deleted": True}

    def _require_resolved(self, arguments: dict[str, Any]) -> Path:
        raw = arguments.get("path")
        if not isinstance(raw, str):
            raise ValueError("A string 'path' argument is required")  # noqa: TRY004
        return self._boundary.resolve_within(raw)

    @staticmethod
    def _bounded_int(value: Any, name: str) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"'{name}' must be a non-negative integer")
        return value
