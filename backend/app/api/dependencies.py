from collections.abc import Iterator

from sqlalchemy.orm import Session

from app.config.settings import get_settings
from app.infrastructure.db import create_session_factory
from app.infrastructure.inference_llamacpp import LlamaCppAdapter


def get_inference() -> LlamaCppAdapter:
    settings = get_settings()
    return LlamaCppAdapter(
        base_url=settings.model_server_url,
        model_name=settings.model_name,
        timeout_seconds=settings.inference_timeout_seconds,
        model_path=settings.model_path or None,
    )


def get_session() -> Iterator[Session]:
    factory = create_session_factory(get_settings().database_url)
    session = factory()
    try:
        yield session
    finally:
        session.close()
