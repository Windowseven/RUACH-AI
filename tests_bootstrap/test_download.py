import hashlib
import http.server
import os
import socketserver
import threading
from typing import ClassVar

import pytest

from ruach_setup.download import ChecksumMismatch, download


class _RangeHandler(http.server.BaseHTTPRequestHandler):
    payload: bytes = b""
    range_hits: ClassVar[list[str | None]] = []
    ignore_range = False

    def do_GET(self) -> None:
        rng = self.headers.get("Range")
        type(self).range_hits.append(rng)
        data = self.payload
        if rng and not self.ignore_range and rng.startswith("bytes="):
            start = int(rng.removeprefix("bytes=").split("-")[0])
            chunk = data[start:]
            self.send_response(206)
            self.send_header("Content-Length", str(len(chunk)))
            self.send_header("Content-Range", f"bytes {start}-{len(data) - 1}/{len(data)}")
            self.end_headers()
            self.wfile.write(chunk)
        else:
            self.send_response(200)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    def log_message(self, *args) -> None:
        pass


@pytest.fixture()
def file_server(tmp_path):
    payload = os.urandom(3 * 1024 * 1024 + 12345)
    srv_dir = tmp_path / "srv"
    srv_dir.mkdir()
    (srv_dir / "blob.bin").write_bytes(payload)

    handler = type("Handler", (_RangeHandler,), {"payload": payload, "range_hits": []})
    with socketserver.ThreadingTCPServer(("127.0.0.1", 0), handler) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        yield f"http://127.0.0.1:{server.server_address[1]}/blob.bin", handler, payload
        server.shutdown()


def test_full_download_verifies_hash_and_cleans_part(file_server, tmp_path):
    url, _handler, payload = file_server
    dest = tmp_path / "out" / "blob.bin"

    result = download(url, dest, expected_sha256=hashlib.sha256(payload).hexdigest())

    assert dest.read_bytes() == payload
    assert result.sha256 == hashlib.sha256(payload).hexdigest()
    assert result.resumed is False
    assert not dest.with_suffix(".bin.part").exists()


def test_resume_sends_real_range_header_and_completes(file_server, tmp_path):
    url, handler, payload = file_server
    dest = tmp_path / "blob.bin"
    part = dest.with_suffix(".bin.part")
    part.write_bytes(payload[:1_000_000])

    result = download(url, dest, expected_sha256=hashlib.sha256(payload).hexdigest())

    assert "bytes=1000000-" in handler.range_hits
    assert result.resumed is True
    assert dest.read_bytes() == payload
    assert not part.exists()


def test_checksum_mismatch_deletes_part_and_final(file_server, tmp_path):
    url, _handler, _payload = file_server
    dest = tmp_path / "blob.bin"
    dest.with_suffix(".bin.part").write_bytes(b"x")

    with pytest.raises(ChecksumMismatch):
        download(url, dest, expected_sha256="0" * 64)

    assert not dest.exists()
    assert not dest.with_suffix(".bin.part").exists()


def test_server_without_range_support_restarts_cleanly(file_server, tmp_path):
    url, handler, payload = file_server
    dest = tmp_path / "blob.bin"
    dest.with_suffix(".bin.part").write_bytes(payload[:500_000])
    handler.ignore_range = True

    try:
        result = download(url, dest, expected_sha256=hashlib.sha256(payload).hexdigest())
    finally:
        handler.ignore_range = False

    assert result.resumed is False
    assert dest.read_bytes() == payload


def test_progress_callback_reports_totals(file_server, tmp_path):
    url, _handler, payload = file_server
    seen: list[tuple[int, int | None]] = []

    download(url, tmp_path / "blob.bin", progress=lambda done, total: seen.append((done, total)))

    assert seen[-1] == (len(payload), len(payload))
    assert all(t == len(payload) for _, t in seen)
