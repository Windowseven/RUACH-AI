import os

import pytest

from app.config.settings import get_settings
from app.infrastructure.inference_llamacpp import LlamaCppAdapter

pytestmark = pytest.mark.skipif(
    os.environ.get("RUACH_LIVE_INFERENCE") != "1",
    reason="Requires a running local llama-server with the configured GGUF model.",
)


def test_live_llama_cpp_round_trip():
    settings = get_settings()
    adapter = LlamaCppAdapter(
        base_url=settings.model_server_url,
        model_name=settings.model_name,
        timeout_seconds=settings.inference_timeout_seconds,
    )
    assert adapter.health() == "ready"
    reply = adapter.complete("Say OK.")
    assert reply.strip()
