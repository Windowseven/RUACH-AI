"""Local operation logging for Doctor and Setup.

Implements docs/15 §36 (logs record timestamp/operation/component/result/
error/profile; never secrets), docs/16 §28 (~/.ruach/logs/setup.log) and
docs/17 §20 (per-area timestamped logs under ~/.ruach/logs/, logs never
dominate the interactive UI).

Layout:
    ~/.ruach/logs/<area>/<YYYYMMDD-HHMMSS>-<operation>.log   per-run files
    ~/.ruach/logs/setup.log                                  append-only feed

Redaction: any key matching a secret pattern is dropped before writing.
Logging failures are swallowed — diagnostics must not crash because the
log directory is unwritable.
"""

from __future__ import annotations

import datetime as _dt
import re
from pathlib import Path
from typing import Any

SECRET_KEY_PATTERN = re.compile(
    r"(password|passwd|secret|token|api[_-]?key|authorization|credential)",
    re.IGNORECASE,
)

AREAS = ("doctor", "setup", "runtime", "model", "install")


def _timestamp() -> str:
    return _dt.datetime.now(_dt.UTC).strftime("%Y%m%d-%H%M%S")


def _stamp() -> str:
    return _dt.datetime.now(_dt.UTC).isoformat(timespec="seconds")


def redact(fields: dict[str, Any]) -> dict[str, Any]:
    """Drop secret-looking keys; values of safe keys pass through."""
    return {
        key: value for key, value in fields.items() if not SECRET_KEY_PATTERN.search(key)
    }


def log_operation(
    area: str,
    operation: str,
    fields: dict[str, Any] | None = None,
    *,
    home: Path | None = None,
) -> Path | None:
    """Write one timestamped operation log under ~/.ruach/logs/<area>/.

    Returns the log path, or None when logging was impossible (never raises).
    """
    base = (home or Path.home()) / ".ruach" / "logs" / area
    safe_fields = redact(fields or {})
    lines = [
        f"timestamp: {_stamp()}",
        f"operation: {operation}",
        *[f"{key}: {value}" for key, value in sorted(safe_fields.items())],
        "",
    ]
    try:
        base.mkdir(parents=True, exist_ok=True)
        path = base / f"{_timestamp()}-{operation}.log"
        path.write_text(NL.join(lines), encoding="utf-8")
        return path
    except OSError:
        return None


def append_setup_log(entry: str, *, home: Path | None = None) -> None:
    """Append one line to ~/.ruach/logs/setup.log (docs/16 §28)."""
    line = f"[{_stamp()}] {entry}"
    try:
        target = (home or Path.home()) / ".ruach" / "logs" / "setup.log"
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "a", encoding="utf-8") as handle:
            handle.write(line + NL)
    except OSError:
        pass


NL = chr(10)  # newline without embedding escape sequences in source


__all__ = ["AREAS", "append_setup_log", "log_operation", "redact"]