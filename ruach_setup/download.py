"""Resumable, verifying downloader (ARCH-009 §31).

Real stdlib HTTP against real servers:
- streams to `<dest>.part`, atomically renames on success
- resumes with a Range header when a partial file exists (best effort: if a
  redirect chain drops the Range header the server answers 200 and the
  download correctly restarts from zero instead of corrupting the file)
- computes SHA-256 while streaming
- when expected_sha256 is None the computed hash is RETURNED for
  trust-on-first-use recording; when provided, mismatch deletes the part
  and raises — a partial file never becomes a valid artifact
"""

import hashlib
import os
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

CHUNK_SIZE = 1024 * 1024


class DownloadError(Exception):
    """Base class for download failures."""


class ChecksumMismatch(DownloadError):
    """Downloaded bytes did not match the expected SHA-256."""


@dataclass(frozen=True)
class DownloadResult:
    path: Path
    bytes_total: int
    resumed: bool
    sha256: str


def sha256_of_file(path: Path, chunk_size: int = CHUNK_SIZE) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def download(
    url: str,
    dest: Path,
    expected_sha256: str | None = None,
    timeout_seconds: float = 60.0,
    progress: Callable[[int, int | None], None] | None = None,
) -> DownloadResult:
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    part_path = dest.with_suffix(dest.suffix + ".part")

    part_size = part_path.stat().st_size if part_path.is_file() else 0
    headers = {"Range": f"bytes={part_size}-"} if part_size else {}

    request = urllib.request.Request(url, headers=headers)
    try:
        response = urllib.request.urlopen(request, timeout=timeout_seconds)
    except (urllib.error.URLError, OSError) as error:
        raise DownloadError(f"Could not reach {url}: {error}") from error

    with response:
        status = getattr(response, "status", 200)
        if status != 206:
            part_size = 0
            mode = "wb"
        else:
            mode = "ab"

        content_length = response.headers.get("Content-Length")
        total: int | None
        if content_length is None:
            total = None
        elif status == 206:
            total = part_size + int(content_length)
        else:
            total = int(content_length)

        digest = hashlib.sha256()
        if status == 206 and part_size:
            with open(part_path, "rb") as existing:
                while chunk := existing.read(CHUNK_SIZE):
                    digest.update(chunk)
        written = 0
        with open(part_path, mode) as handle:
            while chunk := response.read(CHUNK_SIZE):
                handle.write(chunk)
                digest.update(chunk)
                written += len(chunk)
                if progress is not None:
                    progress((part_size if status == 206 else 0) + written, total)

    if total is not None and (part_size if status == 206 else 0) + written < total:
        raise DownloadError(
            f"Connection closed early: got {(part_size or 0) + written} of {total} bytes."
        )

    actual_hash = digest.hexdigest()
    if expected_sha256 is not None and actual_hash != expected_sha256.lower():
        part_path.unlink(missing_ok=True)
        raise ChecksumMismatch(
            f"SHA-256 mismatch for {url}: expected {expected_sha256}, got {actual_hash}."
        )

    os.replace(part_path, dest)
    return DownloadResult(
        path=dest,
        bytes_total=(part_size if status == 206 else 0) + written,
        resumed=status == 206 and part_size > 0,
        sha256=actual_hash,
    )
