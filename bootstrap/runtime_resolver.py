"""RuntimeResolver (P12 §7): no hardcoded runtime paths.

Resolution order — first executable regular file wins:

1. Explicit configuration: RUACH_LLAMA_SERVER_BIN (env or generated
   config) — an operator override.
2. User-local install: ~/.ruach/runtime/llama-server
3. Project-local build: <repo>/.build/runtime/llama-server
4. PATH lookup: `llama-server` on the standard PATH (Termux packages
   install here; $HOME expansion makes order 2 platform-appropriate
   WITHOUT any platform branch in application code).

The resolver returns WHERE the executable lives; nothing above the
bootstrap layer knows or cares. macOS and Termux differ only in which
location exists.

Statuses per reporting rule: Implemented YES; Mac verified YES;
Termux verified NO (target validation pending).
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ResolvedRuntime:
    path: Path | None
    source: str  # "config" | "user" | "project" | "path" | "missing"

    @property
    def found(self) -> bool:
        return self.path is not None


def _executable(path: Path) -> bool:
    return path.is_file() and os.access(path, os.X_OK)


def resolve_llama_server(
    *,
    explicit: str | None = None,
    home: Path | None = None,
    project_root: Path | None = None,
    path_lookup=shutil.which,
) -> ResolvedRuntime:
    home = home if home is not None else Path.home()
    project_root = (
        project_root
        if project_root is not None
        else Path(__file__).resolve().parent.parent
    )

    candidates: list[tuple[Path, str]] = []
    if explicit:
        candidates.append((Path(explicit).expanduser(), "config"))
    candidates.append((home / ".ruach" / "runtime" / "llama-server", "user"))
    candidates.append((project_root / ".build" / "runtime" / "llama-server", "project"))

    for candidate, source in candidates:
        if _executable(candidate):
            return ResolvedRuntime(candidate, source)

    found_on_path = path_lookup("llama-server")
    if found_on_path:
        return ResolvedRuntime(Path(found_on_path), "path")

    return ResolvedRuntime(None, "missing")


def configured_binary_override(env: dict[str, str]) -> str | None:
    value = env.get("RUACH_LLAMA_SERVER_BIN", "").strip()
    return value or None
