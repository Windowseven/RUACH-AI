import http.server
import os
import socketserver
import threading
from typing import ClassVar

import pytest


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
    """Real localhost HTTP server serving a random blob. Yields (url, handler, payload)."""
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
