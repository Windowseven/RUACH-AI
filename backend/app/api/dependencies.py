from collections.abc import Iterator
from pathlib import Path

from sqlalchemy.orm import Session

from app.application.inference import InferencePort
from app.application.tools.audit import AuditLog
from app.application.tools.engine import ToolEngine
from app.application.tools.paths import WorkspaceBoundary
from app.config.settings import Settings, get_settings
from app.infrastructure.approval_store_db import PersistentApprovalStore
from app.infrastructure.db import create_session_factory
from app.infrastructure.inference_llamacpp import LlamaCppAdapter
from app.infrastructure.inference_stub import StubInference


def build_inference(settings: Settings | None = None) -> InferencePort:
    settings = settings or get_settings()
    if settings.model_runtime == "stub":
        return StubInference()
    if settings.model_runtime != "llama_cpp":
        raise ValueError(f"Unknown model_runtime: {settings.model_runtime}")
    return LlamaCppAdapter(
        base_url=settings.model_server_url,
        model_name=settings.model_name,
        timeout_seconds=settings.inference_timeout_seconds,
        max_tokens=settings.inference_max_tokens,
        temperature=settings.inference_temperature,
        model_path=settings.model_path or None,
    )


def get_inference() -> InferencePort:
    return build_inference()


_engine: ToolEngine | None = None


def get_tool_engine() -> ToolEngine:
    global _engine
    if _engine is None:
        settings = get_settings()
        boundary = WorkspaceBoundary(Path(settings.workspace_path))
        sessions = create_session_factory(settings.database_url)
        approvals = PersistentApprovalStore(
            sessions, ttl_seconds=settings.approval_ttl_seconds
        )
        audit = AuditLog(
            Path(settings.audit_log_path),
            max_bytes=settings.audit_max_bytes,
            retention_segments=settings.audit_retention_segments,
        )
        _engine = ToolEngine(boundary, approvals, audit)
        # Explicit transition for anything stale across restarts (docs/13 P4).
        _engine.expire_stale_approvals()
    return _engine


def get_session() -> Iterator[Session]:
    factory = create_session_factory(get_settings().database_url)
    session = factory()
    try:
        yield session
    finally:
        session.close()
