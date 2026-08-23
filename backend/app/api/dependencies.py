from collections.abc import Iterator

from sqlalchemy.orm import Session

from app.application.inference import InferencePort
from app.config.settings import get_settings
from app.infrastructure.db import create_session_factory
from app.infrastructure.inference_llamacpp import LlamaCppAdapter
from app.infrastructure.inference_stub import StubInference


def build_inference(settings=None) -> InferencePort:
    settings = settings or get_settings()
    if settings.model_runtime == "stub":
        return StubInference()
    if settings.model_runtime != "llama_cpp":
        raise ValueError(f"Unknown model_runtime: {settings.model_runtime}")
    return LlamaCppAdapter(
        base_url=settings.model_server_url,
        model_name=settings.model_name,
        timeout_seconds=settings.inference_timeout_seconds,
        model_path=settings.model_path or None,
    )


def get_inference() -> InferencePort:
    return build_inference()


def get_session() -> Iterator[Session]:
    factory = create_session_factory(get_settings().database_url)
    session = factory()
    try:
        yield session
    finally:
        session.close()
