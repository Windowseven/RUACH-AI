"""Storage preflight (ARCH-009 §12).

Refuses to let a download start when free space cannot hold it plus margin.
Real disk statistics via shutil; the caller decides what failure means.
"""

import shutil
from dataclasses import dataclass
from pathlib import Path

DEFAULT_MARGIN_PERCENT = 10


@dataclass(frozen=True)
class StorageCheck:
    ok: bool
    required_bytes: int
    available_bytes: int


def check_storage(
    dest_dir: Path,
    required_bytes: int,
    margin_percent: int = DEFAULT_MARGIN_PERCENT,
) -> StorageCheck:
    dest_dir = Path(dest_dir)
    probe = dest_dir
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    available = shutil.disk_usage(probe).free
    required = required_bytes * (100 + margin_percent) // 100
    return StorageCheck(
        ok=available >= required,
        required_bytes=required,
        available_bytes=available,
    )
