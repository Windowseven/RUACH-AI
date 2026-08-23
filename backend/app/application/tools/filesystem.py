"""Bounded filesystem executor using direct OS APIs, never shell strings (docs/05 §12–§13).

All path mechanics go through WorkspaceBoundary's dirfd walk (P11B):
symlinks are never followed and opens are race-hardened at the kernel
level. Size caps and type checks remain here as policy.
"""

from __future__ import annotations

import os
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
        raw = self._require_string_path(arguments)
        offset = self._bounded_int(arguments.get("offset", 0), "offset")
        raw_limit = arguments.get("limit")
        if raw_limit is None:
            probe_fd, stat = self._boundary.open_read(raw)
            remaining = max(stat.st_size - offset, 0)
            os.close(probe_fd)
            if remaining > self._max_read:
                raise ValueError(f"File exceeds the {self._max_read} byte read cap")
            limit = remaining
        else:
            limit = self._bounded_int(raw_limit, "limit")
            if limit > self._max_read:
                raise ValueError(f"Read limit exceeds {self._max_read} bytes")
        fd, _stat = self._boundary.open_read(raw)
        try:
            if offset:
                os.lseek(fd, offset, os.SEEK_SET)
            data = b""
            while len(data) < limit:
                chunk = os.read(fd, min(65536, limit - len(data)))
                if not chunk:
                    break
                data += chunk
        finally:
            os.close(fd)
        return data.decode("utf-8", errors="replace")

    def list_directory(self, arguments: dict[str, Any]) -> list[str]:
        entries = self._boundary.list_dir(self._require_string_path(arguments))
        if len(entries) > MAX_LIST_ENTRIES:
            raise ValueError(f"Directory has more than {MAX_LIST_ENTRIES} entries")
        return entries

    def write_file(self, arguments: dict[str, Any]) -> dict[str, Any]:
        raw = self._require_string_path(arguments)
        content = arguments.get("content")
        if not isinstance(content, str):
            raise ValueError("Content must be a string")  # noqa: TRY004 - untrusted input contract
        data = content.encode("utf-8")
        if len(data) > self._max_write:
            raise ValueError(f"Write exceeds {self._max_write} byte limit")
        fd = self._boundary.open_write(raw)
        try:
            written = 0
            while written < len(data):
                written += os.write(fd, data[written:])
        finally:
            os.close(fd)
        return {"written_bytes": written}

    def delete_file(self, arguments: dict[str, Any]) -> dict[str, Any]:
        raw = self._require_string_path(arguments)
        try:
            self._boundary.unlink_file(raw)
        except FileNotFoundError as error:
            raise FileNotFoundError("Target is not a regular file") from error
        return {"deleted": True}

    def _require_string_path(self, arguments: dict[str, Any]) -> str:
        raw = arguments.get("path")
        if not isinstance(raw, str):
            raise ValueError("A string 'path' argument is required")  # noqa: TRY004
        # Policy-level containment for audit/policy; execution re-derives
        # independently through the dirfd walk.
        self._boundary.resolve_within(raw)
        return raw

    @staticmethod
    def _bounded_int(value: Any, name: str) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"'{name}' must be a non-negative integer")
        return value
