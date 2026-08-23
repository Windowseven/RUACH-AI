"""Append-only audit log with bounded retention (docs/05 §41–§44, P11A).

The AI never writes here. Retention policy:

- The ACTIVE segment (audit.jsonl) rotates when it reaches
  ``max_bytes``: it is RENAMED to ``audit.jsonl.1`` and older segments
  shift (``audit.jsonl.1 -> audit.jsonl.2`` ...). Rotation renames
  evidence; it never truncates or rewrites it.
- At most ``retention_segments`` rotated segments are kept. When the
  oldest segment falls out of that window it is deleted — this is the
  DOCUMENTED retention boundary, not a silent loss: every event survives
  in the active segment plus N full historical segments before aging out.
- Failure behavior: any OS-level failure to rotate or append raises
  :class:`AuditWriteError`. Callers classify it as infrastructure
  failure (SYSTEM_ERROR), so tool operations FAIL CLOSED instead of
  executing unlogged. Nothing is silently swallowed.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

DEFAULT_MAX_BYTES = 5_000_000
DEFAULT_RETENTION_SEGMENTS = 2


class AuditWriteError(RuntimeError):
    """The audit log could not be written; operations must fail closed."""


class AuditLog:
    def __init__(
        self,
        path: Path,
        clock: Any = time.time,
        max_bytes: int = DEFAULT_MAX_BYTES,
        retention_segments: int = DEFAULT_RETENTION_SEGMENTS,
    ) -> None:
        self._path = Path(path)
        self._clock = clock
        self._max_bytes = max(1, max_bytes)
        self._retention_segments = max(0, retention_segments)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def emit(self, event: str, **fields: Any) -> None:
        record = {"timestamp": self._clock(), "event": event, **fields}
        line = json.dumps(record, sort_keys=True) + "\n"
        try:
            self._rotate_if_full(len(line))
            with self._path.open("a", encoding="utf-8") as handle:
                handle.write(line)
        except OSError as error:
            raise AuditWriteError(f"audit log write failed: {error}") from error

    def _rotate_if_full(self, incoming_bytes: int) -> None:
        try:
            current_size = self._path.stat().st_size if self._path.exists() else 0
        except OSError as error:
            raise AuditWriteError(f"audit log stat failed: {error}") from error
        if current_size + incoming_bytes <= self._max_bytes:
            return
        # Shift audit.jsonl.N -> audit.jsonl.(N+1), dropping the oldest.
        oldest = self._path.with_suffix(self._path.suffix + f".{self._retention_segments}")
        if self._retention_segments > 0 and oldest.exists():
            oldest.unlink()
        for index in range(self._retention_segments - 1, 0, -1):
            source = self._path.with_suffix(self._path.suffix + f".{index}")
            if source.exists():
                source.replace(
                    self._path.with_suffix(self._path.suffix + f".{index + 1}")
                )
        if self._retention_segments > 0:
            self._path.replace(self._path.with_suffix(self._path.suffix + ".1"))
        else:
            # Retention disabled means the active segment starts over;
            # configured deployments should keep segments > 0.
            self._path.unlink()

    def read_all(self) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        segments: list[Path] = []
        for index in range(self._retention_segments, 0, -1):
            candidate = self._path.with_suffix(self._path.suffix + f".{index}")
            if candidate.exists():
                segments.append(candidate)
        for segment_path in [*segments, self._path]:
            if not segment_path.exists():
                continue
            lines = segment_path.read_text(encoding="utf-8").splitlines()
            records.extend(json.loads(line) for line in lines if line.strip())
        return records
