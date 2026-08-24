import io
import urllib.error

import pytest
from app.application.inference import (
    InferenceFailed,
    InferenceRuntimeUnavailable,
    InferenceTimeout,
    ModelNotFound,
)
from app.infrastructure.inference_llamacpp import LlamaCppAdapter


class FakeResponse(io.BytesIO):
    def __init__(self, body: bytes, status: int = 200):
        super().__init__(body)
        self.status = status


def _adapter(opener, model_path=None):
    return LlamaCppAdapter(
        base_url="http://127.0.0.1:8080/",
        model_name="qwen3",
        timeout_seconds=5.0,
        model_path=model_path,
        opener=opener,
    )


def _ok_opener(body: bytes, status: int = 200):
    def opener(request, timeout=None):
        return FakeResponse(body, status)

    return opener


def test_complete_returns_content():
    opener = _ok_opener(
        b'{"choices": [{"message": {"content": "hello from qwen"}}]}'
    )
    assert _adapter(opener).complete("hi") == "hello from qwen"


def test_connection_refused_maps_to_runtime_unavailable():
    def opener(request, timeout=None):
        raise urllib.error.URLError(ConnectionRefusedError())

    with pytest.raises(InferenceRuntimeUnavailable):
        _adapter(opener).complete("hi")


def test_timeout_inside_url_error_maps_to_inference_timeout():
    def opener(request, timeout=None):
        raise urllib.error.URLError(TimeoutError())

    with pytest.raises(InferenceTimeout):
        _adapter(opener).complete("hi")


def test_direct_timeout_maps_to_inference_timeout():
    def opener(request, timeout=None):
        raise TimeoutError()

    with pytest.raises(InferenceTimeout):
        _adapter(opener).complete("hi")


def test_http_500_maps_to_inference_failed():
    def opener(request, timeout=None):
        raise urllib.error.HTTPError(request.full_url, 500, "boom", None, io.BytesIO(b"error"))

    with pytest.raises(InferenceFailed):
        _adapter(opener).complete("hi")


def test_malformed_output_maps_to_inference_failed():
    opener = _ok_opener(b'{"unexpected": true}')
    with pytest.raises(InferenceFailed):
        _adapter(opener).complete("hi")


def test_missing_model_file_blocks_completion(tmp_path):
    missing = tmp_path / "missing.gguf"
    adapter = _adapter(
        _ok_opener(b'{"choices": [{"message": {"content": "x"}}]}'),
        model_path=str(missing),
    )
    with pytest.raises(ModelNotFound):
        adapter.complete("hi")


def test_health_reports_model_not_found(tmp_path):
    missing = tmp_path / "missing.gguf"
    adapter = _adapter(_ok_opener(b"{}"), model_path=str(missing))
    assert adapter.health() == "model_not_found"


def test_health_ready():
    adapter = _adapter(_ok_opener(b'{"status": "ok"}'))
    assert adapter.health() == "ready"


def test_health_loading_when_server_reports_503():
    def opener(request, timeout=None):
        raise urllib.error.HTTPError(request.full_url, 503, "loading", None, io.BytesIO(b"{}"))

    assert _adapter(opener).health() == "loading"


def test_health_error_on_unexpected_status():
    def opener(request, timeout=None):
        raise urllib.error.HTTPError(request.full_url, 500, "broken", None, io.BytesIO(b"{}"))

    assert _adapter(opener).health() == "error"


def test_health_propagates_runtime_unavailable():
    def opener(request, timeout=None):
        raise urllib.error.URLError(ConnectionRefusedError())

    with pytest.raises(InferenceRuntimeUnavailable):
        _adapter(opener).health()
