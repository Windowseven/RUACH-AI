from collections.abc import Iterator
from pathlib import Path

from sqlalchemy.orm import Session

from app.application.inference import InferencePort
from app.application.orchestrator import ApprovalIndex
from app.application.tools.approvals import InMemoryApprovalStore
from app.application.tools.audit import AuditLog
from app.application.tools.engine import ToolEngine
from app.application.tools.paths import WorkspaceBoundary
from app.config.settings import Settings, get_settings
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
        model_path=settings.model_path or None,
    )


def get_inference() -> InferencePort:
    return build_inference()


_engine: ToolEngine | None = None
_approval_index: ApprovalIndex | None = None


def get_tool_engine() -> ToolEngine:
    global _engine
    if _engine is None:
        settings = get_settings()
        boundary = WorkspaceBoundary(Path(settings.workspace_path))
        approvals = InMemoryApprovalStore()
        audit = AuditLog(Path(settings.audit_log_path))
        _engine = ToolEngine(boundary, approvals, audit)
    return _engine


def get_approval_index() -> ApprovalIndex:
    global _approval_index
    if _approval_index is None:
        _approval_index = ApprovalIndex()
    return _approval_index


def get_session() -> Iterator[Session]:
    factory = create_session_factory(get_settings().database_url)
    session = factory()
    try:
        yield session
    finally:
        session.close()
